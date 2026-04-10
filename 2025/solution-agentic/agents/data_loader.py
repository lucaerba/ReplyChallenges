"""
DataLoader Agent — carica e fonde le 4 sorgenti dati per livello.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


def load_status(data_dir: Path) -> pd.DataFrame:
    """Carica status.csv e normalizza i tipi."""
    df = pd.read_csv(data_dir / "status.csv", parse_dates=["Timestamp"])
    df.columns = [c.strip() for c in df.columns]
    return df


def load_users(data_dir: Path) -> pd.DataFrame:
    """Carica users.json e restituisce un DataFrame indicizzato per user_id."""
    with open(data_dir / "users.json", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for u in raw:
        rows.append(
            {
                "citizen_id": u["user_id"],
                "first_name": u.get("first_name", ""),
                "last_name": u.get("last_name", ""),
                "birth_year": u.get("birth_year"),
                "job": u.get("job", ""),
                "city": u.get("residence", {}).get("city", ""),
                "home_lat": float(u.get("residence", {}).get("lat", 0)),
                "home_lng": float(u.get("residence", {}).get("lng", 0)),
            }
        )
    return pd.DataFrame(rows).set_index("citizen_id")


def load_locations(data_dir: Path) -> pd.DataFrame:
    """Carica locations.json (supporta sia BioTag che user_id come chiave)."""
    with open(data_dir / "locations.json", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for loc in raw:
        citizen_id = loc.get("user_id") or loc.get("BioTag")
        rows.append(
            {
                "citizen_id": citizen_id,
                "timestamp": pd.to_datetime(loc.get("timestamp") or loc.get("Datetime")),
                "lat": float(loc.get("lat") or loc.get("Lat", 0)),
                "lng": float(loc.get("lng") or loc.get("Lng", 0)),
                "city": loc.get("city", ""),
            }
        )
    return pd.DataFrame(rows)


def load_personas(data_dir: Path) -> dict[str, str]:
    """
    Carica personas.md e restituisce un dizionario {citizen_id: testo_profilo}.
    Supporta sia il formato '## CITIZEN_ID - Nome' che '## CITIZEN_ID\\nNome'.
    """
    personas_file = data_dir / "personas.md"
    if not personas_file.exists():
        return {}

    text = personas_file.read_text(encoding="utf-8")
    # Suddividi in sezioni per ogni cittadino (header ## XXXXXXXX)
    sections = re.split(r"\n(?=## [A-Z]{8})", text)

    profiles: dict[str, str] = {}
    for section in sections:
        match = re.match(r"## ([A-Z]{8})", section)
        if match:
            citizen_id = match.group(1)
            profiles[citizen_id] = section.strip()

    return profiles


def load_all(data_dir: str | Path) -> dict:
    """
    Entry-point principale del DataLoader Agent.

    Returns
    -------
    dict con chiavi:
        - "status"    : pd.DataFrame — eventi di monitoraggio
        - "users"     : pd.DataFrame — anagrafica, index=citizen_id
        - "locations" : pd.DataFrame — traiettorie GPS
        - "personas"  : dict[str, str] — profili narrativi
        - "citizen_ids": list[str] — tutti i cittadini unici presenti in status
    """
    data_dir = Path(data_dir)

    status = load_status(data_dir)
    users = load_users(data_dir)
    locations = load_locations(data_dir)
    personas = load_personas(data_dir)

    citizen_ids = sorted(status["CitizenID"].unique().tolist())

    return {
        "status": status,
        "users": users,
        "locations": locations,
        "personas": personas,
        "citizen_ids": citizen_ids,
    }
