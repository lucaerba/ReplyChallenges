"""
LangChain Tools — funzioni che gli agenti invocano autonomamente per investigare le frodi.

Ogni tool legge da un DataStore globale inizializzato dall'orchestratore.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# DataStore globale
# ---------------------------------------------------------------------------
_store: dict = {}


def init_data_store(data: dict) -> None:
    """Carica i dati nel DataStore globale. Chiamato una volta dall'orchestratore."""
    global _store
    _store = data


# ---------------------------------------------------------------------------
# Helper interni
# ---------------------------------------------------------------------------

def _get_transactions() -> list[dict]:
    return _store.get("transactions", [])


def _get_users_by_id() -> dict:
    return _store.get("users_by_id", {})


def _get_sms() -> list[str]:
    return _store.get("sms", [])


def _get_mails() -> list[str]:
    return _store.get("mails", [])


def _get_locations() -> list[dict]:
    return _store.get("locations", [])


def _parse_dt(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Tool 1 — Dettagli transazione
# ---------------------------------------------------------------------------

@tool
def get_transaction_details(transaction_id: str) -> str:
    """
    Get full details of a specific transaction by its ID.
    Returns sender, recipient, amount, type, timestamp, IBANs, location, description.
    Use this as the first step when analyzing any transaction.
    """
    txs = _get_transactions()
    tx = next((t for t in txs if t.get("transaction_id") == transaction_id), None)
    if not tx:
        return f"Transaction {transaction_id} not found."

    lines = [f"=== Transaction: {transaction_id} ==="]
    for k, v in tx.items():
        if v:
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2 — Storico transazioni utente
# ---------------------------------------------------------------------------

@tool
def get_user_transactions(user_id: str) -> str:
    """
    Get all transactions where the given user_id appears as sender or recipient.
    Returns a sorted timeline with amounts, types, descriptions and IBANs.
    Use this to understand the user's normal spending and income patterns.
    """
    txs = _get_transactions()
    user_txs = [
        t for t in txs
        if t.get("sender_id") == user_id or t.get("recipient_id") == user_id
    ]
    if not user_txs:
        return f"No transactions found for user {user_id}."

    user_txs.sort(key=lambda t: t.get("timestamp", ""))
    lines = [f"=== Transactions for {user_id} ({len(user_txs)} records) ==="]
    for t in user_txs:
        direction = "OUT" if t.get("sender_id") == user_id else "IN"
        counterpart = t.get("recipient_id") if direction == "OUT" else t.get("sender_id")
        lines.append(
            f"  [{t['timestamp'][:10]}] {direction} | {t['transaction_type']} | "
            f"€{float(t['amount']):.2f} | "
            f"→ {counterpart} | "
            f"desc: {t.get('description', '') or '(none)'} | "
            f"balance_after: {t.get('balance_after', '')} | "
            f"tx_id: {t['transaction_id']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 — Profilo utente
# ---------------------------------------------------------------------------

@tool
def get_user_profile(user_id: str) -> str:
    """
    Get demographic profile and financial info for a citizen.
    Returns name, birth year, salary, job, city of residence, IBAN.
    Use this to contextualize transactions with personal data.
    """
    users = _get_users_by_id()
    u = users.get(user_id)
    if not u:
        return f"No profile found for user {user_id}. This may be a merchant or employer (not a citizen)."

    birth = u.get("birth_year", "?")
    age = (datetime.now().year - int(birth)) if birth != "?" else "?"
    res = u.get("residence", {})
    lines = [
        f"=== Profile: {user_id} ===",
        f"  Name   : {u.get('first_name', '')} {u.get('last_name', '')}",
        f"  Age    : {age} (born {birth})",
        f"  Job    : {u.get('job', 'Unknown')}",
        f"  City   : {res.get('city', '?')} (lat={res.get('lat', '?')}, lng={res.get('lng', '?')})",
        f"  Salary : {u.get('salary', '?')} (annual)",
        f"  IBAN   : {u.get('iban', 'Unknown')}",
        f"  Description: {u.get('description', '')[:300]}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — Consistenza IBAN per merchant/recipient
# ---------------------------------------------------------------------------

@tool
def check_iban_consistency(entity_id: str) -> str:
    """
    Check whether a merchant or entity has used consistent IBANs across all transactions.
    IBAN changes for the same entity can indicate account hijacking or fraud.
    Returns a list of unique IBANs seen, grouped by role (sender/recipient).
    """
    txs = _get_transactions()
    sender_ibans: dict[str, list[str]] = {}
    recipient_ibans: dict[str, list[str]] = {}

    for t in txs:
        if t.get("sender_id") == entity_id:
            iban = t.get("sender_iban", "")
            tx_id = t["transaction_id"]
            date = t["timestamp"][:10]
            if iban:
                sender_ibans.setdefault(iban, []).append(f"{date} tx={tx_id[:8]}...")

        if t.get("recipient_id") == entity_id:
            iban = t.get("recipient_iban", "")
            tx_id = t["transaction_id"]
            date = t["timestamp"][:10]
            if iban:
                recipient_ibans.setdefault(iban, []).append(f"{date} tx={tx_id[:8]}...")

    lines = [f"=== IBAN Consistency for {entity_id} ==="]

    if sender_ibans:
        lines.append(f"As SENDER — {len(sender_ibans)} unique IBAN(s):")
        for iban, txs_list in sender_ibans.items():
            flag = " ← SAME" if len(sender_ibans) == 1 else " ⚠ DIFFERENT"
            lines.append(f"  {iban}{flag if len(sender_ibans) > 1 else ''}")
            for tx_ref in txs_list[:3]:
                lines.append(f"    used in: {tx_ref}")

    if recipient_ibans:
        lines.append(f"As RECIPIENT — {len(recipient_ibans)} unique IBAN(s):")
        for iban, txs_list in recipient_ibans.items():
            lines.append(f"  {iban}")
            for tx_ref in txs_list[:3]:
                lines.append(f"    used in: {tx_ref}")

    if len(recipient_ibans) > 1:
        lines.append(
            f"\n⚠ WARNING: {entity_id} used {len(recipient_ibans)} DIFFERENT recipient IBANs. "
            "This may indicate fraud (account takeover or merchant impersonation)."
        )
    elif len(sender_ibans) > 1:
        lines.append(
            f"\n⚠ WARNING: {entity_id} used {len(sender_ibans)} DIFFERENT sender IBANs."
        )
    else:
        lines.append(f"\n✓ IBAN is consistent across all transactions for {entity_id}.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5 — Comunicazioni sospette per utente
# ---------------------------------------------------------------------------

@tool
def get_suspicious_communications(user_id: str) -> str:
    """
    Scan all SMS and emails for phishing or suspicious messages targeting the given user.
    Looks for typosquatted domains, URGENT flags, fake security alerts, suspicious links.
    Returns any phishing indicators found with their dates.

    Phishing signals: misspelled domains (paypa1, amaz0n, r1d3share), URGENT/VERIFY keywords,
    requests to click links to confirm credentials, unexpected login alerts.
    """
    sms_list = _get_sms()
    mail_list = _get_mails()
    users = _get_users_by_id()

    # Trova il nome del cittadino per cercare nei messaggi
    u = users.get(user_id, {})
    first_name = u.get("first_name", "")
    last_name = u.get("last_name", "")
    search_names = [n for n in [first_name, last_name] if n]

    # Pattern di phishing
    phishing_patterns = [
        r"paypa[^l]",             # paypal typo
        r"amaz[0o]n",             # amazon typo
        r"r[1i]d[e3]share",       # rideshare typo
        r"google[^.]",
        r"urgent[:\s]",
        r"verify.{0,30}(account|identity|login)",
        r"suspicious.{0,30}(login|sign.?in|activity)",
        r"account.{0,20}(lock|suspend|block)",
        r"click.{0,30}(link|here|now|verify)",
        r"bit\.ly/[a-z0-9]*[013]",  # shortened links with l33tspeak
        r"confirm.{0,20}(password|credentials|identity)",
        r"-verify\.com",
        r"-secure\.com",
        r"@(?!.*\.(fr|de|gb|gov|com$))",
    ]

    suspicious_found = []
    all_messages = [(f"SMS-{i}", m) for i, m in enumerate(sms_list)] + \
                   [(f"MAIL-{i}", m) for i, m in enumerate(mail_list)]

    for msg_id, text in all_messages:
        # Controlla se il messaggio è per questo utente (contiene il nome)
        text_lower = text.lower()
        is_for_user = (
            not search_names or
            any(n.lower() in text_lower for n in search_names)
        )
        if not is_for_user:
            continue

        # Cerca pattern di phishing
        flags = []
        for pattern in phishing_patterns:
            if re.search(pattern, text_lower):
                flags.append(pattern)

        if flags:
            # Estrai data se presente
            date_match = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", text)
            date_str = date_match.group(1) if date_match else "unknown date"

            # Estrai mittente
            from_match = re.search(r"From:\s*(.+?)[\n\r]", text)
            from_str = from_match.group(1).strip()[:60] if from_match else "unknown sender"

            suspicious_found.append({
                "msg_id": msg_id,
                "date": date_str,
                "from": from_str,
                "flags": flags,
                "snippet": text[:200].replace("\n", " "),
            })

    if not suspicious_found:
        return f"No phishing or suspicious communications found for {user_id} ({first_name} {last_name})."

    lines = [
        f"=== Suspicious Communications for {user_id} ({first_name} {last_name}) ===",
        f"  {len(suspicious_found)} phishing/suspicious message(s) found:\n"
    ]
    for item in suspicious_found:
        lines.append(
            f"  [{item['date']}] {item['msg_id']} | From: {item['from']}\n"
            f"    Flags: {item['flags']}\n"
            f"    Snippet: {item['snippet'][:150]}...\n"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6 — Posizione GPS vicino alla data della transazione
# ---------------------------------------------------------------------------

@tool
def get_location_at_transaction(user_id: str, transaction_timestamp: str) -> str:
    """
    Get the user's GPS location around the time of a transaction.
    Checks locations within ±3 days of the transaction timestamp.
    Useful for verifying if an in-person payment makes geographic sense.
    """
    locations = _get_locations()
    tx_dt = _parse_dt(transaction_timestamp)
    if not tx_dt:
        return f"Could not parse timestamp: {transaction_timestamp}"

    window = timedelta(days=3)
    nearby = []
    for loc in locations:
        biotag = loc.get("biotag", "")
        if biotag != user_id:
            continue
        loc_dt = _parse_dt(loc.get("timestamp", ""))
        if loc_dt and abs(loc_dt - tx_dt) <= window:
            nearby.append(loc)

    if not nearby:
        return f"No GPS records found for {user_id} within 3 days of {transaction_timestamp[:10]}."

    nearby.sort(key=lambda x: x.get("timestamp", ""))
    lines = [
        f"=== GPS Locations for {user_id} near {transaction_timestamp[:10]} ===",
        f"  ({len(nearby)} records within ±3 days)"
    ]
    for loc in nearby:
        lines.append(
            f"  [{loc['timestamp']}] "
            f"City: {loc.get('city', '?')} | "
            f"lat={loc.get('lat', '?')}, lng={loc.get('lng', '?')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 7 — Analisi pattern statistici per utente
# ---------------------------------------------------------------------------

@tool
def analyze_user_patterns(user_id: str) -> str:
    """
    Compute statistical spending patterns for a user:
    - Typical outgoing amount range (mean, std, min, max) per transaction type
    - Known recurring counterparts (salary senders, rent recipients, merchants)
    - Known merchant IBANs used in the past
    Use this to detect transactions that are statistically anomalous.
    """
    txs = _get_transactions()
    user_out = [t for t in txs if t.get("sender_id") == user_id]

    if not user_out:
        return f"No outgoing transactions for {user_id}."

    # Raggruppa per tipo
    by_type: dict[str, list[float]] = {}
    counterparts: dict[str, int] = {}
    merchant_ibans: dict[str, set] = {}

    for t in user_out:
        ttype = t.get("transaction_type", "unknown")
        try:
            amt = float(t["amount"])
        except (ValueError, KeyError):
            continue

        by_type.setdefault(ttype, []).append(amt)

        cpart = t.get("recipient_id", "?")
        counterparts[cpart] = counterparts.get(cpart, 0) + 1

        iban = t.get("recipient_iban", "")
        if cpart and iban:
            merchant_ibans.setdefault(cpart, set()).add(iban)

    lines = [f"=== Spending Patterns for {user_id} ==="]
    lines.append(f"  Total outgoing transactions: {len(user_out)}")
    lines.append("")

    for ttype, amounts in by_type.items():
        n = len(amounts)
        mean = sum(amounts) / n
        mx = max(amounts)
        mn = min(amounts)
        lines.append(
            f"  {ttype} ({n} tx): "
            f"mean=€{mean:.2f} | min=€{mn:.2f} | max=€{mx:.2f}"
        )

    lines.append("\n  Known counterparts (recipient → count):")
    for cpart, count in sorted(counterparts.items(), key=lambda x: -x[1]):
        ibans = merchant_ibans.get(cpart, set())
        iban_str = (
            f"IBAN consistent ({list(ibans)[0][:15]}...)"
            if len(ibans) == 1
            else f"⚠ {len(ibans)} DIFFERENT IBANs: {', '.join(list(ibans)[:2])}..."
        )
        lines.append(f"    {cpart} ({count}x) — {iban_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 8 — Confronto transazione con baseline utente
# ---------------------------------------------------------------------------

@tool
def check_transaction_anomaly(transaction_id: str) -> str:
    """
    Compare a specific transaction against the user's historical baseline.
    Flags anomalies such as:
    - Amount significantly higher than usual for that transaction type
    - New/unknown counterpart (never seen before)
    - New recipient IBAN for a known counterpart
    - Unusual transaction type for this user
    - Transaction at unusual time (e.g. 3 AM)
    """
    txs = _get_transactions()
    tx = next((t for t in txs if t.get("transaction_id") == transaction_id), None)
    if not tx:
        return f"Transaction {transaction_id} not found."

    sender_id = tx.get("sender_id", "")
    ttype = tx.get("transaction_type", "")
    try:
        amount = float(tx.get("amount", 0))
    except ValueError:
        amount = 0.0

    recipient_id = tx.get("recipient_id", "")
    recipient_iban = tx.get("recipient_iban", "")
    timestamp = tx.get("timestamp", "")

    # Storico del sender (escludi questa transazione)
    history = [
        t for t in txs
        if t.get("sender_id") == sender_id and t.get("transaction_id") != transaction_id
    ]

    flags = []

    if not history:
        return f"No historical data for sender {sender_id} — cannot compare."

    # 1. Amount anomaly per tipo
    same_type = [
        float(t["amount"]) for t in history
        if t.get("transaction_type") == ttype
        and t["amount"]
    ]
    if same_type:
        mean_amt = sum(same_type) / len(same_type)
        if amount > mean_amt * 2.5:
            flags.append(
                f"AMOUNT ANOMALY: €{amount:.2f} is {amount/mean_amt:.1f}x the "
                f"historical mean (€{mean_amt:.2f}) for {ttype}"
            )
    else:
        flags.append(f"NEW transaction type for this user: '{ttype}' (never done before)")

    # 2. New counterpart
    known_recipients = {t.get("recipient_id") for t in history}
    if recipient_id and recipient_id not in known_recipients:
        flags.append(
            f"NEW COUNTERPART: '{recipient_id}' never seen before in this user's history"
        )

    # 3. IBAN change for known merchant
    if recipient_id in known_recipients:
        known_ibans = {
            t.get("recipient_iban")
            for t in history
            if t.get("recipient_id") == recipient_id and t.get("recipient_iban")
        }
        if known_ibans and recipient_iban and recipient_iban not in known_ibans:
            flags.append(
                f"IBAN CHANGE: '{recipient_id}' used {list(known_ibans)[0][:20]}... before, "
                f"now using {recipient_iban[:20]}..."
            )

    # 4. Unusual hour
    tx_dt = _parse_dt(timestamp)
    if tx_dt and (tx_dt.hour < 5 or tx_dt.hour >= 1 and tx_dt.hour < 4):
        flags.append(f"UNUSUAL HOUR: transaction at {tx_dt.hour:02d}:{tx_dt.minute:02d}")

    # Risultato
    lines = [f"=== Anomaly Check: {transaction_id[:16]}... ==="]
    lines.append(
        f"  Sender: {sender_id} | Type: {ttype} | Amount: €{amount:.2f} | "
        f"Recipient: {recipient_id or '?'}"
    )
    if flags:
        lines.append(f"\n  ⚠ {len(flags)} ANOMALY FLAG(S) DETECTED:")
        for f_ in flags:
            lines.append(f"    • {f_}")
    else:
        lines.append("\n  ✓ No anomalies detected — transaction appears within normal range.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 9 — Overview popolazione transazioni (per supervisor)
# ---------------------------------------------------------------------------

@tool
def get_population_overview() -> str:
    """
    Get a high-level statistical overview of ALL transactions across ALL users.
    Returns per-user transaction counts, total volumes, and anomaly indicators.
    Useful for the fraud supervisor to detect systemic patterns.
    """
    txs = _get_transactions()
    users = _get_users_by_id()

    if not txs:
        return "No transaction data available."

    # Aggregazione per sender
    by_sender: dict[str, list] = {}
    for t in txs:
        sid = t.get("sender_id", "?")
        by_sender.setdefault(sid, []).append(t)

    lines = [f"=== Population Overview ({len(txs)} transactions, {len(users)} citizens) ===\n"]

    citizen_ids = set(users.keys())
    lines.append("Citizens:")
    for cid in sorted(citizen_ids):
        out_txs = by_sender.get(cid, [])
        amounts = [float(t["amount"]) for t in out_txs if t.get("amount")]
        total = sum(amounts)
        types = list({t.get("transaction_type") for t in out_txs})
        lines.append(
            f"  {cid}: {len(out_txs)} outgoing tx | "
            f"total=€{total:.2f} | types={types}"
        )

    # IBAN inconsistencies across all merchants
    all_recipient_ibans: dict[str, set] = {}
    for t in txs:
        rid = t.get("recipient_id", "")
        iban = t.get("recipient_iban", "")
        if rid and iban:
            all_recipient_ibans.setdefault(rid, set()).add(iban)

    suspicious_merchants = {
        mid: ibans
        for mid, ibans in all_recipient_ibans.items()
        if len(ibans) > 1
    }
    if suspicious_merchants:
        lines.append(f"\n⚠ Merchants/entities with MULTIPLE recipient IBANs ({len(suspicious_merchants)}):")
        for mid, ibans in suspicious_merchants.items():
            lines.append(f"  {mid}: {len(ibans)} different IBANs → {list(ibans)}")
    else:
        lines.append("\n✓ All merchants use consistent IBANs.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 10 — Lista transaction IDs da analizzare
# ---------------------------------------------------------------------------

@tool
def list_all_transactions() -> str:
    """
    List all transaction IDs in the dataset with basic info (date, type, amount, sender).
    Use this to get an overview of what needs to be investigated.
    """
    txs = _get_transactions()
    lines = [f"=== All Transactions ({len(txs)} total) ==="]
    for t in txs:
        lines.append(
            f"  {t['transaction_id']} | "
            f"{t['timestamp'][:10]} | "
            f"{t.get('transaction_type', '?'):20s} | "
            f"€{float(t.get('amount', 0)):>10.2f} | "
            f"sender={t.get('sender_id', '?')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

ANALYST_TOOLS = [
    get_transaction_details,
    get_user_transactions,
    get_user_profile,
    check_iban_consistency,
    get_suspicious_communications,
    get_location_at_transaction,
    analyze_user_patterns,
    check_transaction_anomaly,
]

SUPERVISOR_TOOLS = [
    get_population_overview,
    list_all_transactions,
    get_transaction_details,
    check_iban_consistency,
    check_transaction_anomaly,
    get_suspicious_communications,
]
