"""
Fast Statistical Scanner — pre-calcolo deterministico dei segnali di frode.

Analizza TUTTE le transazioni in O(n) senza chiamate LLM.
Produce un contesto strutturato per ogni transazione che verrà
passato all'LLM per la classificazione finale.

Segnali calcolati:
  IBAN_CHANGE       — recipient ha cambiato IBAN rispetto a tx precedenti
  AMOUNT_HIGH       — importo > 2.5x media storica per quel tipo/sender
  POST_PHISHING     — tx avviene entro 45 giorni da attacco phishing sul sender
  NEW_COUNTERPART   — destinatario mai visto prima in questo dataset
  UNUSUAL_HOUR      — ore 1-4 AM per transazioni non ricorrenti
  RECURRING_OK      — pattern ricorrente mensile (salary/rent), nessun segnale
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Strutture dati
# ---------------------------------------------------------------------------

@dataclass
class TxSignals:
    """Segnali pre-calcolati per una singola transazione."""
    transaction_id: str
    timestamp: str
    sender_id: str
    recipient_id: str
    transaction_type: str
    amount: float
    description: str
    location: str

    # Contesto utente
    sender_name: str = ""
    sender_job: str = ""
    sender_city: str = ""

    # Segnali di frode
    signals: list[str] = field(default_factory=list)

    # Contesto storico
    is_recurring: bool = False          # pattern mensile noto (salary/rent)
    prev_iban: str = ""                 # IBAN usato in precedenza con questo recipient
    curr_iban: str = ""
    amount_mean: float = 0.0            # media storica per questo tipo/sender
    phishing_count: int = 0             # attacchi phishing nei 45gg precedenti

    @property
    def risk_score(self) -> int:
        """Score 0-10 basato sui segnali (usato per prioritizzare i casi borderline)."""
        score = 0
        for s in self.signals:
            if s.startswith("IBAN_CHANGE"):
                score += 4
            elif s.startswith("POST_PHISHING"):
                score += 3
            elif s.startswith("AMOUNT_HIGH"):
                score += 2
            elif s.startswith("NEW_COUNTERPART"):
                score += 1
            elif s.startswith("UNUSUAL_HOUR"):
                score += 1
        return min(score, 10)

    def to_llm_text(self) -> str:
        """Formatta il contesto per l'LLM (usa override se disponibile)."""
        if hasattr(self, "_llm_text_override") and self._llm_text_override:
            return self._llm_text_override
        lines = [
            f"TX {self.transaction_id}",
            f"  Date : {self.timestamp[:16]} | Type: {self.transaction_type} | Amount: €{self.amount:.2f}",
            f"  From : {self.sender_id} ({self.sender_name}, {self.sender_job}, {self.sender_city})",
            f"  To   : {self.recipient_id}",
        ]
        if self.description:
            lines.append(f"  Desc : {self.description}")
        if self.is_recurring:
            lines.append(f"  ✓ RECURRING pattern (monthly, stable amount ~€{self.amount_mean:.0f})")
        if self.signals:
            lines.append(f"  ⚠ SIGNALS ({len(self.signals)}):")
            for s in self.signals:
                lines.append(f"      • {s}")
        else:
            lines.append(f"  ✓ No anomaly signals detected")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


_PHISHING_PATTERNS = [
    re.compile(r"paypa[^l]", re.I),
    re.compile(r"amaz[0o]n[\-\.]", re.I),
    re.compile(r"r[1i]d[e3]share", re.I),
    re.compile(r"urgent[:\s].{0,60}(verify|confirm|account)", re.I),
    re.compile(r"suspicious.{0,40}(login|sign.?in|activity)", re.I),
    re.compile(r"account.{0,30}(lock|suspend|block)", re.I),
    re.compile(r"[a-z0-9\-]+-verify\.com", re.I),
    re.compile(r"[a-z0-9\-]+-secure\.net", re.I),
    re.compile(r"@[a-z0-9\-]+1[a-z0-9\-]*\.", re.I),   # l33tspeak nel dominio
]


def _is_phishing(text: str) -> bool:
    return any(p.search(text) for p in _PHISHING_PATTERNS)


