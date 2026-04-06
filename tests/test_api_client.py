"""
Tests del cliente HTTP asíncrono para la API FastAPI.
Usa respx para mockear las llamadas HTTP sin necesidad de la API real.
"""

import pytest
import respx
import httpx

from telegram_bot.api_client import (
    is_api_online,
    get_latest_reading,
    get_readings_last_hours,
    get_daily_summary,
    get_weekly_summary,
    chat_with_ai,
)
from datetime import date


pytestmark = pytest.mark.asyncio


# ─── is_api_online ───────────────────────────────────────────────────────────

@respx.mock
async def test_api_online_returns_true_on_200() -> None:
    """Debe retornar True cuando la API responde 200."""
    respx.get("http://localhost:8888/health").mock(return_value=httpx.Response(200))
    result = await is_api_online()
    assert result is True


@respx.mock
async def test_api_online_returns_false_on_connection_error() -> None:
    """Debe retornar False cuando la API no está disponible."""
    respx.get("http://localhost:8888/health").mock(side_effect=httpx.ConnectError("refused"))
    result = await is_api_online()
    assert result is False


# ─── get_latest_reading ───────────────────────────────────────────────────────

@respx.mock
async def test_get_latest_reading_success(sample_reading: dict) -> None:
    """Debe retornar el dict de la lectura más reciente."""
    respx.get("http://localhost:8888/api/readings/latest").mock(
        return_value=httpx.Response(200, json=sample_reading)
    )
    result = await get_latest_reading()
    assert result is not None
    assert result["glucose_mgdl"] == 125.0


@respx.mock
async def test_get_latest_reading_returns_none_on_404() -> None:
    """Debe retornar None cuando no hay lecturas (404)."""
    respx.get("http://localhost:8888/api/readings/latest").mock(
        return_value=httpx.Response(404)
    )
    result = await get_latest_reading()
    assert result is None


@respx.mock
async def test_get_latest_reading_returns_none_on_connection_error() -> None:
    """Debe retornar None en caso de error de conexión."""
    respx.get("http://localhost:8888/api/readings/latest").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = await get_latest_reading()
    assert result is None


# ─── get_readings_last_hours ─────────────────────────────────────────────────

@respx.mock
async def test_get_readings_last_hours_success(sample_reading: dict) -> None:
    """Debe retornar lista de lecturas."""
    respx.get("http://localhost:8888/api/readings/last-hours/3").mock(
        return_value=httpx.Response(200, json=[sample_reading, sample_reading])
    )
    result = await get_readings_last_hours(3)
    assert len(result) == 2


@respx.mock
async def test_get_readings_last_hours_returns_empty_on_error() -> None:
    """Debe retornar lista vacía en caso de error."""
    respx.get("http://localhost:8888/api/readings/last-hours/3").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = await get_readings_last_hours(3)
    assert result == []


# ─── get_daily_summary ───────────────────────────────────────────────────────

@respx.mock
async def test_get_daily_summary_success(sample_daily_summary: dict) -> None:
    """Debe retornar el resumen AGP del día."""
    target = date(2026, 4, 5)
    respx.get("http://localhost:8888/api/summaries/day/2026-04-05").mock(
        return_value=httpx.Response(200, json=sample_daily_summary)
    )
    result = await get_daily_summary(target)
    assert result is not None
    assert result["tir_percent"] == 72.0


@respx.mock
async def test_get_daily_summary_returns_none_on_404() -> None:
    """Debe retornar None cuando no hay datos para esa fecha."""
    target = date(2026, 1, 1)
    respx.get("http://localhost:8888/api/summaries/day/2026-01-01").mock(
        return_value=httpx.Response(404)
    )
    result = await get_daily_summary(target)
    assert result is None


# ─── get_weekly_summary ──────────────────────────────────────────────────────

@respx.mock
async def test_get_weekly_summary_success(sample_weekly_summary: dict) -> None:
    """Debe retornar el resumen semanal."""
    respx.get("http://localhost:8888/api/summaries/weekly").mock(
        return_value=httpx.Response(200, json=sample_weekly_summary)
    )
    result = await get_weekly_summary()
    assert result is not None
    assert result["days_with_data"] == 6


@respx.mock
async def test_get_weekly_summary_returns_none_on_error() -> None:
    """Debe retornar None en caso de error."""
    respx.get("http://localhost:8888/api/summaries/weekly").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = await get_weekly_summary()
    assert result is None


# ─── chat_with_ai ────────────────────────────────────────────────────────────

@respx.mock
async def test_chat_with_ai_success() -> None:
    """Debe retornar la respuesta del LLM."""
    respx.post("http://localhost:8888/api/reports/chat").mock(
        return_value=httpx.Response(200, json={"answer": "Basándome en tu TIR..."})
    )
    result = await chat_with_ai("¿Cuánta insulina me aplico?", [])
    assert result == "Basándome en tu TIR..."


@respx.mock
async def test_chat_with_ai_sends_channel_param() -> None:
    """Debe enviar el parámetro channel='telegram' en el payload."""
    captured_request = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"answer": "respuesta"})

    respx.post("http://localhost:8888/api/reports/chat").mock(side_effect=capture)
    await chat_with_ai("pregunta", [], channel="telegram")

    import json
    body = json.loads(captured_request.content)  # type: ignore[union-attr]
    assert body["channel"] == "telegram"


@respx.mock
async def test_chat_with_ai_sends_history() -> None:
    """Debe incluir el historial de conversación en el payload."""
    captured_request = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"answer": "ok"})

    respx.post("http://localhost:8888/api/reports/chat").mock(side_effect=capture)
    history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hola"}]
    await chat_with_ai("nueva pregunta", history)

    import json
    body = json.loads(captured_request.content)  # type: ignore[union-attr]
    assert len(body["conversation_history"]) == 2


@respx.mock
async def test_chat_with_ai_returns_message_on_503() -> None:
    """Con LLM no configurado (503) debe retornar mensaje de error amigable."""
    respx.post("http://localhost:8888/api/reports/chat").mock(
        return_value=httpx.Response(503, json={"detail": "no configurado"})
    )
    result = await chat_with_ai("pregunta", [])
    assert result is not None
    assert "⚙️" in result


@respx.mock
async def test_chat_with_ai_returns_timeout_message() -> None:
    """En caso de timeout debe retornar mensaje informativo, no None."""
    respx.post("http://localhost:8888/api/reports/chat").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    result = await chat_with_ai("pregunta", [])
    assert result is not None
    assert "⏱" in result


@respx.mock
async def test_chat_with_ai_returns_none_on_generic_error() -> None:
    """En caso de error genérico debe retornar None."""
    respx.post("http://localhost:8888/api/reports/chat").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = await chat_with_ai("pregunta", [])
    assert result is None
