"""
Transaction Analyst Agent — analisi di un BATCH di transazioni in una singola chiamata LLM.

Invece di una chiamata per transazione, l'agente riceve un gruppo di N transazioni,
usa i tool per raccogliere il contesto necessario (patterns utente, IBAN consistency,
comunicazioni sospette) e produce un JSON array con un verdetto per ognuna.

Vantaggi:
- Da O(n) chiamate LLM a O(n/BATCH_SIZE) → ~15x più veloce con batch=15
- Scalabile a migliaia di transazioni
- L'agente può riusare il contesto (es. patterns utente) per più transazioni dello stesso user
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from agents.tools import ANALYST_TOOLS

BATCH_SIZE = 15  # transazioni per chiamata LLM (override via orchestratore)


# ---------------------------------------------------------------------------
# Schema output
# ---------------------------------------------------------------------------

class TransactionAssessment(BaseModel):
    transaction_id: str
    is_fraud: bool
    confidence: float = Field(ge=0.0, le=1.0)
    fraud_signals: list[str] = Field(default_factory=list)
    reasoning: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

ANALYST_SYSTEM_PROMPT = """\
You are a financial fraud analyst for MirrorPay (Reply Mirror, year 2087).
You will receive a BATCH of transaction IDs to analyze together in one pass.

## Efficient Investigation Strategy
Analyze the batch systematically to share context across transactions:

1. For each UNIQUE SENDER in the batch:
   - analyze_user_patterns(sender_id)       → their normal spending behavior
   - get_suspicious_communications(sender_id) → phishing/social engineering attacks

2. For each UNIQUE RECIPIENT in the batch:
   - check_iban_consistency(recipient_id)   → flag if IBAN changed across transactions

3. For individual transactions that look suspicious after step 1-2:
   - check_transaction_anomaly(transaction_id) → statistical anomaly vs baseline
   - get_transaction_details(transaction_id)   → full details if needed

You do NOT need to investigate obviously recurring legitimate transactions
(monthly salary, monthly rent to the same landlord with consistent IBAN).

## Fraud Signals — classify as FRAUD if any present:
- Recipient IBAN changed vs EARLIER transactions with same entity: the LATER transaction
  (the one using the NEW/different IBAN) is the fraudulent one, NOT the first/earlier one
- Transaction occurs shortly after a phishing SMS/email targeting the sender
- Amount > 2.5x the user's historical mean for that transaction type
- New unknown counterpart + suspicious amount or type combination
- In-person payment at geographically inconsistent location

## Legitimate Signals — classify as LEGIT:
- Regular recurring pattern (monthly salary/rent, same amount range, same IBAN)
- Known stable counterpart with consistent IBAN, no surrounding phishing signals
- Small daily-life purchases from known merchants

## Output Format
After investigating, output EXACTLY a JSON array — one object per transaction in the batch:
```json
[
  {
    "transaction_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "is_fraud": false,
    "confidence": 0.95,
    "fraud_signals": [],
    "reasoning": "Regular monthly salary, consistent IBAN, no phishing signals."
  },
  {
    "transaction_id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "is_fraud": true,
    "confidence": 0.92,
    "fraud_signals": ["Recipient IBAN changed", "Preceded by phishing SMS"],
    "reasoning": "ACCST55537 used a new IBAN; user targeted by PayPal phishing 36 days prior."
  }
]
```

Every transaction in the batch MUST appear in the output array.
"""

_BATCH_TASK_TEMPLATE = """\
Analyze the following {n} transactions for fraud. Use tools to investigate efficiently.

## Transaction IDs to analyze:
{tx_list}

Remember:
- Share investigation context across transactions from the same sender/recipient
- Output a JSON array with exactly {n} verdicts (one per transaction above)
"""


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _extract_json_array(text: str) -> list | None:
    """Estrae il primo JSON array valido dal testo."""
    # Cerca blocco ```json [...] ```
    match = re.search(r"```json\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Cerca primo [ ... ] nel testo
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # Prova a estrarre singolo oggetto JSON e wrapparlo in lista
    match2 = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match2:
        try:
            return [json.loads(match2.group(1))]
        except json.JSONDecodeError:
            pass

    return None


def _parse_batch_assessments(
    tx_ids: list[str], raw_text: str
) -> list[TransactionAssessment]:
    """Converte l'output testuale del LLM in lista di TransactionAssessment."""
    results: list[TransactionAssessment] = []
    data_list = _extract_json_array(raw_text)

    seen_ids: set[str] = set()

    if data_list and isinstance(data_list, list):
        for item in data_list:
            if not isinstance(item, dict):
                continue
            tx_id = item.get("transaction_id", "")
            if tx_id not in tx_ids:
                continue  # ignora ID non richiesti
            try:
                item.setdefault("fraud_signals", [])
                item.setdefault("reasoning", "")
                results.append(TransactionAssessment(**item))
                seen_ids.add(tx_id)
            except Exception:
                pass

    # Fallback per transazioni mancanti nel parsing
    text_lower = raw_text.lower()
    for tx_id in tx_ids:
        if tx_id not in seen_ids:
            # Cerca il tx_id nel testo per capire il verdetto
            idx = text_lower.find(tx_id[:8].lower())
            snippet = text_lower[idx:idx + 200] if idx >= 0 else text_lower[:200]
            is_fraud = "fraud" in snippet and "not fraud" not in snippet
            results.append(TransactionAssessment(
                transaction_id=tx_id,
                is_fraud=is_fraud,
                confidence=0.45,
                fraud_signals=["JSON parsing incomplete — fallback used"],
                reasoning=f"Could not parse verdict from LLM output. Snippet: {snippet[:100]}",
            ))

    return results


# ---------------------------------------------------------------------------
# Main batch function
# ---------------------------------------------------------------------------

def analyze_transaction_batch(
    transaction_ids: list[str],
    llm: ChatOpenAI,
    session_id: str = "",
    max_iterations: int = 20,
) -> list[TransactionAssessment]:
    """
    Analizza un batch di transazioni in una singola chiamata LLM ReAct.

    Parameters
    ----------
    transaction_ids : lista di ID da analizzare insieme
    llm             : ChatOpenAI istanza
    session_id      : Langfuse session ID
    max_iterations  : limite al loop ReAct (più alto per batch grandi)
    """
    if not transaction_ids:
        return []

    agent = create_react_agent(
        model=llm,
        tools=ANALYST_TOOLS,
        prompt=ANALYST_SYSTEM_PROMPT,
    )

    tx_list = "\n".join(f"  - {tx_id}" for tx_id in transaction_ids)
    task = _BATCH_TASK_TEMPLATE.format(
        n=len(transaction_ids),
        tx_list=tx_list,
    )

    result = agent.invoke(
        {"messages": [HumanMessage(content=task)]},
        config={
            "recursion_limit": max_iterations * 2,
            "metadata": {"langfuse_session_id": session_id},
        },
    )

    final_message = result["messages"][-1].content
    assessments = _parse_batch_assessments(transaction_ids, final_message)

    # Log
    tool_calls = [m.name for m in result["messages"] if hasattr(m, "name") and m.name]
    fraud_found = [a for a in assessments if a.is_fraud]
    print(
        f"    [Batch {len(transaction_ids)} tx] "
        f"{len(fraud_found)} fraud found | "
        f"tools used: {len(tool_calls)} calls"
    )
    for a in assessments:
        tag = "FRAUD ⚠" if a.is_fraud else "legit ✓"
        print(f"      {a.transaction_id[:16]}... → {tag} (conf={a.confidence:.2f})")

    return assessments
