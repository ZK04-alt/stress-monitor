
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from models.stress_score_cli import (
    electricity_range,
    get_latest,
    normalize,
    predict_drought,
    predict_normal_target,
    validate_files,
    water_range,
)

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"

HISTORY_PATH = MODEL_DIR / "state_model_history.csv"
METADATA_PATH = MODEL_DIR / "project_metadata.json"
METRICS_PATH = MODEL_DIR / "evaluation_metrics.json"
TRAINING_PATH = MODEL_DIR / "training_complete.json"

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

history = pd.read_csv(HISTORY_PATH, dtype={"state_fips": str})
history["state_fips"] = history["state_fips"].astype(str).str.zfill(2)
history["year"] = pd.to_numeric(history["year"], errors="raise").astype(int)

metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
training = json.loads(TRAINING_PATH.read_text(encoding="utf-8"))
validate_files(history, metadata)

LATEST_YEAR = int(metadata["latest_observed_year"])
MAX_YEAR = 2050

app = FastAPI(
    title="U.S. Infrastructure Stress Monitor",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Environment(
    loader=FileSystemLoader(BASE_DIR / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def finite_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def stress_band(score: float) -> dict[str, str]:
    if score < 25:
        return {"label": "Low", "code": "low"}
    if score < 50:
        return {"label": "Guarded", "code": "guarded"}
    if score < 75:
        return {"label": "Elevated", "code": "elevated"}
    return {"label": "Severe", "code": "severe"}


def project_state(state_abbreviation: str, future_year: int, include_series: bool = True) -> dict[str, Any]:
    state_abbreviation = state_abbreviation.upper()
    state_history = history.loc[
        history["state_abbreviation"].astype(str).str.upper() == state_abbreviation
    ].sort_values("year")

    if state_history.empty:
        raise HTTPException(status_code=404, detail="State not found.")

    boundaries = metadata["normalization_boundaries"]
    errors = metadata["backtest_rmse"]

    predicted_saidi = predict_normal_target(
        state_history, "actual_saidi", "predicted_saidi", LATEST_YEAR, future_year
    )
    predicted_saifi = predict_normal_target(
        state_history, "actual_saifi", "predicted_saifi", LATEST_YEAR, future_year
    )
    predicted_drought = predict_drought(state_history, LATEST_YEAR, future_year)
    predicted_compliance = predict_normal_target(
        state_history,
        "actual_compliance",
        "predicted_compliance",
        LATEST_YEAR,
        future_year,
    )

    duration_stress = normalize(
        predicted_saidi, boundaries["saidi"]["low"], boundaries["saidi"]["high"]
    )
    frequency_stress = normalize(
        predicted_saifi, boundaries["saifi"]["low"], boundaries["saifi"]["high"]
    )
    drought_stress = predicted_drought
    compliance_stress = normalize(
        predicted_compliance,
        boundaries["compliance"]["low"],
        boundaries["compliance"]["high"],
    )

    electricity_stress = (duration_stress + frequency_stress) / 2
    water_stress = (drought_stress + compliance_stress) / 2

    latest_saidi = get_latest(state_history, "actual_saidi")
    latest_saifi = get_latest(state_history, "actual_saifi")
    latest_drought = get_latest(state_history, "actual_drought")
    latest_compliance = get_latest(state_history, "actual_compliance")

    latest_electricity = (
        normalize(latest_saidi, boundaries["saidi"]["low"], boundaries["saidi"]["high"])
        + normalize(latest_saifi, boundaries["saifi"]["low"], boundaries["saifi"]["high"])
    ) / 2
    latest_water = (
        latest_drought
        + normalize(
            latest_compliance,
            boundaries["compliance"]["low"],
            boundaries["compliance"]["high"],
        )
    ) / 2

    years_ahead = future_year - LATEST_YEAR
    electricity_low, electricity_high = electricity_range(
        predicted_saidi,
        predicted_saifi,
        years_ahead,
        errors,
        boundaries,
    )
    water_low, water_high = water_range(
        predicted_drought,
        predicted_compliance,
        years_ahead,
        errors,
        boundaries,
    )

    result = {
        "state": {
            "abbreviation": state_abbreviation,
            "name": STATE_NAMES.get(state_abbreviation, state_abbreviation),
            "fips": str(state_history.iloc[0]["state_fips"]).zfill(2),
        },
        "year": future_year,
        "latest_observed_year": LATEST_YEAR,
        "years_ahead": years_ahead,
        "electricity": {
            "score": electricity_stress,
            "band": stress_band(electricity_stress),
            "change": electricity_stress - latest_electricity,
            "range": [electricity_low, electricity_high],
            "saidi": predicted_saidi,
            "saifi": predicted_saifi,
            "duration_stress": duration_stress,
            "frequency_stress": frequency_stress,
            "latest_score": latest_electricity,
        },
        "water": {
            "score": water_stress,
            "band": stress_band(water_stress),
            "change": water_stress - latest_water,
            "range": [water_low, water_high],
            "drought": predicted_drought,
            "compliance": predicted_compliance,
            "drought_stress": drought_stress,
            "compliance_stress": compliance_stress,
            "latest_score": latest_water,
        },
    }

    if include_series:
        historical = []
        for _, row in state_history.iterrows():
            yr = int(row["year"])
            saidi = finite_or_none(row["actual_saidi"])
            saifi = finite_or_none(row["actual_saifi"])
            drought = finite_or_none(row["actual_drought"])
            compliance = finite_or_none(row["actual_compliance"])
            electricity = None
            water = None
            if saidi is not None and saifi is not None:
                electricity = (
                    normalize(saidi, boundaries["saidi"]["low"], boundaries["saidi"]["high"])
                    + normalize(saifi, boundaries["saifi"]["low"], boundaries["saifi"]["high"])
                ) / 2
            if drought is not None and compliance is not None:
                water = (
                    drought
                    + normalize(
                        compliance,
                        boundaries["compliance"]["low"],
                        boundaries["compliance"]["high"],
                    )
                ) / 2
            historical.append(
                {
                    "year": yr,
                    "electricity": electricity,
                    "water": water,
                    "type": "observed",
                }
            )

        projected = []
        for yr in range(LATEST_YEAR + 1, future_year + 1):
            p = project_state(state_abbreviation, yr, include_series=False)
            projected.append(
                {
                    "year": yr,
                    "electricity": p["electricity"]["score"],
                    "water": p["water"]["score"],
                    "electricity_low": p["electricity"]["range"][0],
                    "electricity_high": p["electricity"]["range"][1],
                    "water_low": p["water"]["range"][0],
                    "water_high": p["water"]["range"][1],
                    "type": "projected",
                }
            )
        result["series"] = historical + projected

    return result


def rank_for_year(state_abbreviation: str, future_year: int) -> dict[str, Any]:
    rows = []
    for abbr in sorted(history["state_abbreviation"].dropna().unique()):
        projection = project_state(str(abbr), future_year, include_series=False)
        rows.append(
            {
                "state": str(abbr),
                "electricity": projection["electricity"]["score"],
                "water": projection["water"]["score"],
            }
        )

    electricity_sorted = sorted(rows, key=lambda x: x["electricity"], reverse=True)
    water_sorted = sorted(rows, key=lambda x: x["water"], reverse=True)

    electricity_rank = next(
        index + 1
        for index, row in enumerate(electricity_sorted)
        if row["state"] == state_abbreviation
    )
    water_rank = next(
        index + 1
        for index, row in enumerate(water_sorted)
        if row["state"] == state_abbreviation
    )

    return {
        "electricity": electricity_rank,
        "water": water_rank,
        "total": len(rows),
    }


def diagnostic_payload() -> list[dict[str, Any]]:
    return [
        {
            "target": "SAIDI",
            "model": metadata["best_models"]["saidi"],
            **metrics["electricity"]["saidi"]["backtest"]["state_year"],
        },
        {
            "target": "SAIFI",
            "model": metadata["best_models"]["saifi"],
            **metrics["electricity"]["saifi"]["backtest"]["state_year"],
        },
        {
            "target": "Drought",
            "model": metadata["best_models"]["drought"],
            **metrics["drought"]["backtest"]["state_year"],
        },
        {
            "target": "Compliance",
            "model": metadata["best_models"]["compliance"],
            **metrics["compliance"]["backtest"]["state_year"],
        },
    ]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    template = templates.get_template("index.html")
    return template.render(latest_year=LATEST_YEAR)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "training_status": training.get("status"),
        "latest_observed_year": LATEST_YEAR,
        "model_files_present": all(
            (MODEL_DIR / filename).exists()
            for filename in [
                "saidi_high_event_classifier.cbm",
                "saidi_high_regressor.cbm",
                "saidi_normal_regressor.cbm",
                "saifi_log_catboost.cbm",
                "drought_anova_ridge.joblib",
                "compliance_tweedie.cbm",
            ]
        ),
    }


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    states = [
        {
            "abbreviation": abbr,
            "name": STATE_NAMES.get(abbr, abbr),
        }
        for abbr in sorted(history["state_abbreviation"].dropna().unique())
    ]
    return {
        "states": states,
        "latest_year": LATEST_YEAR,
        "min_year": LATEST_YEAR + 1,
        "max_year": MAX_YEAR,
        "training": training,
        "projection": metadata["projection"],
        "warning": metadata["important_warning"],
        "best_models": metadata["best_models"],
        "main_inputs": metadata["main_historical_model_inputs"],
        "diagnostics": diagnostic_payload(),
        "software_versions": metadata.get("software_versions", {}),
    }


@app.get("/api/project")
def project(
    state: str = Query(..., min_length=2, max_length=2),
    year: int = Query(..., ge=LATEST_YEAR + 1, le=MAX_YEAR),
) -> dict[str, Any]:
    state = state.upper()
    result = project_state(state, year)
    result["rank"] = rank_for_year(state, year)
    return result
