"""
Tests de autorización del bot de Telegram.
"""

import importlib

import pytest


def _reload_security() -> object:
    """Recarga el módulo security para que lea las env vars actuales."""
    import telegram_bot.security as sec
    return importlib.reload(sec)


def test_authorized_primary_chat_id_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """El chat_id principal debe ser aceptado."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111111111")
    monkeypatch.delenv("TELEGRAM_CAREGIVER_CHAT_ID", raising=False)
    sec = _reload_security()
    assert sec.is_authorized(111111111) is True  # type: ignore[attr-defined]


def test_unauthorized_chat_id_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un chat_id desconocido debe ser rechazado."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111111111")
    monkeypatch.delenv("TELEGRAM_CAREGIVER_CHAT_ID", raising=False)
    sec = _reload_security()
    assert sec.is_authorized(999999999) is False  # type: ignore[attr-defined]


def test_caregiver_chat_id_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """El chat_id del cuidador también debe ser aceptado."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111111111")
    monkeypatch.setenv("TELEGRAM_CAREGIVER_CHAT_ID", "222222222")
    sec = _reload_security()
    assert sec.is_authorized(222222222) is True  # type: ignore[attr-defined]


def test_no_env_vars_rejects_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin variables de entorno configuradas, todo chat_id debe ser rechazado."""
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CAREGIVER_CHAT_ID", raising=False)
    sec = _reload_security()
    assert sec.is_authorized(111111111) is False  # type: ignore[attr-defined]
    assert sec.is_authorized(0) is False  # type: ignore[attr-defined]


def test_invalid_env_var_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un valor no numérico en la env var no debe causar excepción."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "not_a_number")
    monkeypatch.delenv("TELEGRAM_CAREGIVER_CHAT_ID", raising=False)
    sec = _reload_security()
    # No debe lanzar excepción; simplemente no habrá IDs autorizados
    assert sec.is_authorized(111111111) is False  # type: ignore[attr-defined]
