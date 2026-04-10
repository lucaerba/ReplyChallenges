"""
LangChain Tools — funzioni che gli agenti possono invocare autonomamente.

Ogni tool legge da un DataStore globale inizializzato dall'orchestratore.
Gli agenti decidono autonomamente quali tool invocare e in quale ordine.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from geopy.distance import geodesic
from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# DataStore globale — inizializzato da orchestrator.init_data_store()
# ---------------------------------------------------------------------------
_store: dict = {}


def init_data_store(data: dict) -> None:
    """Carica i dati nel DataStore globale. Chiamato una volta dall'orchestratore."""
    global _store
    _store = data


# ---------------------------------------------------------------------------
# Tool 1 — Status history
# ---------------------------------------------------------------------------

@tool
def get_status_history(citizen_id: str) -> str:
    """
    Retrieve the full well-being monitoring history for a citizen.
    Returns physical activity index, sleep quality index, environmental exposure,
    and event types over time. Use this as a first step to understand the citizen's
    health trajectory.
    """
    status: pd.DataFrame = _store.get("status", pd.DataFrame())
    df = status[status["CitizenID"] == citizen_id].sort_values("Timestamp")

    if df.empty:
        return f"No monitoring records found for citizen {citizen_id}."

    mean_physical = df["PhysicalActivityIndex"].mean()
    mean_sleep = df["SleepQualityIndex"].mean()
    mean_env = df["EnvironmentalExposureLevel"].mean()

    timeline = "\n".join(
        f"  [{row['Timestamp'].strftime('%Y-%m-%d')}] "
        f"{row['EventType']} | "
        f"Physical={row['PhysicalActivityIndex']} | "
        f"Sleep={row['SleepQualityIndex']} | "
        f"Env={row['EnvironmentalExposureLevel']}"
        for _, row in df.iterrows()
    )

    return (
        f"=== Status History: {citizen_id} ({len(df)} events) ===\n"
        f"Summary: Physical={mean_physical:.1f}/100 | Sleep={mean_sleep:.1f}/100 | Env={mean_env:.1f}/100\n"
        f"Period: {df['Timestamp'].min().date()} → {df['Timestamp'].max().date()}\n\n"
        f"Timeline:\n{timeline}"
    )


# ---------------------------------------------------------------------------
# Tool 2 — Metric trend
# ---------------------------------------------------------------------------

