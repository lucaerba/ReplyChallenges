"""
Orchestrator — LangGraph StateGraph per il sistema di fraud detection.

Flusso a 3 fasi (scalabile a migliaia di transazioni):

  START
    → load_data
    → fast_scan          [deterministico, O(n), zero LLM] → pre-calcola segnali
    → batch_classify     [LLM senza ReAct, batch_size tx per chiamata]
    → fraud_review       [Supervisor ReAct, solo su candidati fraud/borderline]
    → [conditional edge]
        ┌─ re-analisi borderline se richiesta dal supervisor
        └─ write_output
    → END

Complessità LLM:
  - 1000 tx / batch_size=20 = ~50 chiamate (classify)
  - + 1 chiamata supervisor (solo sui ~5% fraud candidates)
  vs approccio ReAct per-tx: 1000 × ~8 = ~8000 tool call iterations
"""

from __future__ import annotations

import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from agents.batch_classifier import TransactionAssessment, classify_batch
from agents.data_loader import load_all
from agents.fast_scanner import TxSignals, scan_all
from agents.fraud_supervisor import SupervisorDecision, run_fraud_review
from agents.llm_factory import build_llm, generate_session_id
from agents.tools import init_data_store

# ---------------------------------------------------------------------------
# Config (override via .env)
# ---------------------------------------------------------------------------
MAX_REANALYSIS_ROUNDS = int(os.getenv("MAX_REANALYSIS_ROUNDS", "1"))
BATCH_SIZE = int(os.getenv("AGENT_BATCH_SIZE", "20"))
BATCH_DELAY = float(os.getenv("AGENT_CALL_DELAY_SECONDS", "0.5"))
MAX_RATE_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "4"))
BASE_RETRY_WAIT = float(os.getenv("AGENT_RETRY_BACKOFF_SECONDS", "8"))
SUPERVISOR_MAX_ITERATIONS = int(os.getenv("SUPERVISOR_MAX_ITERATIONS", "4"))
SUPERVISOR_FASTPATH_MAX_CANDIDATES = int(os.getenv("SUPERVISOR_FASTPATH_MAX_CANDIDATES", "3"))

# ---------------------------------------------------------------------------
# Logging strutturato
# ---------------------------------------------------------------------------


