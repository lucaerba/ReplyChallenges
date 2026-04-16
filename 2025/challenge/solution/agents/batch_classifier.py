"""
Batch Classifier — classificazione LLM senza ReAct loop.

Formato COMPATTO: input ~80 char/tx, output una riga/tx.
Riduce i token di 5-6x rispetto al formato verboso precedente.

Flusso:
  fast_scanner → TxSignals (pre-calcolati)
    → build_compact_prompt(signals)   ← ~80 char/tx invece di ~400
    → llm.invoke(prompt)              ← UNA singola chiamata LLM per batch
    → parse_compact_verdicts()        ← parsing righe "ID: FRAUD/LEGIT"
    → [TransactionAssessment]
"""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agents.llm_factory import invoke_with_langfuse

if TYPE_CHECKING:
    from agents.fast_scanner import TxSignals

logger = logging.getLogger("classifier")

BATCH_SIZE = 20   # default, override via orchestratore


# ---------------------------------------------------------------------------
# Schema output
# ---------------------------------------------------------------------------

class TransactionAssessment(BaseModel):
    transaction_id: str
    is_fraud: bool
    confidence: float = Field(ge=0.0, le=1.0)
    fraud_signals: list[str] = Field(default_factory=list)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Prompt COMPATTO
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Fraud analyst for MirrorPay. Classify each transaction as FRAUD or LEGIT.

Rules:
- POST_PHISHING + any other signal → FRAUD
- AMOUNT_HIGH + (POST_PHISHING or NEW_COUNTERPART) → FRAUD
- AMOUNT_HIGH alone, non-recurring → FRAUD if amount > 3x mean
- NEW_COUNTERPART alone or UNUSUAL_HOUR alone → LEGIT (borderline, default legit)
- POST_PHISHING alone → LEGIT
- No signals → LEGIT

Output exactly one line per transaction, nothing else:
<transaction_id>: FRAUD
<transaction_id>: LEGIT
"""


def _build_compact_prompt(batch: "list[TxSignals]") -> str:
    """Formato ultra-compatto: ~80 char/tx invece di ~400."""
    lines = [f"Classify {len(batch)} transactions:\n"]
    for sig in batch:
        signals_str = ", ".join(sig.signals) if sig.signals else "none"
        recurring_str = "recurring" if sig.is_recurring else "non-recurring"
        lines.append(
            f"{sig.transaction_id}: {sig.transaction_type} €{sig.amount:.0f} "
            f"| {recurring_str} | signals: {signals_str}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing righe "ID: FRAUD/LEGIT"
# ---------------------------------------------------------------------------

def _parse_compact_verdicts(
    batch: "list[TxSignals]", raw_text: str
) -> list[TransactionAssessment]:
    results: list[TransactionAssessment] = []
    seen: set[str] = set()
    valid_ids = {s.transaction_id for s in batch}
    signals_by_id = {s.transaction_id: s.signals for s in batch}

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Cerca pattern: "<uuid>: FRAUD" o "<uuid>: LEGIT"
        m = re.match(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
            r"[:\s]+\**(FRAUD|LEGIT)\**",
            line, re.IGNORECASE
        )
        if not m:
            continue
        tx_id, verdict = m.group(1), m.group(2).upper()
        if tx_id not in valid_ids or tx_id in seen:
            continue
        is_fraud = verdict == "FRAUD"
        confidence = 0.90 if is_fraud else 0.88
        results.append(TransactionAssessment(
            transaction_id=tx_id,
            is_fraud=is_fraud,
            confidence=confidence,
            fraud_signals=signals_by_id.get(tx_id, []) if is_fraud else [],
        ))
        seen.add(tx_id)

    # Fallback per transazioni mancanti nell'output
    for sig in batch:
        if sig.transaction_id not in seen:
            is_fraud = sig.risk_score >= 4
            results.append(TransactionAssessment(
                transaction_id=sig.transaction_id,
                is_fraud=is_fraud,
                confidence=0.50,
                fraud_signals=[f"FALLBACK(score={sig.risk_score})"] + sig.signals,
                reasoning="LLM output parsing failed; using deterministic signal score.",
            ))
            logger.debug(f"Fallback used for {sig.transaction_id} (score={sig.risk_score})")

    return results


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def classify_batch(
    batch: "list[TxSignals]",
    llm: ChatOpenAI,
    session_id: str = "",
) -> list[TransactionAssessment]:
    """
    Classifica un batch di transazioni in UNA SINGOLA chiamata LLM (no ReAct, no tools).
    Usa formato compatto per minimizzare i token.
    """
    if not batch:
        return []

    batch_tx_ids = [b.transaction_id for b in batch]
    prompt = _build_compact_prompt(batch)
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    logger.info(
        "  [DBG] invoke_start | tx=%s | prompt_chars=%d",
        ",".join(t[:8] for t in batch_tx_ids),
        len(prompt),
    )
    t0 = time.perf_counter()
    try:
        response = invoke_with_langfuse(llm, messages, session_id=session_id)
    except Exception as exc:
        logger.exception(
            "  [DBG] invoke_error | tx=%s | err=%s",
            ",".join(t[:8] for t in batch_tx_ids),
            str(exc),
        )
        raise
    elapsed = time.perf_counter() - t0

    token_usage = {}
    if hasattr(response, "response_metadata") and isinstance(response.response_metadata, dict):
        token_usage = response.response_metadata.get("token_usage", {}) or {}
    logger.info(
        "  [DBG] invoke_end   | tx=%s | elapsed=%.2fs | response_chars=%d | tokens=%s",
        ",".join(t[:8] for t in batch_tx_ids),
        elapsed,
        len(getattr(response, "content", "") or ""),
        token_usage,
    )

    assessments = _parse_compact_verdicts(batch, response.content)
    assessed_ids = {a.transaction_id for a in assessments}
    missing_ids = [tx_id for tx_id in batch_tx_ids if tx_id not in assessed_ids]
    if missing_ids:
        logger.warning(
            "  [DBG] parse_missing | missing_tx=%s",
            ",".join(t[:8] for t in missing_ids),
        )

    fraud = [a for a in assessments if a.is_fraud]
    logger.info(
        f"  batch {len(batch)} tx | {len(fraud)} fraud | "
        f"{elapsed:.1f}s | parse_ok={len(assessments)}/{len(batch)}"
    )
    return assessments
