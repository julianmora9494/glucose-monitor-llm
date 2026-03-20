"""
Router: lecturas de glucosa en tiempo real e históricas.
"""

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services.db import get_latest_reading, get_readings_by_date, get_connection

router = APIRouter()


class GlucoseReading(BaseModel):
    timestamp: str
    glucose_mgdl: float
    trend: Optional[str]
    delta_mgdl: Optional[float]
    slope_mgdl_min: Optional[float]
    range_type: str

    model_config = {"from_attributes": True}


class LatestReading(BaseModel):
    """Lectura más reciente con contexto clínico."""
    timestamp: str
    glucose_mgdl: float
    trend: Optional[str]
    trend_description: str          # "bajando", "estable", "subiendo", etc.
    delta_mgdl: Optional[float]
    slope_mgdl_min: Optional[float]
    range_type: str
    range_label: str                # "En rango", "Hipoglucemia", "Hiperglucemia", etc.
    minutes_ago: float
    alert_level: str                # "ok", "warning", "critical"


def _trend_description(trend: Optional[str], slope: Optional[float]) -> str:
    """Convierte el código de tendencia del sensor en texto legible."""
    if slope is not None:
        if slope <= -2.0:
            return "bajando rápido ↓↓"
        if slope <= -1.0:
            return "bajando ↓"
        if slope >= 2.0:
            return "subiendo rápido ↑↑"
        if slope >= 1.0:
            return "subiendo ↑"
        return "estable →"
    trend_map = {
        "1": "bajando rápido ↓↓",
        "2": "bajando ↓",
        "3": "estable →",
        "4": "subiendo ↑",
        "5": "subiendo rápido ↑↑",
    }
    return trend_map.get(str(trend), "sin tendencia")


def _range_label(range_type: str, glucose: float) -> str:
    """Etiqueta clínica legible del rango de glucosa."""
    labels = {
        "very_low": "Hipoglucemia severa (<54)",
        "low": "Hipoglucemia (<70)",
        "normal": "En rango (70-180)",
        "high": "Hiperglucemia (>180)",
        "very_high": "Hiperglucemia severa (>250)",
    }
    return labels.get(range_type, "Desconocido")


def _alert_level(range_type: str) -> str:
    if range_type in ("very_low", "very_high"):
        return "critical"
    if range_type in ("low", "high"):
        return "warning"
    return "ok"


@router.get("/latest", response_model=Optional[LatestReading])
def get_latest() -> Optional[LatestReading]:
    """
    Retorna la lectura más reciente con contexto clínico completo.
    Usado por el dashboard para el panel de tiempo real.
    """
    row = get_latest_reading()
    if row is None:
        return None

    ts = pd.to_datetime(row["timestamp"])
    now = pd.Timestamp.now(tz="UTC")
    minutes_ago = (now - ts).total_seconds() / 60

    return LatestReading(
        timestamp=str(row["timestamp"]),
        glucose_mgdl=row["glucose_mgdl"],
        trend=row["trend"],
        trend_description=_trend_description(row["trend"], row["slope_mgdl_min"]),
        delta_mgdl=row["delta_mgdl"],
        slope_mgdl_min=row["slope_mgdl_min"],
        range_type=row["range_type"],
        range_label=_range_label(row["range_type"], row["glucose_mgdl"]),
        minutes_ago=round(minutes_ago, 1),
        alert_level=_alert_level(row["range_type"]),
    )


@router.get("/day/{reading_date}", response_model=list[GlucoseReading])
def get_by_day(reading_date: date) -> list[GlucoseReading]:
    """
    Retorna todas las lecturas de un día específico ordenadas por hora.
    Usado por el dashboard en la página de análisis diario.
    """
    df = get_readings_by_date(reading_date)
    if df.empty:
        return []

    return [
        GlucoseReading(
            timestamp=str(row["timestamp"]),
            glucose_mgdl=row["glucose_mgdl"],
            trend=row.get("trend"),
            delta_mgdl=row.get("delta_mgdl"),
            slope_mgdl_min=row.get("slope_mgdl_min"),
            range_type=row.get("range_type", "normal"),
        )
        for _, row in df.iterrows()
    ]


@router.get("/range", response_model=list[GlucoseReading])
def get_range(
    start: date = Query(..., description="Fecha inicial"),
    end: date = Query(..., description="Fecha final"),
) -> list[GlucoseReading]:
    """
    Retorna lecturas en un rango de fechas (máx 30 días).
    Usado por el dashboard para el mini-chart de las últimas horas.
    """
    if (end - start).days > 30:
        raise HTTPException(status_code=400, detail="Rango máximo de 30 días")
    if end < start:
        raise HTTPException(status_code=400, detail="La fecha final debe ser mayor que la inicial")

    con = get_connection()
    try:
        df = con.execute("""
            SELECT timestamp, glucose_mgdl, trend, delta_mgdl,
                   dt_min, slope_mgdl_min, percent_change, range_type
            FROM readings
            WHERE CAST(timestamp AS DATE) BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """, [start, end]).df()
    finally:
        con.close()

    if df.empty:
        return []

    return [
        GlucoseReading(
            timestamp=str(row["timestamp"]),
            glucose_mgdl=row["glucose_mgdl"],
            trend=row.get("trend"),
            delta_mgdl=row.get("delta_mgdl"),
            slope_mgdl_min=row.get("slope_mgdl_min"),
            range_type=row.get("range_type", "normal"),
        )
        for _, row in df.iterrows()
    ]


@router.get("/last-hours/{hours}", response_model=list[GlucoseReading])
def get_last_hours(hours: int = 3) -> list[GlucoseReading]:
    """
    Retorna lecturas de las últimas N horas.
    Usado por el mini-chart de tiempo real en el dashboard.
    """
    if hours > 24:
        raise HTTPException(status_code=400, detail="Máximo 24 horas")

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    con = get_connection()
    try:
        df = con.execute("""
            SELECT timestamp, glucose_mgdl, trend, delta_mgdl,
                   slope_mgdl_min, range_type
            FROM readings
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, [cutoff]).df()
    finally:
        con.close()

    if df.empty:
        return []

    return [
        GlucoseReading(
            timestamp=str(row["timestamp"]),
            glucose_mgdl=row["glucose_mgdl"],
            trend=row.get("trend"),
            delta_mgdl=row.get("delta_mgdl"),
            slope_mgdl_min=row.get("slope_mgdl_min"),
            range_type=row.get("range_type", "normal"),
        )
        for _, row in df.iterrows()
    ]
