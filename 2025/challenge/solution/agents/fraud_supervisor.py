"""
Fraud Supervisor Agent — meta-agente che rivede tutti gli assessment individuali.

Comportamento:
1. Riceve tutti gli assessment delle singole transazioni
2. Usa tool per accedere a dati aggregati della popolazione
3. Applica ragionamento di secondo livello:
   - Controlla consistenza (es: transazione A marcata fraud ma transazione B identica no)
   - Verifica falsi positivi (es: regolare pagamento mensile marcato fraud per errore)
   - Cerca pattern di frode cross-transazione (es: più transazioni fraudolente allo stesso merchant)
4. Produce la lista finale di transazioni fraudolente
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from agents.llm_factory import invoke_with_langfuse
from agents.tools import SUPERVISOR_TOOLS


# ---------------------------------------------------------------------------
# Schema output
# ---------------------------------------------------------------------------

class SupervisorDecision(BaseModel):
    final_fraud_transactions: list[str] = Field(
        description="Lista definitiva di transaction_id fraudolenti"
    )
    transactions_to_reanalyze: list[str] = Field(
        default_factory=list,
        description="Transaction ID borderline da rianalizzare"
    )
    revised_verdicts: list[dict] = Field(
        default_factory=list,
        description="Revisioni: [{transaction_id, old_verdict, new_verdict, reason}]"
    )
    population_reasoning: str = Field(
        description="Spiegazione del ragionamento a livello di popolazione"
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM_PROMPT = """\
You are the Chief Fraud Supervisor for MirrorPay (Reply Mirror, 2087).
You have received individual fraud assessments for every transaction in the dataset.
Your job is to apply population-level reasoning to validate and finalize those assessments.

## Your Responsibilities

1. **Consistency Check**: Look for contradictions.
   - Same user, same merchant, similar amount: one labeled fraud and one legit? Investigate.
   - Regular monthly recurring transaction (salary, rent) labeled fraud? Likely a false positive.

2. **Cross-transaction Patterns**: Look for systemic fraud.
   - Multiple transactions flagged with IBAN changes → confirms account hijacking.
   - Phishing SMS followed by unusual transaction → strong fraud signal.
   - Single merchant with multiple IBAN changes → merchant impersonation.

3. **False Positive Reduction**:
   - Monthly salary (same employer, similar amount, monthly cadence) → NOT fraud.
   - Monthly rent (same landlord, similar amount) → NOT fraud unless IBAN changed.
   - Small recurring subscriptions (same merchant, small amount) → NOT fraud.

4. **Borderline Review**: confidence < 0.70 = borderline.
   - Add to transactions_to_reanalyze if more investigation is needed.
   - Revise if population context justifies it.

5. **Final Decision**: Produce the definitive fraud list.

## Available Tools
- get_population_overview: global stats, all merchants with IBAN inconsistencies
- list_all_transactions: overview of all transactions
- get_transaction_details: drill into a specific transaction
- check_iban_consistency: check IBAN patterns for a specific entity
- check_transaction_anomaly: re-run anomaly detection on any transaction
- get_suspicious_communications: check phishing/social engineering for any user

## Output Format
```json
{
  "final_fraud_transactions": ["tx-id-1", "tx-id-2"],
  "transactions_to_reanalyze": [],
  "revised_verdicts": [
    {"transaction_id": "xxx", "old_verdict": true, "new_verdict": false, "reason": "..."}
  ],
  "population_reasoning": "Summary of population-level fraud analysis."
}
```
"""

_SUPERVISOR_TASK = """\
Review the following individual transaction fraud assessments.
Apply population-level reasoning to validate and produce the final fraud list.

## Individual Assessments
{assessments_text}

## Your Task
1. Use get_population_overview to understand the overall picture.
2. Check for consistency errors and false positives.
3. Look for cross-transaction fraud patterns.
4. Produce the final JSON with your definitive fraud list.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_assessments(assessments: dict[str, dict]) -> str:
    lines = []
    for tx_id, a in assessments.items():
        verdict = "FRAUD ⚠" if a.get("is_fraud") else "LEGIT ✓"
        conf = a.get("confidence", 0.0)
        signals = "; ".join(a.get("fraud_signals", []))
        reasoning = a.get("reasoning", "")[:120]
        lines.append(
            f"- {tx_id}: {verdict} (confidence={conf:.2f})\n"
            f"  Signals: {signals or '(none)'}\n"
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


def _parse_decision(
    raw_text: str, fallback_fraud: list[str]
) -> SupervisorDecision:
    data = _extract_json(raw_text)
    if data:
        try:
            data.setdefault("transactions_to_reanalyze", [])
            data.setdefault("revised_verdicts", [])
            data.setdefault("population_reasoning", raw_text[:300])
            return SupervisorDecision(**data)
        except Exception:
            pass

    return SupervisorDecision(
        final_fraud_transactions=fallback_fraud,
        transactions_to_reanalyze=[],
        revised_verdicts=[],
        population_reasoning="JSON parsing failed — individual assessments kept as-is.",
    )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def run_fraud_review(
    individual_assessments: dict[str, dict],
    llm: ChatOpenAI,
    session_id: str = "",
    max_iterations: int = 8,
) -> SupervisorDecision:
    """
    Esegue la revisione del supervisor.

    Parameters
    ----------
    individual_assessments : {transaction_id: assessment_dict}
    llm                    : ChatOpenAI istanza
    session_id             : Langfuse session ID
    max_iterations         : limite al loop ReAct
    """
    fallback_fraud = [
        tx_id for tx_id, a in individual_assessments.items()
        if a.get("is_fraud") is True
    ]

    assessments_text = _format_assessments(individual_assessments)
    task = _SUPERVISOR_TASK.format(assessments_text=assessments_text)

    agent = create_react_agent(
        model=llm,
        tools=SUPERVISOR_TOOLS,
        prompt=SUPERVISOR_SYSTEM_PROMPT,
    )

    result = invoke_with_langfuse(
        agent,
        {"messages": [HumanMessage(content=task)]},
        session_id=session_id,
        extra_config={"recursion_limit": max_iterations * 2},
    )

    final_message = result["messages"][-1].content
    decision = _parse_decision(final_message, fallback_fraud)

    tool_calls = [m.name for m in result["messages"] if hasattr(m, "name") and m.name]
    print(f"    [Supervisor] Tools: {tool_calls}")
    print(f"    [Supervisor] Final fraud list ({len(decision.final_fraud_transactions)}): "
          f"{decision.final_fraud_transactions}")
    if decision.revised_verdicts:
        for rev in decision.revised_verdicts:
            print(
                f"    [Supervisor] REVISED {rev.get('transaction_id', '?')[:16]}...: "
                f"{rev.get('old_verdict')} → {rev.get('new_verdict')} | "
                f"{str(rev.get('reason', ''))[:60]}"
            )
    if decision.transactions_to_reanalyze:
        print(f"    [Supervisor] Requesting re-analysis: {decision.transactions_to_reanalyze}")

    return decision
