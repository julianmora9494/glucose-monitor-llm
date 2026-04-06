"""
Fixtures compartidos para tests del bot de Telegram.
"""

import pytest


@pytest.fixture
def sample_reading() -> dict:
    """Lectura glucémica de ejemplo en rango normal."""
    return {
        "glucose_mgdl": 125.0,
        "trend": "Flat",
        "trend_description": "estable",
        "range_label": "Normal",
        "alert_level": "ok",
        "minutes_ago": 5.0,
        "timestamp": "2026-04-05T10:30:00-05:00",
    }


@pytest.fixture
def sample_reading_high() -> dict:
    """Lectura glucémica de ejemplo en hiperglucemia."""
    return {
        "glucose_mgdl": 220.0,
        "trend": "SingleUp",
        "trend_description": "subiendo",
        "range_label": "Alto",
        "alert_level": "warning",
        "minutes_ago": 3.0,
        "timestamp": "2026-04-05T14:00:00-05:00",
    }


@pytest.fixture
def sample_reading_low() -> dict:
    """Lectura glucémica de ejemplo en hipoglucemia."""
    return {
        "glucose_mgdl": 58.0,
        "trend": "DoubleDown",
        "trend_description": "bajando rápido",
        "range_label": "Muy bajo",
        "alert_level": "critical",
        "minutes_ago": 2.0,
        "timestamp": "2026-04-05T03:00:00-05:00",
    }


@pytest.fixture
def sample_daily_summary() -> dict:
    """Resumen AGP diario de ejemplo."""
    return {
        "date": "2026-04-05",
        "reading_count": 144,
        "avg_glucose_mgdl": 142.0,
        "std_glucose_mgdl": 35.0,
        "cv_percent": 24.6,
        "tir_percent": 72.0,
        "tar_percent": 22.0,
        "tbr_percent": 2.0,
        "tbr_severe_percent": 0.5,
        "gmi_percent": 6.7,
        "mage_mgdl": 95.0,
        "hypo_episodes": 1,
        "hyper_episodes": 2,
        "min_glucose_mgdl": 62.0,
        "max_glucose_mgdl": 245.0,
        "status": {
            "tir": "ok",
            "tar": "ok",
            "tbr": "ok",
            "cv": "ok",
            "gmi": "ok",
        },
        "has_chart": False,
    }


@pytest.fixture
def sample_weekly_summary(sample_daily_summary: dict) -> dict:
    """Resumen semanal de ejemplo."""
    return {
        "week_start": "2026-03-30",
        "week_end": "2026-04-05",
        "days_with_data": 6,
        "avg_tir_percent": 68.5,
        "avg_glucose_mgdl": 155.0,
        "avg_cv_percent": 30.2,
        "gmi_percent": 7.0,
        "total_hypo_episodes": 4,
        "total_hyper_episodes": 12,
        "days": [sample_daily_summary],
    }


@pytest.fixture(autouse=True)
def set_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configura variables de entorno de Telegram para todos los tests."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111111111")
    monkeypatch.setenv("TELEGRAM_CAREGIVER_CHAT_ID", "222222222")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token:ABC123")
    monkeypatch.setenv("API_URL", "http://localhost:8888")
