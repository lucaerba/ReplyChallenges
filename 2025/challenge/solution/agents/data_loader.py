"""
Data Loader — carica tutti i dataset del livello in strutture accessibili.

Gestisce:
- transactions.csv  → DataFrame con le transazioni finanziarie
- users.json        → dict {iban: user_info} e {citizen_id: user_info}
- locations.json    → DataFrame GPS per biotag/citizen
- sms.json          → list di messaggi SMS (testo grezzo)
- mails.json        → list di messaggi email (testo grezzo)
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path


def _load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all(data_dir: str) -> dict:
    """
    Carica tutti i file del dataset e restituisce un dict con:
        - transactions   : list[dict]  — tutte le transazioni
        - users_by_iban  : dict        — IBAN → user_info
        - users_by_id    : dict        — citizen_id → user_info
        - locations      : list[dict]  — tutti i record GPS
        - sms            : list[str]   — testi SMS
        - mails          : list[str]   — testi email
        - transaction_ids: list[str]   — tutti gli ID transazione
    """
    d = Path(data_dir)

    # --- Transactions ---
    tx_path = d / "transactions.csv"
    transactions = _load_csv(tx_path) if tx_path.exists() else []

    # --- Users ---
    users_raw = _load_json(d / "users.json") if (d / "users.json").exists() else []
    users_by_iban: dict = {}
    users_by_id: dict = {}

    for u in users_raw:
        iban = u.get("iban", "").strip()
        if iban:
            users_by_iban[iban] = u

    # Mappa citizen_id → user incrociando IBAN nelle transazioni
    iban_to_citizen: dict = {}
    for tx in transactions:
        sender_iban = tx.get("sender_iban", "").strip()
        sender_id = tx.get("sender_id", "").strip()
        if sender_iban in users_by_iban and sender_id:
            iban_to_citizen[sender_iban] = sender_id
            users_by_id[sender_id] = users_by_iban[sender_iban]

        recipient_iban = tx.get("recipient_iban", "").strip()
        recipient_id = tx.get("recipient_id", "").strip()
        if recipient_iban in users_by_iban and recipient_id:
            iban_to_citizen[recipient_iban] = recipient_id
            users_by_id[recipient_id] = users_by_iban[recipient_iban]

    # Aggiungi anche mapping diretto da users_raw se non trovato sopra
    for u in users_raw:
        iban = u.get("iban", "").strip()
        if iban and iban in iban_to_citizen:
            citizen_id = iban_to_citizen[iban]
            users_by_id[citizen_id] = u

    # --- Locations ---
    locations = _load_json(d / "locations.json") if (d / "locations.json").exists() else []

    # --- SMS ---
    sms_raw = _load_json(d / "sms.json") if (d / "sms.json").exists() else []
    sms_texts = [s.get("sms", "") if isinstance(s, dict) else str(s) for s in sms_raw]

    # --- Mails ---
    mails_raw = _load_json(d / "mails.json") if (d / "mails.json").exists() else []
    mail_texts = [m.get("mail", "") if isinstance(m, dict) else str(m) for m in mails_raw]

    # --- Citizen IDs (only real users, not employers/merchants) ---
    citizen_ids = sorted(users_by_id.keys())

    # --- Transaction IDs ---
    transaction_ids = [tx["transaction_id"] for tx in transactions if tx.get("transaction_id")]

    print(
        f"  DataLoader: {len(transactions)} transactions | "
        f"{len(users_by_id)} citizens | "
        f"{len(locations)} GPS records | "
        f"{len(sms_texts)} SMS | "
        f"{len(mail_texts)} mails"
    )

    return {
        "transactions": transactions,
        "users_by_iban": users_by_iban,
        "users_by_id": users_by_id,
        "locations": locations,
        "sms": sms_texts,
        "mails": mail_texts,
        "citizen_ids": citizen_ids,
        "transaction_ids": transaction_ids,
    }
