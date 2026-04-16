"""
Orchestrator — LangGraph StateGraph con cicli condizionali guidati dall'LLM.

Flusso:
  START
    → load_data
    → analyze_citizens          (ReAct loop per ogni cittadino)
    → population_review         (supervisor meta-agent)
    → [conditional edge]
        ┌─ se supervisor chiede re-analisi E round < MAX_REANALYSIS_ROUNDS
        │     → reanalyze_citizens  (solo i cittadini borderline)
        │     → population_review   (secondo passaggio del supervisor)
        └─ altrimenti
              → write_output
    → END

La differenza fondamentale rispetto a solution/:
- I nodi guidati dall'LLM decidono cosa fare (tool-calling interno)
- Il flusso del grafo stesso dipende da decisioni dell'LLM (conditional edge)
- Non esiste feature engineering pre-calcolato: ogni agente parte da zero
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from agents.citizen_analyst import CitizenAssessment, analyze_citizen
from agents.data_loader import load_all
from agents.llm_factory import build_llm, generate_session_id
from agents.population_supervisor import SupervisorDecision, run_population_review
from agents.tools import init_data_store

MAX_REANALYSIS_ROUNDS = 2  # evita loop infiniti

# Tuning anti-rate-limit (override via env)
CALL_DELAY_SECONDS = float(os.getenv("AGENT_CALL_DELAY_SECONDS", "1.5"))
MAX_RATE_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "4"))
BASE_RETRY_WAIT_SECONDS = float(os.getenv("AGENT_RETRY_BACKOFF_SECONDS", "8"))


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "ratelimit" in text


def _sleep_between_calls() -> None:
    if CALL_DELAY_SECONDS > 0:
        time.sleep(CALL_DELAY_SECONDS)


def _run_with_retry(callable_fn: Any, action_label: str) -> Any:
    """Retry helper for LLM calls that fail with transient 429/rate-limit errors."""
    attempt = 1
    while True:
        try:
            return callable_fn()
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt >= MAX_RATE_RETRIES:
                raise

            wait_s = BASE_RETRY_WAIT_SECONDS * (2 ** (attempt - 1))
            print(
                f"    [Retry] {action_label}: rate-limit rilevato, "
                f"tentativo {attempt + 1}/{MAX_RATE_RETRIES} tra {wait_s:.1f}s..."
            )
            time.sleep(wait_s)
            attempt += 1


# ---------------------------------------------------------------------------
# Stato condiviso del grafo
# ---------------------------------------------------------------------------

class AgenticState(TypedDict):
    # Input
    data_dir: str
    output_path: str

    # Sessione Langfuse (condivisa da tutti gli agenti)
    session_id: str

    # Dati caricati
    status: Any
    users: Any
    locations: Any
    personas: dict
    citizen_ids: list[str]

    # Output degli agenti
    individual_assessments: dict[str, dict]   # citizen_id → assessment dict
    supervisor_decision: dict                  # SupervisorDecision serializzata
    final_citizens_at_risk: list[str]

    # Controllo del loop di re-analisi
    reanalysis_round: int
    citizens_to_reanalyze: list[str]


# ---------------------------------------------------------------------------
# Nodo 1 — Caricamento dati
# ---------------------------------------------------------------------------

def node_load_data(state: AgenticState) -> dict:
    print("\n[1/4] DataLoader — caricamento dati...")
    data = load_all(state["data_dir"])

    # Inizializza il DataStore globale usato dai tool
    init_data_store(data)

    session_id = generate_session_id()
    print(f"      Session ID (Langfuse): {session_id}")
    print(
        f"      status={len(data['status'])} eventi | "
        f"citizens={len(data['citizen_ids'])}"
    )

    return {
        "status": data["status"],
        "users": data["users"],
        "locations": data["locations"],
        "personas": data["personas"],
        "citizen_ids": data["citizen_ids"],
        "session_id": session_id,
        "individual_assessments": {},
        "reanalysis_round": 0,
        "citizens_to_reanalyze": [],
    }


# ---------------------------------------------------------------------------
# Nodo 2 — Analisi individuale (tutti i cittadini)
# ---------------------------------------------------------------------------

def node_analyze_citizens(state: AgenticState) -> dict:
    citizen_ids = state["citizen_ids"]
    session_id = state["session_id"]
    current_assessments = dict(state.get("individual_assessments", {}))

    print(f"\n[2/4] Citizen Analyst — analisi individuale ({len(citizen_ids)} citizens)...")

    llm = build_llm(session_id=session_id, agent_name="citizen_analyst")

    for i, cid in enumerate(citizen_ids):
        if i > 0:
            _sleep_between_calls()
        print(f"  → Analisi {cid}...")
        assessment: CitizenAssessment = _run_with_retry(
            lambda cid=cid: analyze_citizen(citizen_id=cid, llm=llm),
            action_label=f"Analisi {cid}",
        )
        current_assessments[cid] = assessment.model_dump()

    return {"individual_assessments": current_assessments}


# ---------------------------------------------------------------------------
# Nodo 3 — Re-analisi cittadini borderline (richiesta dal supervisor)
# ---------------------------------------------------------------------------

def node_reanalyze_citizens(state: AgenticState) -> dict:
    to_reanalyze = state["citizens_to_reanalyze"]
    session_id = state["session_id"]
    current_assessments = dict(state["individual_assessments"])
    round_num = state["reanalysis_round"] + 1

    print(
        f"\n[2b] Citizen Analyst — re-analisi round {round_num} "
        f"({len(to_reanalyze)} citizens borderline)..."
    )

    # Usa temperatura leggermente più alta per esplorare alternative
    llm = build_llm(
        session_id=session_id,
        agent_name=f"citizen_analyst_round{round_num}",
        temperature=0.1,
    )

    for i, cid in enumerate(to_reanalyze):
        if i > 0:
            _sleep_between_calls()
        print(f"  → Re-analisi {cid}...")
        assessment: CitizenAssessment = _run_with_retry(
            lambda cid=cid: analyze_citizen(citizen_id=cid, llm=llm),
            action_label=f"Re-analisi {cid}",
        )
        current_assessments[cid] = assessment.model_dump()

    return {
        "individual_assessments": current_assessments,
        "reanalysis_round": round_num,
        "citizens_to_reanalyze": [],
    }


# ---------------------------------------------------------------------------
# Nodo 4 — Population Supervisor
# ---------------------------------------------------------------------------

def node_population_review(state: AgenticState) -> dict:
    session_id = state["session_id"]
    assessments = state["individual_assessments"]
    round_num = state.get("reanalysis_round", 0)

    print(f"\n[3/4] Population Supervisor — revisione (round {round_num})...")

    llm = build_llm(
        session_id=session_id,
        agent_name=f"supervisor_round{round_num}",
    )

    decision: SupervisorDecision = _run_with_retry(
        lambda: run_population_review(
            individual_assessments=assessments,
            llm=llm,
        ),
        action_label=f"Population review round {round_num}",
    )

    return {
        "supervisor_decision": decision.model_dump(),
        "final_citizens_at_risk": decision.final_citizens_at_risk,
        "citizens_to_reanalyze": decision.citizens_to_reanalyze,
    }


# ---------------------------------------------------------------------------
# Nodo 5 — Scrittura output
# ---------------------------------------------------------------------------

def node_write_output(state: AgenticState) -> dict:
    output_path = Path(state["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    citizens_at_risk = state["final_citizens_at_risk"]

    print(f"\n[4/4] Output Writer — '{output_path}'...")
    with open(output_path, "w", encoding="ascii") as f:
        for cid in citizens_at_risk:
            f.write(f"{cid}\n")

    # Report finale
    print("\n" + "=" * 60)
    print("REPORT FINALE — AGENTIC SYSTEM")
    print("=" * 60)

    assessments = state.get("individual_assessments", {})
    supervisor = state.get("supervisor_decision", {})

    for cid, a in assessments.items():
        final_label = 1 if cid in citizens_at_risk else 0
        original_label = a.get("risk_label", "?")
        revised = " [REVISED by supervisor]" if final_label != original_label else ""
        label_str = "PREVENTIVO [1]" if final_label == 1 else "STANDARD   [0]"
        print(f"  {cid} → {label_str}{revised} (conf={a.get('confidence', 0):.2f})")
        for finding in a.get("key_findings", []):
            print(f"    • {finding}")

    if supervisor.get("population_reasoning"):
        print(f"\nSupervisor reasoning:\n  {supervisor['population_reasoning'][:200]}")

    print(f"\nSession ID (Langfuse): {state['session_id']}")
    print("=" * 60)

    return {}


# ---------------------------------------------------------------------------
# Conditional edge — il supervisor decide se serve un altro round
# ---------------------------------------------------------------------------

def _should_reanalyze(state: AgenticState) -> Literal["reanalyze", "finalize"]:
    """
    Edge condizionale: l'LLM (supervisor) ha già deciso — qui leggiamo solo la sua scelta.
    Se ha richiesto re-analisi E non abbiamo superato il limite → torna indietro.
    """
    to_reanalyze = state.get("citizens_to_reanalyze", [])
    current_round = state.get("reanalysis_round", 0)

    if to_reanalyze and current_round < MAX_REANALYSIS_ROUNDS:
        print(
            f"\n  [Router] Supervisor richiede re-analisi: {to_reanalyze} "
            f"(round {current_round + 1}/{MAX_REANALYSIS_ROUNDS})"
        )
        return "reanalyze"

    return "finalize"


# ---------------------------------------------------------------------------
# Costruzione e compilazione del grafo
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Costruisce e compila il LangGraph StateGraph agentico."""
    graph = StateGraph(AgenticState)

    # Nodi
    graph.add_node("load_data", node_load_data)
    graph.add_node("analyze_citizens", node_analyze_citizens)
    graph.add_node("population_review", node_population_review)
    graph.add_node("reanalyze_citizens", node_reanalyze_citizens)
    graph.add_node("write_output", node_write_output)

    # Edges lineari
    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "analyze_citizens")
    graph.add_edge("analyze_citizens", "population_review")

    # Edge condizionale guidato dalla decisione del supervisor
    graph.add_conditional_edges(
        "population_review",
        _should_reanalyze,
        {
            "reanalyze": "reanalyze_citizens",
            "finalize": "write_output",
        },
    )

    # Dopo la re-analisi torna sempre al supervisor
    graph.add_edge("reanalyze_citizens", "population_review")
    graph.add_edge("write_output", END)

    return graph.compile()


def run_pipeline(
    data_dir: str,
    output_path: str,
) -> list[str]:
    """
    Esegue la pipeline agentica e restituisce i Citizen ID a rischio.

    Differenze rispetto a solution/:
    - Nessun parametro 'strategy': è sempre fully agentic
    - L'LLM guida il flusso tramite tool-calling e conditional edges
    """
    app = build_graph()
    final_state = app.invoke(
        {
            "data_dir": data_dir,
            "output_path": output_path,
        }
    )
    return final_state.get("final_citizens_at_risk", [])