def _setup_logging() -> logging.Logger:
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )
    # Silenzia log verbosi di librerie terze
    for noisy in ("httpx", "httpcore", "openai", "langchain", "langgraph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger("orchestrator")


log = _setup_logging()


def _phase(msg: str) -> None:
    bar = "─" * 60
    log.info(f"\n{bar}\n  {msg}\n{bar}")


def _progress(current: int, total: int, label: str = "") -> str:
    pct = current / total * 100 if total else 0
    return f"[{current}/{total}] {pct:5.1f}%  {label}"


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


def _is_rate_limit(exc: Exception) -> bool:
    return any(k in str(exc).lower() for k in ("429", "rate limit", "ratelimit"))


def _with_retry(fn: Any, label: str) -> Any:
    attempt = 1
    while True:
        try:
            return fn()
        except Exception as exc:
            if not _is_rate_limit(exc) or attempt >= MAX_RATE_RETRIES:
                raise
            wait = BASE_RETRY_WAIT * (2 ** (attempt - 1))
            log.warning(
                f"Rate-limit on '{label}' — retry {attempt + 1}/{MAX_RATE_RETRIES} in {wait:.0f}s"
            )
            time.sleep(wait)
            attempt += 1


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _is_deterministic_fraud(raw_signal: dict) -> bool:
    """Classifica come FRAUD senza LLM — segnale conclusivo IBAN_CHANGE.

    IBAN_CHANGE da solo è sufficiente: indica account takeover / impersonazione
    merchant. Non serve conferma LLM.
    """
    return any(s.startswith("IBAN_CHANGE") for s in raw_signal.get("signals", []))


def _is_deterministic_legit(raw_signal: dict) -> bool:
    """Salta l'LLM SOLO quando l'esito LEGIT è esplicitamente garantito dalle regole.

    Casi sicuri (dal ruleset della challenge):
      - Nessun segnale
      - POST_PHISHING da solo (phishing senza transazione sospetta — esplicito nelle regole)
      - AMOUNT_HIGH da solo su transazione ricorrente (rata annuale — esplicito nelle regole)

    TUTTO il resto va all'LLM, inclusi:
      - NEW_COUNTERPART da solo (borderline 0.55-0.70, lascia decidere all'LLM)
      - UNUSUAL_HOUR da solo   (borderline 0.55-0.70)
      - POST_PHISHING + QUALUNQUE altro segnale → le regole dicono FRAUD!
    """
    signals = raw_signal.get("signals", [])
    if not signals:
        return True

    signal_types = {s.split(":")[0].strip() for s in signals}

    # POST_PHISHING SOLO → LEGIT (esplicito nelle regole)
    if signal_types == {"POST_PHISHING"}:
        return True

    # AMOUNT_HIGH SOLO su transazione ricorrente → LEGIT (rata annuale)
    if signal_types == {"AMOUNT_HIGH"} and raw_signal.get("is_recurring"):
        return True

    return False


# ---------------------------------------------------------------------------
# Stato condiviso del grafo
# ---------------------------------------------------------------------------


class FraudState(TypedDict):
    data_dir: str
    output_path: str
    session_id: str

    transactions: list[dict]
    transaction_ids: list[str]
    users_by_id: dict

    # Fast scanner output
    tx_signals: dict[str, dict]  # tx_id → TxSignals.asdict()

    # Classifier output
    individual_assessments: dict[str, dict]  # tx_id → TransactionAssessment.dict()

    # Supervisor output
    supervisor_decision: dict
    final_fraud_transactions: list[str]

    reanalysis_round: int
    transactions_to_reanalyze: list[str]


# ---------------------------------------------------------------------------
# Nodo 1 — Caricamento dati
# ---------------------------------------------------------------------------


def node_load_data(state: FraudState) -> dict:
    _phase("FASE 1/4 — DataLoader")
    t0 = time.perf_counter()

    data = load_all(state["data_dir"])
    init_data_store(data)

    session_id = generate_session_id()
    elapsed = time.perf_counter() - t0

    log.info(f"Langfuse Session ID : {session_id}")
    log.info(f"Transactions        : {len(data['transaction_ids'])}")
    log.info(f"Citizens            : {len(data['citizen_ids'])}")
    log.info(f"SMS / Mails         : {len(data['sms'])} / {len(data['mails'])}")
    log.info(f"GPS records         : {len(data['locations'])}")
    log.info(f"Load time           : {elapsed:.2f}s")

    return {
        "transactions": data["transactions"],
        "transaction_ids": data["transaction_ids"],
        "users_by_id": data["users_by_id"],
        "session_id": session_id,
        "tx_signals": {},
        "individual_assessments": {},
        "reanalysis_round": 0,
        "transactions_to_reanalyze": [],
    }


# ---------------------------------------------------------------------------
# Nodo 2 — Fast statistical scan (zero LLM)
# ---------------------------------------------------------------------------


def node_fast_scan(state: FraudState) -> dict:
    _phase("FASE 2/4 — Fast Statistical Scanner (deterministic, no LLM)")
    t0 = time.perf_counter()

    # Ricostruiamo il data dict che serve allo scanner
    data = {
        "transactions": state["transactions"],
        "users_by_id": state["users_by_id"],
        "sms": _store_get("sms"),
        "mails": _store_get("mails"),
    }
    signals_map: dict[str, TxSignals] = scan_all(data)
    elapsed = time.perf_counter() - t0

    # Statistiche
    flagged = [s for s in signals_map.values() if s.signals]
    clean = [s for s in signals_map.values() if not s.signals]
    recurring = [s for s in signals_map.values() if s.is_recurring and not s.signals]

    log.info(f"Scanned             : {len(signals_map)} transactions in {elapsed:.3f}s")
    log.info(
        f"Flagged (any signal): {len(flagged)}  ({len(flagged) / len(signals_map) * 100:.1f}%)"
    )
    log.info(f"Clean (no signals)  : {len(clean)}")
    log.info(f"Recurring OK        : {len(recurring)}")

    if flagged:
        log.info("Flagged transactions:")
        for s in sorted(flagged, key=lambda x: -x.risk_score):
            log.info(
                f"  score={s.risk_score}  {s.transaction_id[:16]}...  "
                f"{s.transaction_type:20s}  €{s.amount:>10.2f}  "
                f"signals={s.signals}"
            )

    # Serializza per il TypedDict (TxSignals non è JSON-serializable natively)
    serialized = {
        tx_id: {
            "signals": sig.signals,
            "risk_score": sig.risk_score,
            "is_recurring": sig.is_recurring,
            "sender_id": sig.sender_id,
            "sender_name": sig.sender_name,
            "amount": sig.amount,
            "transaction_type": sig.transaction_type,
            "llm_text": sig.to_llm_text(),
        }
        for tx_id, sig in signals_map.items()
    }

    return {"tx_signals": serialized}


def _store_get(key: str) -> list:
    """Accede al DataStore globale di tools.py."""
    from agents.tools import _store

    return _store.get(key, [])


# ---------------------------------------------------------------------------
# Nodo 3 — Batch LLM classify (no ReAct, no tools)
# ---------------------------------------------------------------------------


def node_batch_classify(state: FraudState) -> dict:
    tx_ids = state["transaction_ids"]
    session_id = state["session_id"]
    signals_map: dict[str, dict] = state["tx_signals"]
    current_assessments = dict(state.get("individual_assessments", {}))

    # Ricostruiamo i TxSignals dal dict serializzato per passarli al classifier
    from agents.fast_scanner import TxSignals as TS_cls

    signals_objs: dict[str, TxSignals] = {}
    deterministic_legit = 0
    deterministic_fraud = 0
    for tx_id in tx_ids:
        raw = signals_map.get(tx_id)
        if raw:
            if _is_deterministic_fraud(raw):
                # IBAN_CHANGE conclusivo — nessuna conferma LLM necessaria
                current_assessments[tx_id] = {
                    "transaction_id": tx_id,
                    "is_fraud": True,
                    "confidence": 0.97,
                    "fraud_signals": [s for s in raw.get("signals", []) if s.startswith("IBAN_CHANGE")],
                    "reasoning": "Deterministic fast-path: IBAN_CHANGE detected — account takeover / merchant impersonation.",
                }
                deterministic_fraud += 1
                continue
            if _is_deterministic_legit(raw):
                current_assessments[tx_id] = {
                    "transaction_id": tx_id,
                    "is_fraud": False,
                    "confidence": 0.98 if not raw.get("signals") else 0.92,
                    "fraud_signals": [],
                    "reasoning": "Deterministic fast-path: no anomaly signals requiring LLM review.",
                }
                deterministic_legit += 1
                continue
            # Ricostruisci parzialmente (solo i campi usati dal classifier)
            txs = TS_cls(
                transaction_id=tx_id,
                timestamp="",
                sender_id=raw["sender_id"],
                recipient_id="",
                transaction_type=raw["transaction_type"],
                amount=raw["amount"],
                description="",
                location="",
                sender_name=raw["sender_name"],
                sender_job="",
                sender_city="",
                signals=raw["signals"],
                is_recurring=raw["is_recurring"],
            )
            # Override to_llm_text con la versione pre-calcolata
            txs._llm_text_override = raw["llm_text"]
            signals_objs[tx_id] = txs

    llm_tx_ids = list(signals_objs.keys())
    llm_tx_count = len(llm_tx_ids)
    llm_batches = math.ceil(llm_tx_count / BATCH_SIZE) if llm_tx_count else 0
    _phase(
        f"FASE 3/4 — Batch LLM Classifier  "
        f"({llm_tx_count} tx → {llm_batches} batch da {BATCH_SIZE} | "
        f"fast-legit={deterministic_legit} | fast-fraud={deterministic_fraud})"
    )

    if not signals_objs:
        log.info(
            "Nessuna transazione richiede l'LLM: classificazione completata via fast-path."
        )
        return {"individual_assessments": current_assessments}

    # Usa CLASSIFIER_MODEL se impostato, altrimenti il modello principale.
    # Un modello piccolo/veloce (7-8B) è sufficiente per classificazione batch.
    classifier_model = os.getenv("CLASSIFIER_MODEL") or None
    llm = build_llm(
        session_id=session_id,
        agent_name="batch_classifier",
        model=classifier_model,
    )

    t_total = time.perf_counter()
    for batch_idx, batch_ids in enumerate(_chunks(llm_tx_ids, BATCH_SIZE)):
        if batch_idx > 0:
            time.sleep(BATCH_DELAY)

        batch_signals = [signals_objs[tid] for tid in batch_ids if tid in signals_objs]
        if not batch_signals:
            continue
        log.info(
            _progress(
                batch_idx + 1,
                llm_batches,
                f"llm_tx {batch_idx * BATCH_SIZE + 1}–{min((batch_idx + 1) * BATCH_SIZE, llm_tx_count)}",
            )
        )
        log.info(
            "  [DBG] batch_ids=%s",
            ",".join(t[:8] for t in batch_ids),
        )

        assessments: list[TransactionAssessment] = _with_retry(
            lambda b=batch_signals: classify_batch(b, llm, session_id),
            label=f"classify batch {batch_idx + 1}",
        )
        for a in assessments:
            current_assessments[a.transaction_id] = a.model_dump()

    elapsed = time.perf_counter() - t_total
    fraud_ids = [tid for tid, a in current_assessments.items() if a.get("is_fraud")]
    log.info(
        f"Classify total time : {elapsed:.1f}s  ({elapsed / len(tx_ids) * 1000:.0f}ms/tx)"
    )
    log.info(f"Fraud candidates    : {len(fraud_ids)}")
    for fid in fraud_ids:
        a = current_assessments[fid]
        log.info(
            f"  {fid[:36]}  conf={a.get('confidence', 0):.2f}  "
            f"signals={a.get('fraud_signals', [])}"
        )

    return {"individual_assessments": current_assessments}


# ---------------------------------------------------------------------------
# Nodo 3b — Re-classify borderline (richiesto dal supervisor)
# ---------------------------------------------------------------------------


def node_reclassify(state: FraudState) -> dict:
    to_redo = state["transactions_to_reanalyze"]
    session_id = state["session_id"]
    current_assessments = dict(state["individual_assessments"])
    signals_map = state["tx_signals"]
    round_num = state["reanalysis_round"] + 1

    _phase(f"FASE 3b — Re-classify borderline (round {round_num}, {len(to_redo)} tx)")

    from agents.fast_scanner import TxSignals as TS_cls

    batch_signals = []
    for tx_id in to_redo:
        raw = signals_map.get(tx_id, {})
        txs = TS_cls(
            transaction_id=tx_id,
            timestamp="",
            sender_id=raw.get("sender_id", ""),
            recipient_id="",
            transaction_type=raw.get("transaction_type", ""),
            amount=raw.get("amount", 0.0),
            description="",
            location="",
            signals=raw.get("signals", []),
            is_recurring=raw.get("is_recurring", False),
        )
        txs._llm_text_override = raw.get("llm_text", f"TX {tx_id}")
        batch_signals.append(txs)

    llm = build_llm(
        session_id=session_id, agent_name=f"reclassify_r{round_num}", temperature=0.1
    )
    assessments = _with_retry(
        lambda: classify_batch(batch_signals, llm, session_id),
        label="reclassify borderline",
    )
    for a in assessments:
        current_assessments[a.transaction_id] = a.model_dump()

    return {
        "individual_assessments": current_assessments,
        "reanalysis_round": round_num,
        "transactions_to_reanalyze": [],
    }


# ---------------------------------------------------------------------------
# Nodo 4 — Fraud Supervisor (ReAct, solo sui candidati)
# ---------------------------------------------------------------------------


def node_fraud_review(state: FraudState) -> dict:
    session_id = state["session_id"]
    assessments = state["individual_assessments"]
    round_num = state.get("reanalysis_round", 0)

    _phase(f"FASE 4/4 — Fraud Supervisor (round {round_num})")

    fraud_candidates = [tx_id for tx_id, a in assessments.items() if a.get("is_fraud")]
    if not fraud_candidates:
        log.info(
            "Nessun candidato fraud dopo il classifier: salto il supervisor ReAct."
        )
        return {
            "supervisor_decision": {
                "final_fraud_transactions": [],
                "transactions_to_reanalyze": [],
                "revised_verdicts": [],
                "population_reasoning": "No fraud candidates after deterministic and batch classification.",
            },
            "final_fraud_transactions": [],
            "transactions_to_reanalyze": [],
        }

    if len(fraud_candidates) <= SUPERVISOR_FASTPATH_MAX_CANDIDATES:
        log.info(
            "Fast-path supervisor: pochi candidati fraud, salto ReAct e confermo i candidati del classifier."
        )
        return {
            "supervisor_decision": {
                "final_fraud_transactions": fraud_candidates,
                "transactions_to_reanalyze": [],
                "revised_verdicts": [],
                "population_reasoning": "Supervisor fast-path enabled for small fraud-candidate sets.",
            },
            "final_fraud_transactions": fraud_candidates,
            "transactions_to_reanalyze": [],
        }

    # Riduce il payload del supervisor: solo fraud candidati e borderline.
    review_assessments = {
        tx_id: a
        for tx_id, a in assessments.items()
        if a.get("is_fraud") or a.get("confidence", 1.0) < 0.70
    }
    if not review_assessments:
        review_assessments = {tx_id: assessments[tx_id] for tx_id in fraud_candidates}
    log.info(
        f"Supervisor review scope: {len(review_assessments)}/{len(assessments)} assessments"
    )

    llm = build_llm(session_id=session_id, agent_name=f"supervisor_r{round_num}")

    t0 = time.perf_counter()
    decision: SupervisorDecision = _with_retry(
        lambda: run_fraud_review(
            individual_assessments=review_assessments,
            llm=llm,
            session_id=session_id,
            max_iterations=SUPERVISOR_MAX_ITERATIONS,
        ),
        label="fraud_review",
    )
    elapsed = time.perf_counter() - t0

    log.info(f"Supervisor time     : {elapsed:.1f}s")
    log.info(
        f"Final fraud list    : {len(decision.final_fraud_transactions)} transactions"
    )
    for tx_id in decision.final_fraud_transactions:
        log.info(f"  FRAUD → {tx_id}")
    if decision.revised_verdicts:
        for rev in decision.revised_verdicts:
            log.info(
                f"  REVISED {rev.get('transaction_id', '?')[:16]}... "
                f"{rev.get('old_verdict')} → {rev.get('new_verdict')} | {str(rev.get('reason', ''))[:60]}"
            )
    if decision.transactions_to_reanalyze:
        log.info(f"  Re-analyze requested: {decision.transactions_to_reanalyze}")

    return {
        "supervisor_decision": decision.model_dump(),
        "final_fraud_transactions": decision.final_fraud_transactions,
        "transactions_to_reanalyze": decision.transactions_to_reanalyze,
    }


# ---------------------------------------------------------------------------
# Nodo 5 — Scrittura output
# ---------------------------------------------------------------------------


def node_write_output(state: FraudState) -> dict:
    output_path = Path(state["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fraud_txs = state["final_fraud_transactions"]
    assessments = state.get("individual_assessments", {})

    with open(output_path, "w", encoding="ascii") as f:
        for tx_id in fraud_txs:
            f.write(f"{tx_id}\n")

    total = len(assessments)
    _phase("RISULTATO FINALE")
    log.info(f"Output file         : {output_path}")
    log.info(f"Total tx analyzed   : {total}")
    log.info(
        f"Fraud detected      : {len(fraud_txs)}  ({len(fraud_txs) / total * 100:.1f}% of total)"
    )
    log.info(f"Langfuse session    : {state['session_id']}")
    log.info("")
    log.info("Fraud transactions:")
    for tx_id in fraud_txs:
        a = assessments.get(tx_id, {})
        log.info(
            f"  {tx_id}  conf={a.get('confidence', 0):.2f}  {a.get('fraud_signals', [])}"
        )

    supervisor_reasoning = state.get("supervisor_decision", {}).get(
        "population_reasoning", ""
    )
    if supervisor_reasoning:
        log.info(f"\nSupervisor reasoning:\n  {supervisor_reasoning[:300]}")

    return {}


# ---------------------------------------------------------------------------
# Conditional edge
# ---------------------------------------------------------------------------


def _should_reanalyze(state: FraudState) -> Literal["reanalyze", "finalize"]:
    to_redo = state.get("transactions_to_reanalyze", [])
    round_num = state.get("reanalysis_round", 0)
    if to_redo and round_num < MAX_REANALYSIS_ROUNDS:
        log.info(
            f"Supervisor requests re-analysis: {len(to_redo)} tx (round {round_num + 1}/{MAX_REANALYSIS_ROUNDS})"
        )
        return "reanalyze"
    return "finalize"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    g = StateGraph(FraudState)
    g.add_node("load_data", node_load_data)
    g.add_node("fast_scan", node_fast_scan)
    g.add_node("batch_classify", node_batch_classify)
    g.add_node("fraud_review", node_fraud_review)
    g.add_node("reclassify", node_reclassify)
    g.add_node("write_output", node_write_output)

    g.set_entry_point("load_data")
    g.add_edge("load_data", "fast_scan")
    g.add_edge("fast_scan", "batch_classify")
    g.add_edge("batch_classify", "fraud_review")
    g.add_conditional_edges(
        "fraud_review",
        _should_reanalyze,
        {"reanalyze": "reclassify", "finalize": "write_output"},
    )
    g.add_edge("reclassify", "fraud_review")
    g.add_edge("write_output", END)
    return g.compile()


def run_pipeline(data_dir: str, output_path: str) -> list[str]:
    """Entry point: esegue la pipeline e restituisce gli ID delle transazioni fraudolente."""
    t0 = time.perf_counter()
    app = build_graph()
    final_state = app.invoke({"data_dir": data_dir, "output_path": output_path})
    elapsed = time.perf_counter() - t0
    log.info(f"\nTotal pipeline time: {elapsed:.1f}s")
    return final_state.get("final_fraud_transactions", [])
