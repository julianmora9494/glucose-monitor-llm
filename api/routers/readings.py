"""
Router: lecturas de glucosa en tiempo real e históricas.
"""

from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# TODO: importar servicio de base de datos cuando se implemente db.py

router = APIRouter()


class GlucoseReading(BaseModel):
    timestamp: str
    glucose_mgdl: float
    trend: str | None
    delta_mgdl: float | None
    slope_mgdl_min: float | None
    range_type: str


@router.get("/latest", response_model=GlucoseReading | None)
def get_latest_reading() -> GlucoseReading | None:
    """Retorna la lectura más reciente de glucosa."""
    # TODO: implementar con DuckDB
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/day/{reading_date}")
def get_readings_by_day(reading_date: date) -> list[GlucoseReading]:
    """Retorna todas las lecturas de un día específico."""
    # TODO: implementar con DuckDB
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/range")
def get_readings_range(start: date, end: date) -> list[GlucoseReading]:
    """Retorna lecturas en un rango de fechas (máx 30 días)."""
    if (end - start).days > 30:
        raise HTTPException(status_code=400, detail="Rango máximo de 30 días")
    # TODO: implementar con DuckDB
    raise HTTPException(status_code=501, detail="Not implemented yet")
