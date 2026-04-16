"""
Population Supervisor Agent — meta-agente che ragiona sull'intera popolazione.

Comportamento agentico:
1. Riceve tutti gli assessment individuali prodotti dai Citizen Analyst
2. Usa tool per accedere ai dati aggregati della popolazione
3. Applica ragionamento di secondo livello:
   - Rivede i casi borderline alla luce del contesto collettivo
   - Verifica consistenza interna (es: due cittadini molto simili, classificazioni diverse)
   - Aggiusta soglie se la popolazione è sistematicamente atipica
4. Decide quali cittadini richiedono una seconda analisi
5. Emette la classificazione finale

Questo livello non può emergere da un sistema deterministico:
richiede comprensione del contesto di popolazione, non solo del singolo.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from agents.tools import SUPERVISOR_TOOLS


# ---------------------------------------------------------------------------
# Schema output
# ---------------------------------------------------------------------------

class SupervisorDecision(BaseModel):
    final_citizens_at_risk: list[str] = Field(
        description="Lista definitiva di CitizenID che necessitano supporto preventivo"
    )
    citizens_to_reanalyze: list[str] = Field(
        default_factory=list,
        description="CitizenID borderline che il supervisor richiede vengano rianalizzati"
    )
    revised_labels: list[dict] = Field(
        default_factory=list,
        description="Revisioni apportate dal supervisor: [{citizen_id, old_label, new_label, reason}]"
    )
    population_reasoning: str = Field(
        description="Spiegazione del ragionamento a livello di popolazione"
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM_PROMPT = """\
You are the Population Health Supervisor in the MirrorLife prevention system.
You have received individual risk assessments from citizen analyst agents.
Your task is to apply population-level reasoning to validate, revise, and finalize those assessments.

## Your Responsibilities

1. **Consistency Check**: Look for contradictions.
   - Two citizens with similar profiles but different labels? Investigate.
   - A young, active citizen flagged as high-risk? Verify why.

2. **Population Context**: Use get_population_overview to understand the baseline.
   - If 80% of citizens are elderly, the threshold should account for that.
   - If the population average physical activity is low, a "low" individual score
     may still be within the norm.

3. **Borderline Revision**: Identify citizens on the edge.
   - Confidence < 0.65 = borderline, worth a second look.
   - You may revise a label if population data justifies it.
   - You may flag a citizen for full re-analysis by adding them to citizens_to_reanalyze.

4. **Final Decision**: Produce the definitive list.

## Available Tools
- get_population_overview: overall stats across all citizens
- get_status_history: drill into a specific citizen's timeline
- compare_to_population: check a specific citizen's z-scores
- get_demographics: verify age/job context for a specific citizen

## Output Format
When your analysis is complete, output EXACTLY this JSON:
```json
{
  "final_citizens_at_risk": ["ID1", "ID2"],
  "citizens_to_reanalyze": [],
  "revised_labels": [
    {"citizen_id": "XXX", "old_label": 0, "new_label": 1, "reason": "..."}
  ],
  "population_reasoning": "Summary of your population-level thinking."
}
```
"""

_SUPERVISOR_TASK_TEMPLATE = """\
Review the following individual citizen risk assessments and apply population-level reasoning.

## Individual Assessments
{assessments_text}

## Your Task
1. Use get_population_overview to understand the population baseline.
2. Identify any inconsistencies or borderline cases.
3. Revise labels where population context justifies it.
4. Produce the final JSON with your definitive decisions.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_assessments(assessments: dict[str, dict]) -> str:
    """Formatta gli assessment individuali come testo leggibile dall'LLM."""
    lines = []
    for cid, a in assessments.items():
        label_str = "PREVENTIVE [1]" if a.get("risk_label") == 1 else "STANDARD [0]"
        conf = a.get("confidence", 0.0)
        findings = "; ".join(a.get("key_findings", []))
        reasoning = a.get("reasoning", "")[:150]
        lines.append(
            f"- {cid}: {label_str} (confidence={conf:.2f})\n"
            f"  Findings: {findings}\n"
            f"  Reasoning: {reasoning}"
        )
    return "\n".join(lines)


def _extract_json(text: str) -> dict | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None


def _parse_supervisor_decision(
    raw_text: str, fallback_at_risk: list[str]
) -> SupervisorDecision:
    """Converte l'output testuale del supervisor in SupervisorDecision."""
    data = _extract_json(raw_text)

    if data:
        try:
            data.setdefault("citizens_to_reanalyze", [])
            data.setdefault("revised_labels", [])
            data.setdefault("population_reasoning", raw_text[:300])
            return SupervisorDecision(**data)
        except Exception:
            pass

    # Fallback conservativo: mantiene gli assessment originali
    return SupervisorDecision(
        final_citizens_at_risk=fallback_at_risk,
        citizens_to_reanalyze=[],
        revised_labels=[],
        population_reasoning="JSON parsing failed — original individual assessments kept.",
    )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def run_population_review(
    individual_assessments: dict[str, dict],
    llm: ChatOpenAI,
    max_iterations: int = 6,
) -> SupervisorDecision:
    """
    Esegue il ciclo ReAct del Population Supervisor.

    Parameters
    ----------
    individual_assessments : {citizen_id: assessment_dict} da citizen_analyst
    llm                    : ChatOpenAI istanza (da llm_factory.build_llm)
    max_iterations         : limite al loop ReAct (default 6)
    """
    # Lista originale da usare come fallback
    original_at_risk = [
        cid for cid, a in individual_assessments.items()
        if a.get("risk_label") == 1
    ]

    assessments_text = _format_assessments(individual_assessments)
    task = _SUPERVISOR_TASK_TEMPLATE.format(assessments_text=assessments_text)

    agent = create_react_agent(
        model=llm,
        tools=SUPERVISOR_TOOLS,
        prompt=SUPERVISOR_SYSTEM_PROMPT,
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content=task)]},
        config={"recursion_limit": max_iterations * 2},
    )

    final_message = result["messages"][-1].content
    decision = _parse_supervisor_decision(final_message, original_at_risk)

    # Log
    tool_calls = [
        m.name for m in result["messages"]
        if hasattr(m, "name") and m.name is not None
    ]
    print(f"    [Supervisor] Tools used: {tool_calls}")
    print(f"    [Supervisor] Final at-risk: {decision.final_citizens_at_risk}")
    if decision.revised_labels:
        for rev in decision.revised_labels:
            print(
                f"    [Supervisor] REVISED {rev['citizen_id']}: "
                f"{rev['old_label']} → {rev['new_label']} | {rev['reason'][:60]}"
            )
    if decision.citizens_to_reanalyze:
        print(f"    [Supervisor] Requesting re-analysis for: {decision.citizens_to_reanalyze}")

    return decision
