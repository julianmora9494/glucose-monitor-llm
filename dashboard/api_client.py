"""
Cliente HTTP para comunicarse con el FastAPI backend.
Todas las llamadas a la API pasan por aquí, con manejo de errores centralizado.
"""

import os
from datetime import date
from typing import Optional

import requests
from requests.exceptions import ConnectionError, Timeout

API_URL = os.getenv("API_URL", "http://localhost:8888")
TIMEOUT = 10  # segundos


def _get(path: str, params: Optional[dict] = None) -> Optional[dict | list]:
    """GET genérico con manejo de errores."""
    try:
        r = requests.get(f"{API_URL}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except ConnectionError:
        return None
    except Timeout:
        return None
    except Exception:
        return None


def is_api_online() -> bool:
    """Verifica si la API está disponible."""
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def get_latest_reading() -> Optional[dict]:
    """Última lectura de glucosa con contexto clínico."""
    return _get("/api/readings/latest")


def get_readings_day(day: date) -> list[dict]:
    """Todas las lecturas de un día."""
    result = _get(f"/api/readings/day/{day}")
    return result if isinstance(result, list) else []


def get_readings_last_hours(hours: int = 3) -> list[dict]:
    """Lecturas de las últimas N horas."""
    result = _get(f"/api/readings/last-hours/{hours}")
    return result if isinstance(result, list) else []


def get_daily_summary(day: date) -> Optional[dict]:
    """Métricas AGP de un día."""
    return _get(f"/api/summaries/day/{day}")


def get_weekly_summary(end_date: Optional[date] = None) -> Optional[dict]:
    """Resumen de los últimos 7 días."""
    params = {"end_date": str(end_date)} if end_date else None
    return _get("/api/summaries/weekly", params=params)


def get_chart_url(day: date) -> str:
    """URL del chart PNG del día."""
    return f"{API_URL}/api/summaries/chart/{day}"


def get_available_dates() -> list[str]:
    """Fechas con datos disponibles."""
    result = _get("/api/summaries/available-dates")
    return result if isinstance(result, list) else []