@tool
def compute_metric_trend(citizen_id: str, metric: str) -> str:
    """
    Compute the temporal trend for a specific health metric over time.
    metric must be one of: PhysicalActivityIndex, SleepQualityIndex, EnvironmentalExposureLevel.
    Returns direction (IMPROVING / DECLINING / STABLE), slope, and early-vs-recent comparison.
    Use this after get_status_history to understand if the situation is getting better or worse.
    """
    valid_metrics = ["PhysicalActivityIndex", "SleepQualityIndex", "EnvironmentalExposureLevel"]
    if metric not in valid_metrics:
        return f"Invalid metric '{metric}'. Choose from: {valid_metrics}"

    status: pd.DataFrame = _store.get("status", pd.DataFrame())
    df = status[status["CitizenID"] == citizen_id].sort_values("Timestamp")

    if df.empty:
        return f"No data for citizen {citizen_id}."
    if len(df) < 2:
        return f"Only 1 event — cannot compute trend for {citizen_id}."

    values = df[metric].values.astype(float)
    x = np.arange(len(values), dtype=float)
    x -= x.mean()
    y = values - values.mean()
    slope = float(np.dot(x, y) / ((x ** 2).sum() or 1.0))

    if slope > 0.05:
        direction = "IMPROVING ↑"
    elif slope < -0.05:
        direction = "DECLINING ↓"
    else:
        direction = "STABLE →"

    half = max(len(values) // 2, 1)
    early_mean = values[:half].mean()
    recent_mean = values[-half:].mean()
    delta = recent_mean - early_mean
    pct = (delta / early_mean * 100) if early_mean != 0 else 0.0

    return (
        f"=== Trend: {metric} for {citizen_id} ===\n"
        f"Direction: {direction} (slope={slope:+.4f}/event)\n"
        f"Early period mean : {early_mean:.1f}\n"
        f"Recent period mean: {recent_mean:.1f}\n"
        f"Change: {delta:+.1f} ({pct:+.1f}%)"
    )


# ---------------------------------------------------------------------------
# Tool 3 — Mobility summary
# ---------------------------------------------------------------------------

@tool
def get_mobility_summary(citizen_id: str) -> str:
    """
    Get GPS-based mobility and movement patterns for a citizen.
    Returns radius of gyration (overall movement range), unique cities visited,
    days with GPS tracking, and distance from home. Use this to detect isolation,
    reduced mobility, or travel changes.
    """
    locations: pd.DataFrame = _store.get("locations", pd.DataFrame())
    users: pd.DataFrame = _store.get("users", pd.DataFrame())

    loc = locations[locations["citizen_id"] == citizen_id].copy()
    if loc.empty:
        return f"No GPS data available for citizen {citizen_id}."

    # Radius of gyration
    center_lat, center_lng = loc["lat"].mean(), loc["lng"].mean()
    dists = [
        geodesic((la, ln), (center_lat, center_lng)).km
        for la, ln in zip(loc["lat"], loc["lng"])
    ]
    rog = float(np.sqrt(np.mean(np.array(dists) ** 2)))

    # Days with GPS
    days_with_gps = int(loc["timestamp"].dt.date.nunique())

    # Unique cities
    unique_cities = int(loc["city"].nunique()) if "city" in loc.columns else 0
    top_cities = (
        loc["city"].value_counts().head(3).to_dict()
        if "city" in loc.columns
        else {}
    )

    # Distance from home
    home_lat = home_lng = None
    if citizen_id in users.index:
        u = users.loc[citizen_id]
        home_lat = float(u.get("home_lat", 0) or 0)
        home_lng = float(u.get("home_lng", 0) or 0)

    if home_lat and home_lat != 0.0:
        dists_home = [
            geodesic((la, ln), (home_lat, home_lng)).km
            for la, ln in zip(loc["lat"], loc["lng"])
        ]
        mean_dist = float(np.mean(dists_home))
        max_dist = float(np.max(dists_home))
        home_info = f"Mean distance from home: {mean_dist:.1f} km | Max: {max_dist:.1f} km"
    else:
        home_info = "Home coordinates unavailable."

    mobility_label = (
        "LOW" if rog < 3.0
        else "MODERATE" if rog < 15.0
        else "HIGH"
    )

    return (
        f"=== Mobility: {citizen_id} ===\n"
        f"Mobility level: {mobility_label}\n"
        f"Radius of gyration: {rog:.2f} km\n"
        f"Days with GPS records: {days_with_gps}\n"
        f"Unique cities visited: {unique_cities} → {top_cities}\n"
        f"{home_info}"
    )


# ---------------------------------------------------------------------------
# Tool 4 — Demographics & persona
# ---------------------------------------------------------------------------

@tool
def get_demographics(citizen_id: str) -> str:
    """
    Get demographic information and the behavioral persona profile for a citizen.
    Returns age, occupation, residence city, and a narrative behavioral description.
    Use this to contextualize health data with personal circumstances and lifestyle.
    """
    users: pd.DataFrame = _store.get("users", pd.DataFrame())
    personas: dict = _store.get("personas", {})

    demo = ""
    if citizen_id in users.index:
        u = users.loc[citizen_id]
        birth_year = u.get("birth_year")
        age = (datetime.now().year - int(birth_year)) if birth_year else "Unknown"
        demo = (
            f"Name    : {u.get('first_name', '')} {u.get('last_name', '')}\n"
            f"Age     : {age}\n"
            f"Job     : {u.get('job', 'Unknown')}\n"
            f"City    : {u.get('city', 'Unknown')}\n"
        )
    else:
        demo = f"No user record found for {citizen_id}.\n"

    persona_text = personas.get(citizen_id, "No behavioral profile available.")

    return (
        f"=== Demographics: {citizen_id} ===\n"
        f"{demo}\n"
        f"Behavioral Profile:\n{persona_text}"
    )


# ---------------------------------------------------------------------------
# Tool 5 — Population comparison
# ---------------------------------------------------------------------------

@tool
def compare_to_population(citizen_id: str) -> str:
    """
    Compare a citizen's health metrics to the population average.
    Returns z-scores and deviation labels (BELOW AVERAGE, AVERAGE, ABOVE AVERAGE)
    for each metric. Use this to understand if the citizen is an outlier.
    """
    status: pd.DataFrame = _store.get("status", pd.DataFrame())
    if status.empty:
        return "No population data available."

    cit_data = status[status["CitizenID"] == citizen_id]
    if cit_data.empty:
        return f"No data for citizen {citizen_id}."

    metrics = ["PhysicalActivityIndex", "SleepQualityIndex", "EnvironmentalExposureLevel"]
    lines = [f"=== Population Comparison: {citizen_id} ==="]

    for m in metrics:
        pop_mean = status[m].mean()
        pop_std = status[m].std() or 1.0
        cit_mean = cit_data[m].mean()
        z = (cit_mean - pop_mean) / pop_std

        if z < -1.5:
            label = "⚠ SIGNIFICANTLY BELOW AVERAGE"
        elif z < -0.5:
            label = "↓ BELOW AVERAGE"
        elif z > 1.5:
            label = "✓ SIGNIFICANTLY ABOVE AVERAGE"
        elif z > 0.5:
            label = "↑ ABOVE AVERAGE"
        else:
            label = "= AVERAGE"

        lines.append(
            f"  {m}: citizen={cit_mean:.1f} | "
            f"pop_mean={pop_mean:.1f} ± {pop_std:.1f} | "
            f"z={z:+.2f} → {label}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6 — Population overview (for supervisor)
# ---------------------------------------------------------------------------

@tool
def get_population_overview() -> str:
    """
    Get a statistical overview of ALL citizens in the dataset.
    Returns per-citizen averages, population statistics, and age distribution.
    Use this to understand the overall population context before making final decisions.
    This tool is especially useful for the population supervisor agent.
    """
    status: pd.DataFrame = _store.get("status", pd.DataFrame())
    users: pd.DataFrame = _store.get("users", pd.DataFrame())

    if status.empty:
        return "No population data."

    n_citizens = int(status["CitizenID"].nunique())
    metrics = ["PhysicalActivityIndex", "SleepQualityIndex", "EnvironmentalExposureLevel"]

    lines = [f"=== Population Overview ({n_citizens} citizens) ===\n"]

    lines.append("Global Statistics:")
    for m in metrics:
        lines.append(
            f"  {m}: "
            f"mean={status[m].mean():.1f} | "
            f"std={status[m].std():.1f} | "
            f"p25={status[m].quantile(0.25):.1f} | "
            f"p75={status[m].quantile(0.75):.1f}"
        )

    lines.append("\nPer-Citizen Summary:")
    for cid in sorted(status["CitizenID"].unique()):
        cit = status[status["CitizenID"] == cid]
        age_str = ""
        if cid in users.index:
            by = users.loc[cid].get("birth_year")
            if by:
                age_str = f" age={datetime.now().year - int(by)}"
        lines.append(
            f"  {cid}{age_str}: "
            f"physical={cit['PhysicalActivityIndex'].mean():.1f} | "
            f"sleep={cit['SleepQualityIndex'].mean():.1f} | "
            f"n_events={len(cit)}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Esporta la lista completa dei tool per gli agenti
# ---------------------------------------------------------------------------

CITIZEN_TOOLS = [
    get_status_history,
    compute_metric_trend,
    get_mobility_summary,
    get_demographics,
    compare_to_population,
]

SUPERVISOR_TOOLS = [
    get_population_overview,
    get_status_history,
    compare_to_population,
    get_demographics,
]
