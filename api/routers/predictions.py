"""
Router: predicciones glucémicas a corto plazo.
Usa regresión lineal sobre la tendencia reciente para estimar
el nivel de glucosa en los próximos 15-30 minutos.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class GlucosePrediction(BaseModel):
    current_glucose_mgdl: float
    predicted_15min_mgdl: float
    predicted_30min_mgdl: float
    confidence: str                  # "alta", "media", "baja"
    alert: str | None                # Alerta preventiva si se predice cruzar umbral
    trend_description: str           # "bajando rápido", "estable", "subiendo", etc.


@router.get("/next30min", response_model=GlucosePrediction)
def predict_next_30min() -> GlucosePrediction:
    """
    Predice glucosa a 15 y 30 minutos basado en las últimas lecturas.
    Permite alertas PREVENTIVAS antes de cruzar umbrales.
    """
    # TODO: implementar con modelo de predicción
    raise HTTPException(status_code=501, detail="Not implemented yet")