def _extract_name_from_sms(text: str) -> str:
    """Cerca 'Hi/Hello NAME' o 'To: NAME' nel testo."""
    m = re.search(r"(?:Hi|Hello|Dear)\s+([A-Z][a-z]+)", text)
    if m:
        return m.group(1)
    m = re.search(r"To:\s+\+?\d{10,}", text)  # numero tel → non è un nome
    return ""


# ---------------------------------------------------------------------------
# Scanner principale
# ---------------------------------------------------------------------------

def scan_all(data: dict) -> dict[str, TxSignals]:
    """
    Analizza tutte le transazioni e restituisce {tx_id: TxSignals}.
    Complessità O(n) — nessuna chiamata LLM.
    """
    transactions: list[dict] = data["transactions"]
    users_by_id: dict = data["users_by_id"]
    sms_list: list[str] = data["sms"]
    mail_list: list[str] = data["mails"]

    # ---- 1. Build user profiles ----------------------------------------
    # Per ogni utente: patterns per tipo (mean amount), counterparts noti, IBANs usati

    user_tx_out: dict[str, list[dict]] = defaultdict(list)
    for tx in transactions:
        sid = tx.get("sender_id", "")
        if sid:
            user_tx_out[sid].append(tx)

    # Statistiche per tipo (calcolate su tutto l'insieme — nel dataset reale si
    # userebbe una finestra temporale, ma qui usiamo l'intera storia)
    user_type_stats: dict[str, dict[str, dict]] = {}
    for uid, txs in user_tx_out.items():
        by_type: dict[str, list[float]] = defaultdict(list)
        for t in txs:
            try:
                by_type[t["transaction_type"]].append(float(t["amount"]))
            except (ValueError, KeyError):
                pass
        user_type_stats[uid] = {
            ttype: {
                "mean": sum(amts) / len(amts),
                "count": len(amts),
            }
            for ttype, amts in by_type.items()
        }

    # Counterparts noti per utente
    user_known_recipients: dict[str, set] = defaultdict(set)
    for uid, txs in user_tx_out.items():
        for t in txs:
            r = t.get("recipient_id", "")
            if r:
                user_known_recipients[uid].add(r)

    # ---- 2. Build IBAN history (cronologico) ----------------------------
    # Per ogni (recipient_id), teniamo gli IBANs visti nelle transazioni PRECEDENTI
    # (ordinate per timestamp), così possiamo rilevare cambio IBAN in sequenza.

    txs_sorted = sorted(
        transactions,
        key=lambda t: t.get("timestamp", ""),
    )
    recipient_iban_history: dict[str, list[tuple[str, str]]] = defaultdict(list)
    # recipient_id → [(timestamp, iban), ...]  (in ordine cronologico)
    for t in txs_sorted:
        rid = t.get("recipient_id", "")
        iban = t.get("recipient_iban", "")
        ts = t.get("timestamp", "")
        if rid and iban:
            recipient_iban_history[rid].append((ts, iban))

    # ---- 3. Phishing map ------------------------------------------------
    # Per ogni utente (nome → citizen_id): lista di date phishing

    # Mappa nome → citizen_id
    name_to_cid: dict[str, str] = {}
    for cid, u in users_by_id.items():
        fn = u.get("first_name", "")
        ln = u.get("last_name", "")
        if fn:
            name_to_cid[fn.lower()] = cid
        if ln:
            name_to_cid[ln.lower()] = cid

    phishing_dates_by_cid: dict[str, list[datetime]] = defaultdict(list)
    all_comms = [(f"SMS-{i}", t) for i, t in enumerate(sms_list)] + \
                [(f"MAIL-{i}", t) for i, t in enumerate(mail_list)]

    for _, text in all_comms:
        if not _is_phishing(text):
            continue
        # Cerca a chi è diretto
        date_m = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", text)
        if not date_m:
            continue
        dt = _parse_dt(date_m.group(1))
        if not dt:
            continue
        # Trova il nome nel messaggio
        for name, cid in name_to_cid.items():
            if name in text.lower():
                phishing_dates_by_cid[cid].append(dt)
                break

    # ---- 4. Recurring pattern detection --------------------------------
    # Identifica transazioni mensili ricorrenti (salary, rent, subscriptions)
    # per ogni (sender, recipient, type) — se appaiono ogni mese con importo stabile

    pattern_key_counts: dict[tuple, int] = defaultdict(int)
    for t in transactions:
        key = (t.get("sender_id"), t.get("recipient_id"), t.get("transaction_type"))
        pattern_key_counts[key] += 1

    # Pattern ricorrente = stessa terna appare ≥ 3 volte
    RECURRING_MIN = 3

    # ---- 5. Calcola segnali per ogni transazione -----------------------

    result: dict[str, TxSignals] = {}

    for t in txs_sorted:
        tx_id = t.get("transaction_id", "")
        if not tx_id:
            continue

        sender_id = t.get("sender_id", "")
        recipient_id = t.get("recipient_id", "")
        ttype = t.get("transaction_type", "")
        ts = t.get("timestamp", "")
        tx_dt = _parse_dt(ts)

        try:
            amount = float(t.get("amount", 0))
        except ValueError:
            amount = 0.0

        curr_iban = t.get("recipient_iban", "")

        # Profilo sender
        u = users_by_id.get(sender_id, {})
        res = u.get("residence", {})
        sender_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        sender_job = u.get("job", "")
        sender_city = res.get("city", "")

        signals: list[str] = []

        # --- Segnale: IBAN change ---
        prev_ibans_for_recipient = [
            iban for (prev_ts, iban) in recipient_iban_history[recipient_id]
            if prev_ts < ts  # solo transazioni PRECEDENTI a questa
        ]
        prev_iban_set = set(prev_ibans_for_recipient)
        if prev_iban_set and curr_iban and curr_iban not in prev_iban_set:
            prev_iban = list(prev_iban_set)[-1]  # ultimo IBAN usato
            signals.append(
                f"IBAN_CHANGE: {recipient_id} previously used ...{prev_iban[-8:]} "
                f"→ now {curr_iban[-8:]} (first seen in this tx)"
            )

        # --- Segnale: Amount anomaly ---
        type_stats = user_type_stats.get(sender_id, {}).get(ttype, {})
        mean_amt = type_stats.get("mean", 0.0)
        if mean_amt > 0 and amount > mean_amt * 2.5:
            signals.append(
                f"AMOUNT_HIGH: €{amount:.0f} is {amount/mean_amt:.1f}x "
                f"historical mean €{mean_amt:.0f} for {ttype}"
            )

        # --- Segnale: Post-phishing window ---
        phishing_count = 0
        if tx_dt and sender_id in phishing_dates_by_cid:
            window = timedelta(days=45)
            phishing_count = sum(
                1 for pd in phishing_dates_by_cid[sender_id]
                if timedelta(0) <= (tx_dt - pd) <= window
            )
            if phishing_count > 0:
                signals.append(
                    f"POST_PHISHING: {phishing_count} phishing attack(s) targeting sender "
                    f"in the 45 days before this transaction"
                )

        # --- Segnale: New counterpart (solo per tipi non salary/rent) ---
        is_known = recipient_id in user_known_recipients.get(sender_id, set())
        is_salary_like = "salary" in t.get("description", "").lower() or \
                         ttype == "transfer" and sender_id.startswith("EMP")
        if not is_known and not is_salary_like and sender_id in users_by_id:
            signals.append(f"NEW_COUNTERPART: {recipient_id} never seen before for {sender_id}")

        # --- Segnale: Unusual hour ---
        if tx_dt and tx_dt.hour in (1, 2, 3, 4) and ttype not in ("direct debit",):
            signals.append(f"UNUSUAL_HOUR: transaction at {tx_dt.hour:02d}:{tx_dt.minute:02d}")

        # --- Recurring pattern ---
        pattern_key = (sender_id, recipient_id, ttype)
        is_recurring = pattern_key_counts[pattern_key] >= RECURRING_MIN

        result[tx_id] = TxSignals(
            transaction_id=tx_id,
            timestamp=ts,
            sender_id=sender_id,
            recipient_id=recipient_id,
            transaction_type=ttype,
            amount=amount,
            description=t.get("description", ""),
            location=t.get("location", ""),
            sender_name=sender_name,
            sender_job=sender_job,
            sender_city=sender_city,
            signals=signals,
            is_recurring=is_recurring,
            curr_iban=curr_iban,
            prev_iban=list(prev_iban_set)[-1] if prev_iban_set else "",
            amount_mean=mean_amt,
            phishing_count=phishing_count,
        )

    return result
