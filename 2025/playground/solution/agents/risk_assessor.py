"""
Risk Assessment Agent — usa un LLM (Anthropic/OpenRouter) per classificare ogni cittadino
come 0 (monitoraggio standard) o 1 (supporto preventivo attivo).

Strategie disponibili:
  - "llm"       : solo LLM (più accurato, più costoso)
  - "heuristic" : solo regole euristiche (veloce, zero API)
  - "hybrid"    : LLM + fallback euristico se la confidenza LLM è bassa
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.openrouter_client import OpenRouterClient

# ---------------------------------------------------------------------------
# Schema output strutturato
# ---------------------------------------------------------------------------


class RiskAssessment(BaseModel):
    citizen_id: str = Field(description="Identificativo del cittadino")
    risk_label: int = Field(
        description="0=monitoraggio standard, 1=supporto preventivo", ge=0, le=1
    )
    confidence: float = Field(
        description="Confidenza della predizione tra 0.0 e 1.0", ge=0.0, le=1.0
    )
    reasoning: str = Field(description="Motivazione sintetica della classificazione")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Sei The Eye, un sistema di intelligenza artificiale per la prevenzione proattiva \
del benessere nell'ecosistema digitale MirrorLife.

Il tuo compito è analizzare il profilo di un cittadino e determinare se il suo \
attuale percorso di salute richiede l'attivazione di un supporto preventivo \
personalizzato.

CRITERI DI CLASSIFICAZIONE:
- Classifica come 1 (supporto preventivo) se rilevi UNO O PIÙ di questi segnali:
  * Indici di attività fisica o qualità del sonno cronicamente bassi (< 40/100)
  * Trend in peggioramento per attività fisica o sonno
  * Mobilità molto ridotta combinata con isolamento sociale
  * Età avanzata (> 80 anni) con fattori di rischio aggiuntivi
  * Interruzione di routine consolidate
  * Comportamenti a rischio (stress, dieta scorretta, evitamento medico)

- Classifica come 0 (monitoraggio standard) se:
  * Gli indici sono nella norma o in miglioramento
  * Il profilo è stabile e non presenta segnali di allarme

IMPORTANTE: preferisci ridurre i falsi negativi (missed prevention) piuttosto \
che i falsi positivi. Un supporto preventivo non necessario è meno costoso di \
un'opportunità di prevenzione mancata.
"""

HUMAN_PROMPT = """\
Analizza il seguente profilo del cittadino e fornisci la tua classificazione.

=== DATI ANAGRAFICI ===
- Citizen ID: {citizen_id}
- Età: {age} anni
- Occupazione: {job}
- Pensionato: {is_retired}

=== SEGNALI DI BENESSERE (da status.csv) ===
- Numero di eventi monitorati: {n_events}
- Physical Activity Index medio: {mean_physical_activity}/100
- Sleep Quality Index medio: {mean_sleep_quality}/100
- Environmental Exposure Level medio: {mean_env_exposure}/100
- Trend attività fisica (positivo=miglioramento): {trend_physical_activity}
- Trend qualità del sonno (positivo=miglioramento): {trend_sleep_quality}
- Variabilità attività fisica (std): {std_physical_activity}
- Variabilità qualità del sonno (std): {std_sleep_quality}
- Media giorni tra un evento e il successivo: {mean_days_between_events}
- % check-up routine: {pct_routine_checkup}
- % screening preventivo: {pct_preventive_screening}
- % sessioni coaching: {pct_lifestyle_coaching}

=== MOBILITÀ E PATTERN GEOGRAFICI (da locations.json) ===
- Raggio di girazione (mobilità): {radius_of_gyration_km} km
- Città visitate: {unique_cities_visited}
- Giorni senza spostamenti GPS: {days_without_movement}
- Distanza media dalla residenza: {mean_dist_from_home_km} km
- Distanza massima dalla residenza: {max_dist_from_home_km} km

=== PROFILO COMPORTAMENTALE ===
{persona}

=== SCORE EURISTICO DI RISCHIO ===
Punteggio pre-calcolato: {heuristic_risk_score}/100

Fornisci la tua classificazione (0 o 1), la confidenza e una breve motivazione.
"""


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _build_llm() -> Any:
    # Priorita a OpenRouter se e presente la chiave dedicata.
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_api_key:
        return OpenRouterClient()

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        return ChatAnthropic(
            model="claude-haiku-4-5-20251001",  # Haiku: veloce ed economico per inferenza massiva
            api_key=anthropic_api_key,
            temperature=0,  # deterministico
            max_tokens=512,
        )

    raise EnvironmentError(
        "Nessuna API key LLM trovata. Imposta OPENROUTER_API_KEY (consigliato) "
        "oppure ANTHROPIC_API_KEY nel file .env."
    )


# ---------------------------------------------------------------------------
# Assessment functions
# ---------------------------------------------------------------------------


def assess_with_llm(features: dict, persona: str, llm: Any) -> RiskAssessment:
    """Chiama il LLM per classificare un singolo cittadino."""
    if isinstance(llm, OpenRouterClient):
        return _assess_with_openrouter(features, persona, llm)

    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
    )
    chain = prompt | llm.with_structured_output(RiskAssessment)

    result = chain.invoke(
        {
            **features,
            "persona": persona
            if persona
            else "Profilo comportamentale non disponibile.",
        }
    )
    return result


