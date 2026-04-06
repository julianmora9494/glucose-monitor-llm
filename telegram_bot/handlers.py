"""
Handlers de comandos y mensajes para el bot de Telegram.
Cada handler: verifica autorización → typing → llama API → formatea → responde.

Persistencia de conversaciones:
  - Los mensajes se guardan en conversations.duckdb via ConversationStore.
  - Cuando una sesión expira (TTL 30 min), se genera un resumen LLM de los
    mensajes más antiguos y se extraen notas clínicas de la paciente.
  - El contexto LLM para cada mensaje incluye: notas activas + resúmenes + mensajes recientes.
"""

import logging
from datetime import date, timezone, timedelta

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from telegram_bot import api_client
from telegram_bot.conversation import conversation_manager
from telegram_bot.memory import conversation_store
from telegram_bot.formatters import (
    format_api_error,
    format_daily_summary,
    format_help,
    format_status,
    format_weekly_summary,
    split_message,
)
from telegram_bot.security import require_auth

logger = logging.getLogger(__name__)

# Zona horaria Colombia (UTC-5, sin DST)
_TZ_BOGOTA = timezone(timedelta(hours=-5))


def _today_bogota() -> date:
    """Retorna la fecha actual en hora Colombia."""
    from datetime import datetime
    return datetime.now(_TZ_BOGOTA).date()


async def _send_parts(update: Update, text: str, parse_mode: str = "Markdown") -> None:
    """Envía texto dividiéndolo en partes si supera el límite de Telegram."""
    parts = split_message(text)
    for part in parts:
        await update.effective_message.reply_text(part, parse_mode=parse_mode)  # type: ignore[union-attr]


@require_auth
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /start — envía bienvenida e instrucciones."""
    welcome = (
        "👋 *Bienvenida al asistente de monitoreo glucémico*\n\n"
        "Puedo ayudarte a:\n"
        "• Revisar tu glucosa actual y tendencia\n"
        "• Consultar tus métricas AGP del día o la semana\n"
        "• Preguntar sobre dosificación de insulina, comidas y más\n\n"
        "Escríbeme cualquier pregunta o usa los comandos:\n"
        "/status — glucosa actual\n"
        "/resumen — resumen de hoy\n"
        "/semana — resumen semanal\n"
        "/ayuda — lista completa de comandos"
    )
    await update.effective_message.reply_text(welcome, parse_mode="Markdown")  # type: ignore[union-attr]


@require_auth
async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja /status — retorna la última lectura glucémica."""
    await update.effective_chat.send_action(ChatAction.TYPING)  # type: ignore[union-attr]

    reading = await api_client.get_latest_reading()
    if reading is None:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            format_api_error("No hay lecturas disponibles.")
        )
        return

    await _send_parts(update, format_status(reading))


@require_auth
async def resumen_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja /resumen — resumen AGP del día actual."""
    await update.effective_chat.send_action(ChatAction.TYPING)  # type: ignore[union-attr]

    today = _today_bogota()
    summary = await api_client.get_daily_summary(today)

    if summary is None:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            format_api_error(f"Sin datos suficientes para hoy ({today}).")
        )
        return

    await _send_parts(update, format_daily_summary(summary))


@require_auth
async def semana_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja /semana — resumen semanal de métricas AGP."""
    await update.effective_chat.send_action(ChatAction.TYPING)  # type: ignore[union-attr]

    summary = await api_client.get_weekly_summary()
    if summary is None:
        await update.effective_message.reply_text(  # type: ignore[union-attr]
            format_api_error("No se pudo obtener el resumen semanal.")
        )
        return

    await _send_parts(update, format_weekly_summary(summary))


@require_auth
async def ayuda_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja /ayuda — lista de comandos disponibles."""
    await update.effective_message.reply_text(format_help(), parse_mode="Markdown")  # type: ignore[union-attr]


@require_auth
async def limpiar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja /limpiar — reinicia el contexto LLM de la sesión.

    El historial en DB se preserva para auditoría y summarización futura,
    pero no se enviará al LLM hasta que se acumule nuevo historial.
    """
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    conversation_manager.clear(chat_id)
    await update.effective_message.reply_text(  # type: ignore[union-attr]
        "🔄 Conversación reiniciada. ¿En qué puedo ayudarte?"
    )


@require_auth
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja mensajes de texto libre — envía al LLM con contexto persistente.

    Contexto enviado al LLM (en orden):
      1. Notas de la paciente (hechos que Veronica reportó, pueden contradecir el perfil)
      2. Resúmenes de conversaciones anteriores (>7 días)
      3. Mensajes recientes verbatim (últimos 7 días / 40 mensajes)
      4. Pregunta actual
    """
    if not update.effective_message or not update.effective_message.text:
        return

    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    question = update.effective_message.text.strip()

    if not question:
        return

    await update.effective_chat.send_action(ChatAction.TYPING)  # type: ignore[union-attr]

    # Construir contexto enriquecido desde la DB persistente
    context_since = conversation_manager.get_context_since(chat_id)
    history = conversation_store.build_llm_context(chat_id, context_since=context_since)

    # Llamar al LLM via API
    answer = await api_client.chat_with_ai(
        question=question,
        history=history,
        channel="telegram",
    )

    if answer is None:
        await update.effective_message.reply_text(
            format_api_error("Error al comunicarse con la IA. Intenta de nuevo.")
        )
        return

    # Persistir el intercambio en conversations.duckdb
    conversation_store.save_message(chat_id, "user", question)
    conversation_store.save_message(chat_id, "assistant", answer)

    # Actualizar TTL de la sesión en memoria
    conversation_manager.touch(chat_id)

    await _send_parts(update, answer)


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job periódico que:
      1. Detecta sesiones expiradas (TTL 30 min)
      2. Para cada sesión expirada con mensajes no resumidos, llama al API
         para generar un resumen + extraer notas clínicas de la paciente
      3. Persiste resumen y notas en conversations.duckdb
      4. Elimina las sesiones expiradas de memoria

    Ejecutado por el job queue cada 10 minutos.
    """
    # Capturar sesiones expiradas ANTES de limpiarlas
    expired_sessions = conversation_manager.get_expired_sessions()
    removed = conversation_manager.cleanup_stale()

    if removed > 0:
        logger.info("Job cleanup: %d sesiones inactivas eliminadas", removed)

    # Procesar mensajes pendientes de summarización para cada sesión expirada
    for chat_id in expired_sessions:
        messages = conversation_store.get_messages_to_summarize(chat_id)

        # Mínimo 4 mensajes (2 turnos) para que tenga sentido resumir
        if len(messages) < 4:
            continue

        logger.info(
            "Resumiendo %d mensajes para chat_id=%s", len(messages), chat_id
        )

        result = await api_client.process_conversation_batch(messages)
        if not result:
            logger.warning("No se pudo resumir conversación para chat_id=%s", chat_id)
            continue

        # Guardar resumen
        period_start = messages[0]["timestamp"]
        period_end = messages[-1]["timestamp"]
        conversation_store.save_summary(
            chat_id=chat_id,
            period_start=period_start,
            period_end=period_end,
            summary=result.get("summary", ""),
            message_count=len(messages),
        )

        # Guardar notas clínicas extraídas (pueden contradecir el perfil médico)
        notes = result.get("notes", [])
        if notes:
            conversation_store.save_notes(chat_id, notes, source_date=period_end)
            logger.info(
                "%d notas clínicas extraídas para chat_id=%s", len(notes), chat_id
            )
