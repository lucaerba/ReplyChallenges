"""
Citizen Analyst Agent — agente ReAct per l'analisi individuale di un singolo cittadino.

Comportamento agentico:
1. Riceve solo il citizen_id — NON un contesto pre-calcolato
2. Decide autonomamente quali tool invocare e in quale ordine
3. Itera finché non ha abbastanza evidenza (criterio di arresto interno)
4. Produce un JSON strutturato come output finale

Questo è il cuore dell'approccio agentico: l'LLM guida l'investigazione,
non esegue una classificazione passiva su feature pre-digerite.
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from agents.tools import CITIZEN_TOOLS


# ---------------------------------------------------------------------------
# Schema output
# ---------------------------------------------------------------------------

class CitizenAssessment(BaseModel):
    citizen_id: str = Field(description="Identificativo del cittadino")
    risk_label: int = Field(description="0=monitoraggio standard, 1=supporto preventivo", ge=0, le=1)
    confidence: float = Field(description="Confidenza tra 0.0 e 1.0", ge=0.0, le=1.0)
    key_findings: list[str] = Field(description="Lista dei segnali chiave trovati")
    reasoning: str = Field(description="Motivazione della classificazione")


# ---------------------------------------------------------------------------
# System prompt — guida il ciclo ReAct dell'agente
# ---------------------------------------------------------------------------

ANALYST_SYSTEM_PROMPT = """\
You are a citizen health analyst in the MirrorLife prevention system (year 2087).
Your role is to determine if a citizen needs preventive support (label=1) or standard monitoring (label=0).

## Investigation Protocol
You MUST use the available tools to investigate the citizen before making any decision.
Do NOT guess based on the citizen ID alone.

Recommended investigation sequence:
1. get_demographics → understand who this person is (age, job, lifestyle)
2. get_status_history → get the health monitoring timeline
3. compute_metric_trend → check if physical activity or sleep is declining
4. get_mobility_summary → detect isolation or mobility reduction
5. compare_to_population → contextualize relative to peers (optional)

Stop investigating when you have enough evidence to classify with confidence.

## Classification Criteria
Classify as 1 (PREVENTIVE SUPPORT NEEDED) if you detect ANY of:
- Physical Activity Index chronically below 40/100
- Sleep Quality Index chronically below 40/100
- DECLINING trend in physical activity or sleep over multiple events
- Radius of gyration < 2 km combined with behavioral isolation signals
- Age > 80 with additional risk factors (declining trends, isolation)
- Behavioral profile showing deterioration (cancelled plans, avoidance, poor diet)

Classify as 0 (STANDARD MONITORING) if:
- Metrics are stable and within acceptable range
- No significant declining trends
- Mobility and social engagement are maintained

## Output Format
When you have sufficient evidence, output EXACTLY this JSON (and nothing else after it):
```json
{
  "citizen_id": "XXXXXXXX",
  "risk_label": 0,
  "confidence": 0.85,
  "key_findings": ["finding 1", "finding 2"],
  "reasoning": "Brief explanation of the classification decision."
}
```
"""

_TASK_TEMPLATE = (
    "Investigate citizen {citizen_id} and determine if they need preventive health support. "
    "Use the available tools to gather evidence, then provide your final JSON assessment."
)

# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | None:
    """Estrae il primo oggetto JSON valido da un testo libero."""
    # 1. Prova con blocco ```json ... ```
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Prova con primo { ... } nel testo
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _parse_assessment(citizen_id: str, raw_text: str) -> CitizenAssessment:
    """Converte l'output testuale del LLM in CitizenAssessment."""
    data = _extract_json(raw_text)

    if data:
        try:
            data.setdefault("citizen_id", citizen_id)
            data.setdefault("key_findings", [])
            data.setdefault("reasoning", raw_text[:200])
            return CitizenAssessment(**data)
        except Exception:
            pass

    # Fallback: cerca parole chiave nel testo
    text_lower = raw_text.lower()
    if any(kw in text_lower for kw in ["risk_label: 1", '"risk_label": 1', "preventive support", "label=1"]):
        label, confidence = 1, 0.60
    elif any(kw in text_lower for kw in ["risk_label: 0", '"risk_label": 0', "standard monitoring", "label=0"]):
        label, confidence = 0, 0.60
    else:
        label, confidence = 0, 0.40  # default conservativo

    return CitizenAssessment(
        citizen_id=citizen_id,
        risk_label=label,
        confidence=confidence,
        key_findings=["JSON parsing failed — text-based fallback used"],
        reasoning=raw_text[:300],
    )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def analyze_citizen(
    citizen_id: str,
    llm: ChatOpenAI,
    max_iterations: int = 8,
) -> CitizenAssessment:
    """
    Esegue il ciclo ReAct per un singolo cittadino.

    L'agente decide autonomamente:
    - quali tool invocare
    - in quale ordine
    - quando ha abbastanza evidenza per classificare

    Parameters
    ----------
    citizen_id     : ID del cittadino da analizzare
    llm            : ChatOpenAI istanza (da llm_factory.build_llm)
    max_iterations : limite di sicurezza al loop (default 8 tool calls)
    """
    agent = create_react_agent(
        model=llm,
        tools=CITIZEN_TOOLS,
        prompt=ANALYST_SYSTEM_PROMPT,
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content=_TASK_TEMPLATE.format(citizen_id=citizen_id))]},
        config={"recursion_limit": max_iterations * 2},
    )

    # L'ultimo messaggio contiene la risposta finale dell'agente
    final_message = result["messages"][-1].content
    assessment = _parse_assessment(citizen_id, final_message)

    # Log intermediary tool calls per debug
    tool_calls_made = [
        m.name for m in result["messages"]
        if hasattr(m, "name") and m.name is not None
    ]
    print(
        f"    [{citizen_id}] Tools used: {tool_calls_made} → "
        f"label={assessment.risk_label} conf={assessment.confidence:.2f}"
    )

    return assessment
