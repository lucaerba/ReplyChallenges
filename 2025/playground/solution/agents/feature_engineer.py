"""
Feature Engineering Agent — costruisce un profilo numerico per ogni cittadino
a partire da status.csv, locations.json e users.json.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from geopy.distance import geodesic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _linear_trend(series: pd.Series) -> float:
    """Coefficiente angolare di una regressione lineare sulla serie (normalizzata 0..1)."""
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series), dtype=float)
    x -= x.mean()
    y = series.values.astype(float)
    y -= y.mean()
    denom = (x ** 2).sum()
    return float(np.dot(x, y) / denom) if denom != 0 else 0.0


def _radius_of_gyration(lats: pd.Series, lngs: pd.Series) -> float:
    """Raggio di girazione in km come proxy della mobilità."""
    if len(lats) < 2:
        return 0.0
    center_lat = lats.mean()
    center_lng = lngs.mean()
    distances = [
        geodesic((la, ln), (center_lat, center_lng)).km
        for la, ln in zip(lats, lngs)
    ]
    return float(np.sqrt(np.mean(np.array(distances) ** 2)))


def _days_without_movement(loc_df: pd.DataFrame, start: datetime, end: datetime) -> int:
    """
    Stima i giorni nel periodo [start, end] in cui il cittadino
    non ha registrato spostamenti GPS.
    """
    if loc_df.empty:
        total_days = max((end - start).days, 0)
        return total_days

    dates_with_gps = set(loc_df["timestamp"].dt.date)
    total_days = max((end - start).days, 0)
    days_with_gps = len(dates_with_gps)
    return max(total_days - days_with_gps, 0)


def _unique_cities(loc_df: pd.DataFrame) -> int:
    """Numero di città distinte visitate."""
    if loc_df.empty or "city" not in loc_df.columns:
        return 0
    return int(loc_df["city"].nunique())


def _compute_age(birth_year: int | None) -> int | None:
    if birth_year is None:
        return None
    return datetime.now().year - int(birth_year)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def build_citizen_features(
    citizen_id: str,
    status: pd.DataFrame,
    users: pd.DataFrame,
    locations: pd.DataFrame,
) -> dict:
    """
    Costruisce un dizionario di feature per un singolo cittadino.

    Parameters
    ----------
    citizen_id : str
    status     : DataFrame completo (tutti i cittadini)
    users      : DataFrame indicizzato per citizen_id
    locations  : DataFrame completo (tutti i cittadini)

    Returns
    -------
    dict con feature numeriche e categoriche
    """
    # --- Filtri per il cittadino ---
    s = status[status["CitizenID"] == citizen_id].copy().sort_values("Timestamp")
    loc = locations[locations["citizen_id"] == citizen_id].copy()

    # --- Anagrafica ---
    user_row = users.loc[citizen_id] if citizen_id in users.index else {}
    birth_year = user_row.get("birth_year") if isinstance(user_row, dict) else user_row["birth_year"]
    job = user_row.get("job", "") if isinstance(user_row, dict) else user_row["job"]
    home_lat = user_row.get("home_lat", 0.0) if isinstance(user_row, dict) else user_row["home_lat"]
    home_lng = user_row.get("home_lng", 0.0) if isinstance(user_row, dict) else user_row["home_lng"]

    age = _compute_age(birth_year)
    is_retired = int("retired" in str(job).lower())
    is_elderly = int(age is not None and age >= 70)

    # --- Feature da status.csv ---
    n_events = len(s)
    mean_physical = float(s["PhysicalActivityIndex"].mean()) if n_events > 0 else 0.0
    mean_sleep = float(s["SleepQualityIndex"].mean()) if n_events > 0 else 0.0
    mean_env = float(s["EnvironmentalExposureLevel"].mean()) if n_events > 0 else 0.0

    trend_physical = _linear_trend(s["PhysicalActivityIndex"]) if n_events >= 2 else 0.0
    trend_sleep = _linear_trend(s["SleepQualityIndex"]) if n_events >= 2 else 0.0

    std_physical = float(s["PhysicalActivityIndex"].std()) if n_events >= 2 else 0.0
    std_sleep = float(s["SleepQualityIndex"].std()) if n_events >= 2 else 0.0

    # Frequenza eventi: media di giorni tra un evento e il successivo
    if n_events >= 2:
        deltas = s["Timestamp"].diff().dropna().dt.days
        mean_days_between_events = float(deltas.mean())
    else:
        mean_days_between_events = 999.0

    # Percentuale eventi per tipo
    event_counts = s["EventType"].value_counts(normalize=True)
    pct_routine = float(event_counts.get("routine check-up", 0.0))
    pct_preventive = float(event_counts.get("preventive screening", 0.0))
    pct_coaching = float(event_counts.get("lifestyle coaching session", 0.0))

    # --- Feature da locations.json ---
    rog = _radius_of_gyration(loc["lat"], loc["lng"]) if not loc.empty else 0.0
    n_unique_cities = _unique_cities(loc)

    if not s.empty:
        period_start = s["Timestamp"].min().to_pydatetime()
        period_end = s["Timestamp"].max().to_pydatetime()
    else:
        period_start = period_end = datetime.now()

    days_no_movement = _days_without_movement(loc, period_start, period_end)

    # Distanza media dalla residenza
    if not loc.empty and home_lat != 0.0:
        distances_from_home = [
            geodesic((row["lat"], row["lng"]), (home_lat, home_lng)).km
            for _, row in loc.iterrows()
        ]
        mean_dist_from_home = float(np.mean(distances_from_home))
        max_dist_from_home = float(np.max(distances_from_home))
    else:
        mean_dist_from_home = 0.0
        max_dist_from_home = 0.0

    # --- Score di rischio euristico (0..100) ---
    # Usato come feature aggiuntiva e come fallback senza LLM
    risk_score = _heuristic_risk_score(
        age=age,
        mean_physical=mean_physical,
        mean_sleep=mean_sleep,
        trend_physical=trend_physical,
        trend_sleep=trend_sleep,
        days_no_movement=days_no_movement,
        rog=rog,
        mean_days_between_events=mean_days_between_events,
    )

    return {
        "citizen_id": citizen_id,
        # Anagrafica
        "age": age,
        "job": str(job),
        "is_retired": is_retired,
        "is_elderly": is_elderly,
        # Status
        "n_events": n_events,
        "mean_physical_activity": round(mean_physical, 2),
        "mean_sleep_quality": round(mean_sleep, 2),
        "mean_env_exposure": round(mean_env, 2),
        "trend_physical_activity": round(trend_physical, 4),
        "trend_sleep_quality": round(trend_sleep, 4),
        "std_physical_activity": round(std_physical, 2),
        "std_sleep_quality": round(std_sleep, 2),
        "mean_days_between_events": round(mean_days_between_events, 1),
        "pct_routine_checkup": round(pct_routine, 3),
        "pct_preventive_screening": round(pct_preventive, 3),
        "pct_lifestyle_coaching": round(pct_coaching, 3),
        # Locations
        "radius_of_gyration_km": round(rog, 2),
        "unique_cities_visited": n_unique_cities,
        "days_without_movement": days_no_movement,
        "mean_dist_from_home_km": round(mean_dist_from_home, 2),
        "max_dist_from_home_km": round(max_dist_from_home, 2),
        # Euristico
        "heuristic_risk_score": round(risk_score, 1),
    }


def _heuristic_risk_score(
    age: int | None,
    mean_physical: float,
    mean_sleep: float,
    trend_physical: float,
    trend_sleep: float,
    days_no_movement: int,
    rog: float,
    mean_days_between_events: float,
) -> float:
    """
    Calcola un punteggio di rischio euristico tra 0 e 100.
    Soglie calibrate empiricamente sul dominio del problema.
    """
    score = 0.0

    # Età (più anziano = più vulnerabile)
    if age is not None:
        if age >= 85:
            score += 25
        elif age >= 70:
            score += 15
        elif age >= 60:
            score += 8

    # Attività fisica bassa
    if mean_physical < 30:
        score += 20
    elif mean_physical < 45:
        score += 10

    # Qualità del sonno bassa
    if mean_sleep < 40:
        score += 20
    elif mean_sleep < 55:
        score += 10

    # Trend negativo
    if trend_physical < -0.05:
        score += 10
    if trend_sleep < -0.05:
        score += 10

    # Isolamento (pochi spostamenti)
    if days_no_movement > 200:
        score += 15
    elif days_no_movement > 100:
        score += 8

    # Mobilità molto ridotta
    if rog < 2.0 and rog > 0:
        score += 10
    elif rog == 0.0:
        score += 5

    # Eventi molto radi (monitoraggio discontinuo)
    if mean_days_between_events > 45:
        score += 5

    return min(score, 100.0)


def build_all_features(
    citizen_ids: list[str],
    status: pd.DataFrame,
    users: pd.DataFrame,
    locations: pd.DataFrame,
) -> list[dict]:
    """Costruisce le feature per tutti i cittadini."""
    return [
        build_citizen_features(cid, status, users, locations)
        for cid in citizen_ids
    ]