def _assess_with_openrouter(
    features: dict, persona: str, llm: OpenRouterClient
) -> RiskAssessment:
    """Chiama OpenRouter e converte la risposta in RiskAssessment."""
    user_prompt = HUMAN_PROMPT.format(
        **features,
        persona=persona if persona else "Profilo comportamentale non disponibile.",
    )
    user_prompt += (
        "\n\nRispondi SOLO in JSON valido con questi campi: "
        "citizen_id (string), risk_label (0 o 1), confidence (0..1), reasoning (string)."
    )

    response = llm.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        temperature=0,
        max_tokens=512,
    )

    if response.get("error"):
        raise RuntimeError(response["error"])

    content = response.get("content") or ""
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("Risposta OpenRouter non contiene JSON valido")

    parsed = json.loads(content[start:end])
    parsed["citizen_id"] = parsed.get("citizen_id") or features["citizen_id"]

    return RiskAssessment(**parsed)


def assess_with_heuristic(features: dict) -> RiskAssessment:
    """
    Classificazione euristica pura (nessuna chiamata API).
    Threshold = 35/100 sullo score euristico.
    """
    score = features["heuristic_risk_score"]
    label = 1 if score >= 35 else 0
    confidence = min(abs(score - 35) / 65 + 0.5, 1.0)

    reasons = []
    if features["mean_physical_activity"] < 40:
        reasons.append(
            f"bassa attività fisica ({features['mean_physical_activity']}/100)"
        )
    if features["mean_sleep_quality"] < 50:
        reasons.append(
            f"bassa qualità del sonno ({features['mean_sleep_quality']}/100)"
        )
    if features["trend_physical_activity"] < -0.05:
        reasons.append("trend negativo dell'attività fisica")
    if features["days_without_movement"] > 150:
        reasons.append(
            f"elevato isolamento ({features['days_without_movement']} giorni senza GPS)"
        )
    if features["age"] and features["age"] >= 80:
        reasons.append(f"età avanzata ({features['age']} anni)")

    if not reasons:
        reasoning = "Nessun segnale di rischio significativo rilevato."
    else:
        action = (
            "Attivazione percorso preventivo" if label == 1 else "Monitoraggio standard"
        )
        reasoning = f"{action}: {'; '.join(reasons)}. Score euristico: {score}/100."

    return RiskAssessment(
        citizen_id=features["citizen_id"],
        risk_label=label,
        confidence=round(confidence, 2),
        reasoning=reasoning,
    )


def assess_citizen(
    features: dict,
    persona: str,
    strategy: Literal["llm", "heuristic", "hybrid"] = "hybrid",
    llm: Any | None = None,
    confidence_threshold: float = 0.70,
) -> RiskAssessment:
    """
    Valuta un cittadino con la strategia scelta.

    Parameters
    ----------
    features            : dict da feature_engineer.build_citizen_features()
    persona             : testo dalla sezione personas.md
    strategy            : "llm" | "heuristic" | "hybrid"
    llm                 : istanza chat model LangChain (richiesta per strategie llm/hybrid)
    confidence_threshold: soglia sotto la quale il fallback euristico viene usato in hybrid
    """
    if strategy == "heuristic":
        return assess_with_heuristic(features)

    if strategy == "llm":
        if llm is None:
            llm = _build_llm()
        return assess_with_llm(features, persona, llm)

    # strategy == "hybrid"
    heuristic_result = assess_with_heuristic(features)

    # Se l'euristica è molto sicura, non chiamiamo il LLM (risparmio di costi)
    if heuristic_result.confidence >= confidence_threshold:
        return heuristic_result

    # Altrimenti affiniamo con il LLM
    if llm is None:
        llm = _build_llm()
    try:
        llm_result = assess_with_llm(features, persona, llm)
        # In caso di conflitto, vince il LLM (più contesto)
        return llm_result
    except Exception as e:
        print(f"[WARN] LLM fallito per {features['citizen_id']}: {e}. Uso euristica.")
        return heuristic_result


def assess_all_citizens(
    all_features: list[dict],
    personas: dict[str, str],
    strategy: Literal["llm", "heuristic", "hybrid"] = "hybrid",
) -> list[RiskAssessment]:
    """
    Valuta tutti i cittadini e restituisce la lista di RiskAssessment.

    Parameters
    ----------
    all_features : lista da feature_engineer.build_all_features()
    personas     : dizionario {citizen_id: profilo_narrativo}
    strategy     : "llm" | "heuristic" | "hybrid"
    """
    llm = None
    if strategy in ("llm", "hybrid"):
        try:
            llm = _build_llm()
            if isinstance(llm, OpenRouterClient):
                print(f"[Langfuse] Session ID per submission: {llm.get_session_id()}")
        except EnvironmentError as e:
            print(f"[WARN] {e}")
            print("[WARN] Fallback automatico alla strategia 'heuristic'.")
            strategy = "heuristic"

    results: list[RiskAssessment] = []
    for features in all_features:
        cid = features["citizen_id"]
        persona = personas.get(cid, "")
        assessment = assess_citizen(features, persona, strategy=strategy, llm=llm)
        print(
            f"  [{cid}] label={assessment.risk_label} "
            f"conf={assessment.confidence:.2f} | {assessment.reasoning[:80]}..."
        )
        results.append(assessment)

    if isinstance(llm, OpenRouterClient):
        llm.flush()

    return results
