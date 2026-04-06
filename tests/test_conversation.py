"""
Tests del gestor de estado de conversación.
"""

from datetime import datetime, timedelta

import pytest

from telegram_bot.conversation import ConversationManager


def test_new_session_created_on_first_get() -> None:
    """La primera llamada a get_history debe crear la sesión."""
    mgr = ConversationManager(ttl_minutes=30)
    history = mgr.get_history(12345)
    assert history == []
    assert mgr.active_sessions == 1


def test_history_maintained_across_messages() -> None:
    """Los mensajes deben acumularse en el historial."""
    mgr = ConversationManager(ttl_minutes=30)
    mgr.add_message(1, "user", "Hola, ¿cuánta insulina me aplico?")
    mgr.add_message(1, "assistant", "Basándome en tu lectura actual...")
    mgr.add_message(1, "user", "¿Y si como pizza?")

    history = mgr.get_history(1)
    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[2]["content"] == "¿Y si como pizza?"


def test_max_history_trims_oldest() -> None:
    """Al superar MAX_HISTORY, deben descartarse los mensajes más antiguos."""
    mgr = ConversationManager(ttl_minutes=30)
    # Agregar 22 mensajes (supera MAX_HISTORY=20)
    for i in range(22):
        mgr.add_message(1, "user", f"msg {i}")

    history = mgr.get_history(1)
    assert len(history) == 20
    # El mensaje más antiguo que queda debe ser el índice 2 (msg 2)
    assert history[0]["content"] == "msg 2"
    assert history[-1]["content"] == "msg 21"


def test_clear_resets_session() -> None:
    """Clear debe vaciar el historial pero mantener la sesión."""
    mgr = ConversationManager(ttl_minutes=30)
    mgr.add_message(1, "user", "pregunta")
    mgr.clear(1)

    history = mgr.get_history(1)
    assert history == []


def test_multiple_chat_ids_isolated() -> None:
    """Los historiales de diferentes chat_ids deben ser independientes."""
    mgr = ConversationManager(ttl_minutes=30)
    mgr.add_message(1, "user", "mensaje de chat 1")
    mgr.add_message(2, "user", "mensaje de chat 2")

    assert len(mgr.get_history(1)) == 1
    assert len(mgr.get_history(2)) == 1
    assert mgr.get_history(1)[0]["content"] == "mensaje de chat 1"
    assert mgr.get_history(2)[0]["content"] == "mensaje de chat 2"


def test_cleanup_stale_removes_old_sessions() -> None:
    """Las sesiones inactivas más antiguas que el TTL deben eliminarse."""
    mgr = ConversationManager(ttl_minutes=30)
    mgr.add_message(1, "user", "antiguo")
    mgr.add_message(2, "user", "reciente")

    # Simular que la sesión 1 es muy antigua
    mgr._sessions[1].last_active = datetime.now() - timedelta(minutes=60)

    removed = mgr.cleanup_stale()
    assert removed == 1
    assert mgr.active_sessions == 1
    # La sesión 2 (reciente) debe sobrevivir
    assert mgr.get_history(2) != []


def test_cleanup_keeps_active_sessions() -> None:
    """Las sesiones recientes no deben eliminarse en el cleanup."""
    mgr = ConversationManager(ttl_minutes=30)
    mgr.add_message(1, "user", "mensaje reciente")

    removed = mgr.cleanup_stale()
    assert removed == 0
    assert mgr.active_sessions == 1


def test_get_history_returns_copy() -> None:
    """get_history debe retornar una copia para evitar mutaciones externas."""
    mgr = ConversationManager(ttl_minutes=30)
    mgr.add_message(1, "user", "original")
    history = mgr.get_history(1)

    # Mutar la lista externa no debe afectar el estado interno
    history.append({"role": "user", "content": "intruso"})
    assert len(mgr.get_history(1)) == 1
