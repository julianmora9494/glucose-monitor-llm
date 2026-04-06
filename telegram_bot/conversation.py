"""
Gestión de sesiones activas por chat_id.

Solo rastrea TTL y el timestamp de último /limpiar.
El historial de mensajes se persiste en ConversationStore (memory.py),
no en RAM — así sobrevive reinicios del bot.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    """Sesión activa para un chat_id."""

    last_active: datetime = field(default_factory=datetime.now)
    # Timestamp desde el que incluir mensajes en el contexto LLM.
    # None = incluir todos los mensajes recientes (comportamiento por defecto).
    # Seteado a datetime.now() cuando el usuario ejecuta /limpiar.
    context_since: Optional[datetime] = None


class ConversationManager:
    """
    Rastrea sesiones activas y sus TTLs.

    No almacena historial de conversación (eso va en ConversationStore).
    Solo sirve para saber cuándo una sesión expiró y disparar la summarización.
    """

    def __init__(self, ttl_minutes: int | None = None) -> None:
        self._sessions: dict[int, ConversationSession] = {}
        self._ttl_minutes: int = ttl_minutes or int(
            os.getenv("TELEGRAM_CONVERSATION_TTL_MIN", "30")
        )

    def touch(self, chat_id: int) -> None:
        """Registra actividad del chat_id. Crea sesión si no existe."""
        if chat_id not in self._sessions:
            self._sessions[chat_id] = ConversationSession()
        else:
            self._sessions[chat_id].last_active = datetime.now()

    def get_context_since(self, chat_id: int) -> Optional[datetime]:
        """
        Retorna el timestamp desde el que incluir mensajes recientes en el contexto LLM.
        None si la sesión no existe o el usuario no ejecutó /limpiar.
        """
        session = self._sessions.get(chat_id)
        return session.context_since if session else None

    def clear(self, chat_id: int) -> None:
        """
        Reinicia el contexto LLM del chat_id (/limpiar).

        El historial en DB se preserva (útil para auditoría y summarización futura),
        pero no se incluirá en futuros LLM contexts hasta que el usuario
        vuelva a interactuar pasando el límite de tiempo.
        """
        session = self._sessions.setdefault(chat_id, ConversationSession())
        session.last_active = datetime.now()
        session.context_since = datetime.now()
        logger.info("Contexto LLM reiniciado para chat_id=%s", chat_id)

    def get_expired_sessions(self) -> list[int]:
        """
        Retorna los chat_ids de sesiones que han expirado.
        Llamado antes de cleanup_stale() para saber a qué sesiones resumir.
        """
        cutoff = datetime.now() - timedelta(minutes=self._ttl_minutes)
        return [cid for cid, s in self._sessions.items() if s.last_active < cutoff]

    def cleanup_stale(self) -> int:
        """Elimina sesiones expiradas de memoria. Retorna el número eliminado."""
        cutoff = datetime.now() - timedelta(minutes=self._ttl_minutes)
        stale = [cid for cid, s in self._sessions.items() if s.last_active < cutoff]

        for chat_id in stale:
            del self._sessions[chat_id]
            logger.info("Sesión expirada eliminada para chat_id=%s", chat_id)

        return len(stale)

    @property
    def active_sessions(self) -> int:
        """Número de sesiones activas en memoria."""
        return len(self._sessions)


# Instancia global compartida por todos los handlers
conversation_manager = ConversationManager()
