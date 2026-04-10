"""
Orchestrator — LangGraph StateGraph che coordina tutti gli agenti.

Grafo:
  load_data → engineer_features → assess_risk → write_output → END
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from agents.data_loader import load_all
from agents.feature_engineer import build_all_features
from agents.risk_assessor import RiskAssessment, assess_all_citizens


# ---------------------------------------------------------------------------
# Stato condiviso tra i nodi
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    # Input
    data_dir: str
    output_path: str
    strategy: str

    # Prodotti dai nodi
    status: Any          # pd.DataFrame
    users: Any           # pd.DataFrame
    locations: Any       # pd.DataFrame
    personas: dict
    citizen_ids: list[str]
    all_features: list[dict]
    assessments: list[dict]  # RiskAssessment serializzati come dict
    citizens_at_risk: list[str]


# ---------------------------------------------------------------------------
# Nodi del grafo
# ---------------------------------------------------------------------------

def node_load_data(state: PipelineState) -> dict:
    """Nodo 1: carica tutte le sorgenti dati."""
    print("\n[1/4] DataLoader Agent — caricamento dati...")
    data = load_all(state["data_dir"])
    print(
        f"      status: {len(data['status'])} eventi | "
        f"users: {len(data['users'])} | "
        f"locations: {len(data['locations'])} | "
        f"cittadini: {len(data['citizen_ids'])}"
    )
    return {
        "status": data["status"],
        "users": data["users"],
        "locations": data["locations"],
        "personas": data["personas"],
        "citizen_ids": data["citizen_ids"],
    }


def node_engineer_features(state: PipelineState) -> dict:
    """Nodo 2: costruisce le feature numeriche per ogni cittadino."""
    print("\n[2/4] Feature Engineering Agent — calcolo feature...")
    features = build_all_features(
        citizen_ids=state["citizen_ids"],
        status=state["status"],
        users=state["users"],
        locations=state["locations"],
    )
    for f in features:
        print(
            f"      {f['citizen_id']} | età={f['age']} | "
            f"physical={f['mean_physical_activity']} | "
            f"sleep={f['mean_sleep_quality']} | "
            f"rog={f['radius_of_gyration_km']}km | "
            f"risk_score={f['heuristic_risk_score']}"
        )
    return {"all_features": features}


def node_assess_risk(state: PipelineState) -> dict:
    """Nodo 3: classifica ogni cittadino con la strategia scelta."""
    strategy = state.get("strategy", "hybrid")
    print(f"\n[3/4] Risk Assessment Agent — classificazione (strategy='{strategy}')...")

    assessments = assess_all_citizens(
        all_features=state["all_features"],
        personas=state["personas"],
        strategy=strategy,
    )

    citizens_at_risk = [a.citizen_id for a in assessments if a.risk_label == 1]
    print(f"\n      Cittadini a rischio identificati: {citizens_at_risk}")

    return {
        "assessments": [a.model_dump() for a in assessments],
        "citizens_at_risk": citizens_at_risk,
    }


def node_write_output(state: PipelineState) -> dict:
    """Nodo 4: scrive il file di output nel formato richiesto dalla challenge."""
    output_path = Path(state["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    citizens_at_risk = state["citizens_at_risk"]

    print(f"\n[4/4] Output Writer — scrittura in '{output_path}'...")
    with open(output_path, "w", encoding="ascii") as f:
        for cid in citizens_at_risk:
            f.write(f"{cid}\n")

    print(f"      {len(citizens_at_risk)} cittadini scritti nel file di output.")

    # Report leggibile su stdout
    print("\n" + "=" * 60)
    print("REPORT FINALE")
    print("=" * 60)
    for a in state["assessments"]:
        label_str = "PREVENTIVO [1]" if a["risk_label"] == 1 else "STANDARD   [0]"
        print(f"  {a['citizen_id']} → {label_str} (conf={a['confidence']:.2f})")
        print(f"    {a['reasoning'][:100]}")
    print("=" * 60)

    return {}


# ---------------------------------------------------------------------------
# Costruzione e compilazione del grafo
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Costruisce e compila il LangGraph StateGraph."""
    graph = StateGraph(PipelineState)

    graph.add_node("load_data", node_load_data)
    graph.add_node("engineer_features", node_engineer_features)
    graph.add_node("assess_risk", node_assess_risk)
    graph.add_node("write_output", node_write_output)

    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "engineer_features")
    graph.add_edge("engineer_features", "assess_risk")
    graph.add_edge("assess_risk", "write_output")
    graph.add_edge("write_output", END)

    return graph.compile()


def run_pipeline(
    data_dir: str,
    output_path: str,
    strategy: Literal["llm", "heuristic", "hybrid"] = "hybrid",
) -> list[str]:
    """
    Esegue l'intera pipeline e restituisce i Citizen ID a rischio.

    Parameters
    ----------
    data_dir    : cartella con status.csv, users.json, locations.json, personas.md
    output_path : percorso del file di output (ASCII, un CitizenID per riga)
    strategy    : "llm" | "heuristic" | "hybrid"
    """
    app = build_graph()
    final_state = app.invoke(
        {
            "data_dir": data_dir,
            "output_path": output_path,
            "strategy": strategy,
        }
    )
    return final_state.get("citizens_at_risk", [])
