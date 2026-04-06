"""
Tests de los formateadores de mensajes de Telegram.
"""

import pytest

from telegram_bot.formatters import (
    format_api_error,
    format_daily_summary,
    format_help,
    format_status,
    format_weekly_summary,
    split_message,
)


# ─── format_status ──────────────────────────────────────────────────────────

def test_format_status_normal_range(sample_reading: dict) -> None:
    """Lectura normal debe incluir checkmark y el valor de glucosa."""
    result = format_status(sample_reading)
    assert "125" in result
    assert "✅" in result
    assert "estable" in result


def test_format_status_high_glucose(sample_reading_high: dict) -> None:
    """Lectura alta debe incluir emoji de advertencia."""
    result = format_status(sample_reading_high)
    assert "220" in result
    assert "⚠️" in result


def test_format_status_critical_low(sample_reading_low: dict) -> None:
    """Lectura crítica baja debe incluir emoji SOS."""
    result = format_status(sample_reading_low)
    assert "58" in result
    assert "🆘" in result


def test_format_status_recent_reading(sample_reading: dict) -> None:
    """Lectura de hace <2 min debe mostrar 'ahora mismo'."""
    sample_reading["minutes_ago"] = 1.0
    result = format_status(sample_reading)
    assert "ahora mismo" in result


def test_format_status_older_reading(sample_reading: dict) -> None:
    """Lectura de hace más de 2 min debe mostrar los minutos."""
    sample_reading["minutes_ago"] = 8.0
    result = format_status(sample_reading)
    assert "8 min" in result


# ─── format_daily_summary ───────────────────────────────────────────────────

def test_format_daily_summary_contains_key_metrics(sample_daily_summary: dict) -> None:
    """El resumen diario debe contener las métricas principales."""
    result = format_daily_summary(sample_daily_summary)
    assert "TIR" in result
    assert "TAR" in result
    assert "TBR" in result
    assert "CV" in result
    assert "GMI" in result
    assert "2026-04-05" in result


def test_format_daily_summary_good_control(sample_daily_summary: dict) -> None:
    """Control bueno (TIR >70%) debe mostrar checkmarks."""
    result = format_daily_summary(sample_daily_summary)
    assert "✅" in result


def test_format_daily_summary_poor_tir(sample_daily_summary: dict) -> None:
    """TIR bajo el objetivo debe mostrar emoji de alerta."""
    sample_daily_summary["tir_percent"] = 40.0
    result = format_daily_summary(sample_daily_summary)
    assert "🔴" in result


def test_format_daily_summary_shows_mage(sample_daily_summary: dict) -> None:
    """Si hay MAGE disponible, debe aparecer en el mensaje."""
    result = format_daily_summary(sample_daily_summary)
    assert "MAGE" in result
    assert "95" in result


def test_format_daily_summary_no_mage(sample_daily_summary: dict) -> None:
    """Sin MAGE no debe aparecer esa línea (no lanzar error)."""
    sample_daily_summary["mage_mgdl"] = None
    result = format_daily_summary(sample_daily_summary)
    assert "MAGE" not in result


# ─── format_weekly_summary ──────────────────────────────────────────────────

def test_format_weekly_summary_contains_range(sample_weekly_summary: dict) -> None:
    """El resumen semanal debe incluir el rango de fechas."""
    result = format_weekly_summary(sample_weekly_summary)
    assert "2026-03-30" in result
    assert "2026-04-05" in result


def test_format_weekly_summary_contains_metrics(sample_weekly_summary: dict) -> None:
    """El resumen semanal debe contener métricas clave."""
    result = format_weekly_summary(sample_weekly_summary)
    assert "TIR" in result
    assert "GMI" in result


# ─── format_help ────────────────────────────────────────────────────────────

def test_format_help_contains_all_commands() -> None:
    """La ayuda debe listar todos los comandos disponibles."""
    result = format_help()
    assert "/status" in result
    assert "/resumen" in result
    assert "/semana" in result
    assert "/limpiar" in result
    assert "/ayuda" in result


# ─── split_message ──────────────────────────────────────────────────────────

def test_split_message_short_text() -> None:
    """Un texto corto no debe dividirse."""
    text = "Hola"
    parts = split_message(text)
    assert parts == ["Hola"]


def test_split_message_long_text() -> None:
    """Un texto largo debe dividirse en partes ≤ max_len."""
    long_text = "A" * 5000
    parts = split_message(long_text, max_len=100)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 100


def test_split_message_prefers_newline_split() -> None:
    """Debe preferir dividir en saltos de línea para no cortar palabras."""
    text = "Línea 1\nLínea 2\nLínea 3"
    parts = split_message(text, max_len=10)
    # Cada parte debe ser una línea completa o menos
    for part in parts:
        assert len(part) <= 10


def test_split_message_exact_limit() -> None:
    """Un texto exactamente del límite no debe dividirse."""
    text = "X" * 4096
    parts = split_message(text)
    assert len(parts) == 1


# ─── format_api_error ───────────────────────────────────────────────────────

def test_format_api_error_basic() -> None:
    """Debe retornar mensaje de error legible."""
    result = format_api_error()
    assert "❌" in result


def test_format_api_error_with_detail() -> None:
    """Debe incluir el detalle del error si se provee."""
    result = format_api_error("Timeout after 30s")
    assert "Timeout after 30s" in result
