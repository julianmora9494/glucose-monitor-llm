"""
Cliente HTTP asíncrono para comunicarse con la API FastAPI.
Sigue el mismo patrón que dashboard/api_client.py pero usando httpx async.
"""

import logging
import os
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Timeout en segundos para llamadas a la API
_DEFAULT_TIMEOUT = 30.0
# Timeout extendido para llamadas al LLM (pueden tardar más)
_LLM_TIMEOUT = 60.0


def _base_url() -> str:
    """Retorna la URL base de la API desde variable de entorno."""
    return os.getenv("API_URL", "http://localhost:8888")


async def is_api_online() -> bool:
    """Verifica si la API FastAPI está disponible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{_base_url()}/health")
            return response.status_code == 200
    except Exception as exc:
        logger.warning("API no disponible: %s", exc)
        return False


async def get_latest_reading() -> Optional[dict]:
    """
    Obtiene la última lectura glucémica con contexto clínico.
    Retorna None si la API no responde o no hay datos.
    """
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{_base_url()}/api/readings/latest")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.info("Sin lecturas disponibles")
        else:
            logger.error("Error HTTP obteniendo última lectura: %s", exc)
        return None
    except Exception as exc:
        logger.error("Error obteniendo última lectura: %s", exc)
        return None


async def get_readings_last_hours(hours: int = 3) -> list[dict]:
    """
    Obtiene las lecturas de las últimas N horas.
    Retorna lista vacía si hay error.
    """
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{_base_url()}/api/readings/last-hours/{hours}")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Error obteniendo lecturas de últimas %s horas: %s", hours, exc)
        return []


async def get_daily_summary(target_date: date) -> Optional[dict]:
    """
    Obtiene el resumen AGP de un día específico.
    Retorna None si no hay datos suficientes o hay error.
    """
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{_base_url()}/api/summaries/day/{target_date.isoformat()}"
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.info("Sin datos AGP para %s", target_date)
        else:
            logger.error("Error HTTP obteniendo resumen de %s: %s", target_date, exc)
        return None
    except Exception as exc:
        logger.error("Error obteniendo resumen de %s: %s", target_date, exc)
        return None


async def get_weekly_summary() -> Optional[dict]:
    """
    Obtiene el resumen de los últimos 7 días.
    Retorna None si hay error.
    """
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{_base_url()}/api/summaries/weekly")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.error("Error obteniendo resumen semanal: %s", exc)
        return None


async def process_conversation_batch(messages: list[dict]) -> Optional[dict]:
    """
    Envía un batch de mensajes al API para generar resumen + extraer notas clínicas.
    Llamado por cleanup_job cuando una sesión expira.

    Retorna {"summary": "...", "notes": [...]} o None si hay error.
    """
    payload = {
        "messages": [
            {
                "role": m["role"],
                "content": m["content"],
                "timestamp": str(m.get("timestamp", "")),
            }
            for m in messages
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            response = await client.post(
                f"{_base_url()}/api/reports/process-conversation-batch",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            logger.warning("LLM no configurado — no se puede resumir conversación")
        else:
            logger.error("Error procesando batch de conversación: %s", exc)
        return None
    except Exception as exc:
        logger.error("Error procesando batch de conversación: %s", exc)
        return None


async def chat_with_ai(
    question: str,
    history: list[dict[str, str]],
    channel: str = "telegram",
) -> Optional[str]:
    """
    Envía una pregunta al LLM médico via API.
    Incluye el historial de conversación y especifica el canal 'telegram'
    para que el LLM ajuste su estilo de respuesta.

    Retorna el texto de respuesta o None si hay error.
    """
    payload = {
        "question": question,
        "conversation_history": history,
        "channel": channel,
    }
    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            response = await client.post(
                f"{_base_url()}/api/reports/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("answer")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            logger.warning("LLM no configurado en la API")
            return "⚙️ El asistente de IA no está configurado. Contacta al administrador."
        logger.error("Error HTTP en chat con IA: %s", exc)
        return None
    except httpx.TimeoutException:
        logger.warning("Timeout esperando respuesta del LLM")
        return "⏱ La respuesta tardó demasiado. Intenta de nuevo en un momento."
    except Exception as exc:
        logger.error("Error en chat con IA: %s", exc)
        return None
