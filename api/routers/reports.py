"""
Router: generacion de informes medicos con Azure OpenAI.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services.db import get_readings_by_date
from api.services.metrics import calculate_daily_metrics
from api.services.llm_service import (
    is_llm_configured,
    generate_report,
    interpret_daily,
    detect_patterns,
    get_cached_llm_summary,
    cache_llm_summary,
)

logger = logging.getLogger("reports-router")
router = APIRouter()


class MedicalReportRequest(BaseModel):
    date_from: date
    date_to: date
    include_recommendations: bool = True
    language: str = "es"


class MedicalReportResponse(BaseModel):
    period: str
    executive_summary: str
    glycemic_control: str
    patterns_detected: list[str]
    recommendations: list[str]
    for_physician: str
    generated_at: str


class DailyInterpretation(BaseModel):
    date: str
    interpretation: str
    cached: bool


@router.get("/llm-status")
def llm_status() -> dict[str, bool]:
    """Verifica si Azure OpenAI esta configurado."""
    return {"configured": is_llm_configured()}


@router.post("/generate", response_model=MedicalReportResponse)
def generate_medical_report(request: MedicalReportRequest) -> MedicalReportResponse:
    """
    Genera un informe medico completo usando Azure OpenAI.
    Combina metricas AGP con historial clinico de la paciente.
    """
    if not is_llm_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI no configurado. Agregar AZURE_OPENAI_API_KEY y AZURE_OPENAI_ENDPOINT al .env",
        )

    if (request.date_to - request.date_from).days > 30:
        raise HTTPException(status_code=400, detail="Rango maximo de 30 dias")
    if request.date_to < request.date_from:
        raise HTTPException(status_code=400, detail="Fecha final debe ser mayor que la inicial")

    # Recopilar metricas diarias del periodo
    daily_metrics: list[dict] = []
    current = request.date_from
    while current <= request.date_to:
        df = get_readings_by_date(current)
        if not df.empty and len(df) >= 3:
            metrics = calculate_daily_metrics(df)
            if metrics:
                metrics["date"] = str(current)
                daily_metrics.append(metrics)
        current += timedelta(days=1)

    if not daily_metrics:
        raise HTTPException(
            status_code=404,
            detail=f"Sin datos suficientes en el periodo {request.date_from} - {request.date_to}",
        )

    # Construir datos del periodo para el LLM
    period_data = {
        "date_from": str(request.date_from),
        "date_to": str(request.date_to),
        "days_with_data": len(daily_metrics),
        "daily_summaries": daily_metrics,
        "period_averages": {
            "avg_glucose": round(sum(d["avg_glucose"] for d in daily_metrics) / len(daily_metrics), 1),
            "avg_tir": round(sum(d["tir_percent"] for d in daily_metrics) / len(daily_metrics), 1),
            "avg_tar": round(sum(d["tar_percent"] for d in daily_metrics) / len(daily_metrics), 1),
            "avg_tbr": round(sum(d["tbr_percent"] for d in daily_metrics) / len(daily_metrics), 1),
            "avg_cv": round(sum(d["cv_percent"] for d in daily_metrics) / len(daily_metrics), 1),
            "total_hypo": sum(d["hypo_episodes"] for d in daily_metrics),
            "total_hyper": sum(d["hyper_episodes"] for d in daily_metrics),
        },
    }

    try:
        result = generate_report(
            period_data=period_data,
            include_recommendations=request.include_recommendations,
        )
    except Exception as exc:
        logger.error("Error generando informe: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error del LLM: {exc}")

    return MedicalReportResponse(
        period=f"{request.date_from} a {request.date_to}",
        executive_summary=result.get("executive_summary", ""),
        glycemic_control=result.get("glycemic_control", ""),
        patterns_detected=result.get("patterns_detected", []),
        recommendations=result.get("recommendations", []),
        for_physician=result.get("for_physician", ""),
        generated_at=datetime.now().isoformat(),
    )


@router.get("/daily-interpretation/{target_date}", response_model=DailyInterpretation)
def get_daily_interpretation(
    target_date: date,
    force: bool = Query(False, description="Forzar regeneracion (ignorar cache)"),
) -> DailyInterpretation:
    """
    Interpretacion clinica de un dia con IA.
    Usa cache en daily_summaries.llm_summary para no re-generar.
    """
    if not is_llm_configured():
        raise HTTPException(status_code=503, detail="Azure OpenAI no configurado")

    # Verificar cache primero
    if not force:
        cached = get_cached_llm_summary(target_date)
        if cached:
            return DailyInterpretation(
                date=str(target_date),
                interpretation=cached,
                cached=True,
            )

    # Calcular metricas del dia
    df = get_readings_by_date(target_date)
    if df.empty or len(df) < 3:
        raise HTTPException(
            status_code=404,
            detail=f"Sin datos suficientes para {target_date}",
        )

    metrics = calculate_daily_metrics(df)
    if not metrics:
        raise HTTPException(status_code=404, detail="No se pudieron calcular metricas")

    metrics["date"] = str(target_date)

    # Llamar al LLM
    try:
        interpretation = interpret_daily(metrics)
    except Exception as exc:
        logger.error("Error en interpretacion diaria: %s", exc)
        raise HTTPException(status_code=500, detail=f"Error del LLM: {exc}")

    if not interpretation:
        raise HTTPException(status_code=500, detail="El LLM no genero respuesta")

    # Cachear en DB
    try:
        cache_llm_summary(target_date, interpretation)
    except Exception as exc:
        logger.warning("No se pudo cachear llm_summary: %s", exc)

    return DailyInterpretation(
        date=str(target_date),
        interpretation=interpretation,
        cached=False,
    )


@router.get("/pdf/{report_date}")
def generate_pdf_report(report_date: date) -> dict[str, str]:
    """
    Genera un PDF del informe medico (Fase 6).
    """
    raise HTTPException(status_code=501, detail="PDF export pendiente — Fase 6")
