"""
Tests de los handlers del bot de Telegram.
Usa unittest.mock para simular objetos de Telegram y el cliente API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.conversation import conversation_manager
from telegram_bot.handlers import (
    ayuda_handler,
    limpiar_handler,
    message_handler,
    resumen_handler,
    semana_handler,
    start_handler,
    status_handler,
)

pytestmark = pytest.mark.asyncio


def _make_update(chat_id: int, text: str = "") -> MagicMock:
    """Crea un mock de telegram.Update para tests."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_chat.send_action = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.text = text
    return update


def _make_context() -> MagicMock:
    """Crea un mock de ContextTypes.DEFAULT_TYPE."""
    return MagicMock()


AUTHORIZED_CHAT_ID = 111111111
UNAUTHORIZED_CHAT_ID = 999999999


# ─── Autorización ─────────────────────────────────────────────────────────────

async def test_unauthorized_user_is_rejected() -> None:
    """Un usuario no autorizado debe recibir mensaje de rechazo."""
    update = _make_update(UNAUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        await status_handler(update, context)

    # La respuesta de rechazo se envía, NO se llama a la API
    update.effective_message.reply_text.assert_called_once()
    call_args = update.effective_message.reply_text.call_args[0][0]
    assert "⛔" in call_args


async def test_authorized_user_is_allowed() -> None:
    """Un usuario autorizado no debe ser rechazado."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.get_latest_reading", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = {
                "glucose_mgdl": 125.0,
                "trend_description": "estable",
                "range_label": "Normal",
                "alert_level": "ok",
                "minutes_ago": 5.0,
            }
            await status_handler(update, context)

    # El handler ejecutó y llamó a la API
    mock_api.assert_called_once()


# ─── /start ──────────────────────────────────────────────────────────────────

async def test_start_sends_welcome() -> None:
    """El comando /start debe enviar un mensaje de bienvenida."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        await start_handler(update, context)

    update.effective_message.reply_text.assert_called_once()
    call_text = update.effective_message.reply_text.call_args[0][0]
    assert "Bienvenida" in call_text or "bienvenida" in call_text


# ─── /status ─────────────────────────────────────────────────────────────────

async def test_status_with_reading_sends_formatted_response(sample_reading: dict) -> None:
    """Con lectura disponible, /status debe formatear y enviar la respuesta."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.get_latest_reading", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = sample_reading
            await status_handler(update, context)

    update.effective_message.reply_text.assert_called()
    # La respuesta debe contener el valor de glucosa
    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "125" in response_text


async def test_status_without_reading_sends_error() -> None:
    """Sin lectura disponible, /status debe enviar mensaje de error."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.get_latest_reading", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = None
            await status_handler(update, context)

    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "❌" in response_text


# ─── /resumen ────────────────────────────────────────────────────────────────

async def test_resumen_with_data_sends_summary(sample_daily_summary: dict) -> None:
    """Con datos disponibles, /resumen debe enviar el resumen AGP."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.get_daily_summary", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = sample_daily_summary
            await resumen_handler(update, context)

    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "TIR" in response_text


async def test_resumen_without_data_sends_error() -> None:
    """Sin datos disponibles, /resumen debe enviar mensaje de error."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.get_daily_summary", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = None
            await resumen_handler(update, context)

    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "❌" in response_text


# ─── /semana ─────────────────────────────────────────────────────────────────

async def test_semana_with_data_sends_weekly(sample_weekly_summary: dict) -> None:
    """Con datos disponibles, /semana debe enviar el resumen semanal."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.get_weekly_summary", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = sample_weekly_summary
            await semana_handler(update, context)

    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "semanal" in response_text.lower() or "TIR" in response_text


# ─── /ayuda ──────────────────────────────────────────────────────────────────

async def test_ayuda_contains_all_commands() -> None:
    """El comando /ayuda debe listar todos los comandos."""
    update = _make_update(AUTHORIZED_CHAT_ID)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        await ayuda_handler(update, context)

    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "/status" in response_text
    assert "/resumen" in response_text
    assert "/limpiar" in response_text


# ─── /limpiar ────────────────────────────────────────────────────────────────

async def test_limpiar_clears_conversation_history() -> None:
    """El comando /limpiar debe vaciar el historial del chat."""
    chat_id = AUTHORIZED_CHAT_ID
    conversation_manager.add_message(chat_id, "user", "pregunta previa")
    assert len(conversation_manager.get_history(chat_id)) == 1

    update = _make_update(chat_id)
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        await limpiar_handler(update, context)

    assert conversation_manager.get_history(chat_id) == []
    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "reiniciada" in response_text.lower() or "limpiar" in response_text.lower()

    # Limpiar estado después del test
    conversation_manager.clear(chat_id)


# ─── Texto libre (chat con IA) ─────────────────────────────────────────────────

async def test_text_message_calls_chat_ai() -> None:
    """Texto libre debe invocar chat_with_ai y devolver la respuesta."""
    update = _make_update(AUTHORIZED_CHAT_ID, text="¿Cuánta insulina me aplico?")
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.chat_with_ai", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Basándome en tu glucosa actual de 125 mg/dL..."
            await message_handler(update, context)

    mock_chat.assert_called_once()
    # El canal debe ser 'telegram'
    call_kwargs = mock_chat.call_args[1]
    assert call_kwargs.get("channel") == "telegram"

    # La respuesta del LLM se envía al usuario
    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "125" in response_text

    # Limpiar estado después del test
    conversation_manager.clear(AUTHORIZED_CHAT_ID)


async def test_text_message_maintains_conversation_history() -> None:
    """El historial de conversación debe crecer con cada intercambio."""
    chat_id = AUTHORIZED_CHAT_ID
    conversation_manager.clear(chat_id)

    for i in range(2):
        update = _make_update(chat_id, text=f"pregunta {i}")
        context = _make_context()

        with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
            with patch("telegram_bot.handlers.api_client.chat_with_ai", new_callable=AsyncMock) as mock_chat:
                mock_chat.return_value = f"respuesta {i}"
                await message_handler(update, context)

    # 2 intercambios = 4 mensajes (2 user + 2 assistant)
    history = conversation_manager.get_history(chat_id)
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    # Limpiar estado después del test
    conversation_manager.clear(chat_id)


async def test_text_message_with_api_error_sends_error_message() -> None:
    """Si el LLM retorna None, debe enviarse un mensaje de error."""
    update = _make_update(AUTHORIZED_CHAT_ID, text="pregunta")
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.chat_with_ai", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = None
            await message_handler(update, context)

    response_text = update.effective_message.reply_text.call_args[0][0]
    assert "❌" in response_text


async def test_text_message_sends_previous_history_to_llm() -> None:
    """El historial previo debe incluirse en la llamada al LLM."""
    chat_id = AUTHORIZED_CHAT_ID
    conversation_manager.clear(chat_id)
    conversation_manager.add_message(chat_id, "user", "pregunta anterior")
    conversation_manager.add_message(chat_id, "assistant", "respuesta anterior")

    update = _make_update(chat_id, text="nueva pregunta")
    context = _make_context()

    with patch("telegram_bot.security.ALLOWED_CHAT_IDS", {AUTHORIZED_CHAT_ID}):
        with patch("telegram_bot.handlers.api_client.chat_with_ai", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "nueva respuesta"
            await message_handler(update, context)

    # El historial enviado debe tener los 2 mensajes previos
    call_kwargs = mock_chat.call_args[1]
    history_sent = call_kwargs.get("history", [])
    assert len(history_sent) == 2
    assert history_sent[0]["content"] == "pregunta anterior"

    # Limpiar estado después del test
    conversation_manager.clear(chat_id)
