"""
Router: métricas clínicas AGP (Ambulatory Glucose Profile).
Estándar internacional para evaluación de control glucémico.
"""

from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class DailySummary(BaseModel):
    """Métricas AGP para un día completo."""
    date: str
    reading_count: int
    avg_glucose_mgdl: float
    std_glucose_mgdl: float
    cv_percent: float                 # Coeficiente de variación (objetivo <36%)
    tir_percent: float                # Time In Range 70-180 mg/dL (objetivo >70%)
    tar_percent: float                # Time Above Range >180 mg/dL
    tbr_percent: float                # Time Below Range <70 mg/dL
    tbr_severe_percent: float         # Time Below Range <54 mg/dL
    gmi_percent: float                # Glucose Management Indicator (estima HbA1c)
    mage_mgdl: float | None          # Mean Amplitude of Glycemic Excursions
    hypo_episodes: int                # Episodios de hipoglucemia (<70 mg/dL)
    hyper_episodes: int               # Episodios de hiperglucemia (>180 mg/dL)
    min_glucose_mgdl: float
    max_glucose_mgdl: float


class WeeklySummary(BaseModel):
    """Resumen semanal con métricas consolidadas."""
    week_start: str
    week_end: str
    days_with_data: int
    avg_tir_percent: float
    avg_glucose_mgdl: float
    avg_cv_percent: float
    estimated_hba1c_percent: float
    days: list[DailySummary]


@router.get("/day/{summary_date}", response_model=DailySummary)
def get_daily_summary(summary_date: date) -> DailySummary:
    """
    Calcula métricas AGP completas para un día.
    Este es el resumen que se envía por Telegram cada noche.
    """
    # TODO: implementar cálculo con DuckDB
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/weekly", response_model=WeeklySummary)
def get_weekly_summary(end_date: date | None = None) -> WeeklySummary:
    """Resumen de los últimos 7 días."""
    # TODO: implementar con DuckDB
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/chart/daily/{chart_date}")
def get_daily_chart(chart_date: date) -> dict[str, str]:
    """
    Genera el chart diario AGP y retorna la imagen en base64.
    Un solo chart por día (no uno por ejecución).
    """
    # TODO: implementar generación de chart con plotly
    raise HTTPException(status_code=501, detail="Not implemented yet")
