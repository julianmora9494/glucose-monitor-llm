"""
Router: métricas clínicas AGP (Ambulatory Glucose Profile).
Estándar internacional para evaluación de control glucémico.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.services.db import get_readings_by_date, get_daily_summaries, get_connection
from api.services.metrics import calculate_daily_metrics, interpret_metrics
from api.services.chart import generate_daily_chart

router = APIRouter()


class DailySummary(BaseModel):
    """Métricas AGP para un día completo con interpretación clínica."""
    date: str
    reading_count: int
    avg_glucose_mgdl: float
    std_glucose_mgdl: float
    cv_percent: float
    tir_percent: float
    tar_percent: float
    tbr_percent: float
    tbr_severe_percent: float
    gmi_percent: float
    mage_mgdl: Optional[float]
    hypo_episodes: int
    hyper_episodes: int
    min_glucose_mgdl: float
    max_glucose_mgdl: float
    status: dict                    # {"tir": "ok", "cv": "warning", ...}
    has_chart: bool                 # Si existe el chart PNG del día


class WeeklySummary(BaseModel):
    """Resumen semanal con métricas consolidadas y tendencia."""
    week_start: str
    week_end: str
    days_with_data: int
    avg_tir_percent: float
    avg_glucose_mgdl: float
    avg_cv_percent: float
    gmi_percent: float              # GMI del promedio semanal
    total_hypo_episodes: int
    total_hyper_episodes: int
    days: list[DailySummary]


def _build_daily_summary(target_date: date) -> Optional[DailySummary]:
    """Calcula o recupera el resumen AGP de un día."""
    df = get_readings_by_date(target_date)
    if df.empty or len(df) < 3:
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    metrics = calculate_daily_metrics(df)
    if not metrics:
        return None

    status = interpret_metrics(metrics)
    chart_path = Path("charts") / f"glucose_{target_date}.png"

    return DailySummary(
        date=str(target_date),
        reading_count=metrics["reading_count"],
        avg_glucose_mgdl=metrics["avg_glucose"],
        std_glucose_mgdl=metrics["std_glucose"],
        cv_percent=metrics["cv_percent"],
        tir_percent=metrics["tir_percent"],
        tar_percent=metrics["tar_percent"],
        tbr_percent=metrics["tbr_percent"],
        tbr_severe_percent=metrics["tbr_severe_percent"],
        gmi_percent=metrics["gmi_percent"],
        mage_mgdl=metrics.get("mage_mgdl"),
        hypo_episodes=metrics["hypo_episodes"],
        hyper_episodes=metrics["hyper_episodes"],
        min_glucose_mgdl=metrics["min_glucose"],
        max_glucose_mgdl=metrics["max_glucose"],
        status=status,
        has_chart=chart_path.exists(),
    )


@router.get("/day/{summary_date}", response_model=DailySummary)
def get_daily_summary(summary_date: date) -> DailySummary:
    """
    Calcula métricas AGP completas para un día.
    Incluye interpretación clínica (ok/warning/alert) de cada métrica.
    """
    summary = _build_daily_summary(summary_date)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sin datos suficientes para {summary_date} (mínimo 3 lecturas requeridas)"
        )
    return summary


@router.get("/weekly", response_model=WeeklySummary)
def get_weekly_summary(end_date: Optional[date] = None) -> WeeklySummary:
    """
    Resumen de los últimos 7 días con métricas consolidadas.
    Muestra progresión del TIR, variabilidad y episodios.
    """
    end = end_date or date.today()
    start = end - timedelta(days=6)

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        summary = _build_daily_summary(d)
        if summary:
            days.append(summary)

    if not days:
        raise HTTPException(
            status_code=404,
            detail=f"Sin datos para el período {start} — {end}"
        )

    avg_tir = round(sum(d.tir_percent for d in days) / len(days), 1)
    avg_glucose = round(sum(d.avg_glucose_mgdl for d in days) / len(days), 1)
    avg_cv = round(sum(d.cv_percent for d in days) / len(days), 1)
    gmi = round(3.31 + 0.02392 * avg_glucose, 2)

    return WeeklySummary(
        week_start=str(start),
        week_end=str(end),
        days_with_data=len(days),
        avg_tir_percent=avg_tir,
        avg_glucose_mgdl=avg_glucose,
        avg_cv_percent=avg_cv,
        gmi_percent=gmi,
        total_hypo_episodes=sum(d.hypo_episodes for d in days),
        total_hyper_episodes=sum(d.hyper_episodes for d in days),
        days=days,
    )


@router.get("/chart/{chart_date}")
def get_chart(chart_date: date, force: bool = False) -> FileResponse:
    """
    Retorna el chart AGP del día como imagen PNG.
    Si no existe lo genera; si ya existe lo sirve directamente.
    Parámetro force=true para regenerar aunque ya exista.
    """
    path = generate_daily_chart(chart_date, force=force)

    if path is None or not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Sin datos suficientes para generar el chart de {chart_date}"
        )

    return FileResponse(
        path=str(path),
        media_type="image/png",
        filename=f"glucosa_{chart_date}.png",
    )


@router.get("/available-dates")
def get_available_dates() -> list[str]:
    """
    Retorna las fechas que tienen datos registrados.
    Usado por el selector de fecha en el dashboard.
    """
    con = get_connection()
    try:
        rows = con.execute("""
            SELECT DISTINCT CAST(timestamp AT TIME ZONE 'America/Bogota' AS DATE) as day
            FROM readings
            ORDER BY day DESC
            LIMIT 90
        """).fetchall()
    finally:
        con.close()

    return [str(r[0]) for r in rows]
