"""
Servicio LLM — conecta GlucoseInterpreter con la API FastAPI.
Singleton del intérprete + cache de resúmenes diarios en DuckDB.
"""

import logging
import os
from datetime import date
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("llm-service")

# Variables de entorno para Azure OpenAI
_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

_interpreter: Optional[Any] = None


def is_llm_configured() -> bool:
    """Retorna True si las credenciales de Azure OpenAI estan configuradas."""
    return bool(_API_KEY and _ENDPOINT)


def get_interpreter() -> Any:
    """Singleton del GlucoseInterpreter. Lanza error si no esta configurado."""
    global _interpreter
    if _interpreter is not None:
        return _interpreter

    if not is_llm_configured():
        raise RuntimeError(
            "Azure OpenAI no configurado. Setear AZURE_OPENAI_API_KEY y "
            "AZURE_OPENAI_ENDPOINT en el .env"
        )

    # Import local para no romper la app si openai no esta instalado
    from llm.interpreter import GlucoseInterpreter

    _interpreter = GlucoseInterpreter(
        api_key=_API_KEY,
        endpoint=_ENDPOINT,
        deployment=_DEPLOYMENT,
        api_version=_API_VERSION,
    )
    logger.info("GlucoseInterpreter inicializado (deployment=%s)", _DEPLOYMENT)
    return _interpreter


def interpret_daily(summary_data: dict[str, Any]) -> str:
    """
    Genera interpretacion clinica de un resumen diario.
    Lanza excepcion si falla para que el router la maneje.
    """
    interpreter = get_interpreter()
    return interpreter.interpret_daily_summary(summary_data)


def generate_report(
    period_data: dict[str, Any],
    include_recommendations: bool = True,
) -> dict[str, Any]:
    """
    Genera informe medico completo para un periodo.
    Retorna dict con secciones del informe.
    """
    interpreter = get_interpreter()
    return interpreter.generate_medical_report(
        period_data=period_data,
        include_recommendations=include_recommendations,
    )


def detect_patterns(weekly_data: list[dict[str, Any]]) -> list[str]:
    """Detecta patrones clinicos en datos semanales."""
    try:
        interpreter = get_interpreter()
        return interpreter.detect_patterns(weekly_data)
    except Exception as exc:
        logger.error("Error en detect_patterns: %s", exc)
        return []


def chat_answer(
    question: str,
    glucose_context: dict[str, Any],
    conversation_history: list[dict[str, str]],
    channel: str = "dashboard",
) -> str:
    """
    Responde una pregunta del usuario con contexto clinico + glucemico.

    Args:
        channel: 'telegram' para chat directo con la paciente (más conciso,
                 preguntas proactivas). 'dashboard' para el modo completo.
    """
    interpreter = get_interpreter()
    return interpreter.answer_question(
        question=question,
        glucose_context=glucose_context,
        conversation_history=conversation_history,
        channel=channel,
    )


def process_conversation_batch(messages: list[dict]) -> dict:
    """
    Procesa un batch de mensajes del bot de Telegram:
    genera resumen + extrae notas clínicas de la paciente.

    Llamado por el bot cuando una sesión expira (cleanup_job cada 10 min).
    Retorna {"summary": "...", "notes": [{"content": "...", "type": "..."}]}.
    """
    interpreter = get_interpreter()
    summary = interpreter.summarize_conversation(messages)
    notes = interpreter.extract_patient_notes(messages)
    return {"summary": summary, "notes": notes}


def get_cached_llm_summary(target_date: date) -> Optional[str]:
    """Lee el llm_summary cacheado de daily_summaries."""
    from api.services.db import get_connection
    con = get_connection()
    try:
        row = con.execute(
            "SELECT llm_summary FROM daily_summaries WHERE date = ?",
            [target_date],
        ).fetchone()
        return row[0] if row and row[0] else None
    finally:
        con.close()


def cache_llm_summary(target_date: date, summary_text: str) -> None:
    """Guarda el llm_summary en daily_summaries (UPDATE, no INSERT)."""
    from api.services.db import get_connection
    con = get_connection(read_only=False)
    try:
        con.execute(
            "UPDATE daily_summaries SET llm_summary = ? WHERE date = ?",
            [summary_text, target_date],
        )
    finally:
        con.close()
