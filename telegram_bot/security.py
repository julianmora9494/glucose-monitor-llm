"""
Autorización de usuarios del bot de Telegram.
Solo los chat_ids configurados en .env pueden interactuar con el bot.
"""

import logging
import os
from collections.abc import Callable
from functools import wraps
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _load_allowed_chat_ids() -> set[int]:
    """Carga los chat_ids autorizados desde variables de entorno."""
    allowed: set[int] = set()

    primary = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if primary:
        try:
            allowed.add(int(primary))
        except ValueError:
            logger.error("TELEGRAM_CHAT_ID no es un entero válido: %s", primary)

    caregiver = os.getenv("TELEGRAM_CAREGIVER_CHAT_ID", "").strip()
    if caregiver:
        try:
            allowed.add(int(caregiver))
        except ValueError:
            logger.error("TELEGRAM_CAREGIVER_CHAT_ID no es un entero válido: %s", caregiver)

    return allowed


# Conjunto de chat_ids autorizados — cargado al importar el módulo
ALLOWED_CHAT_IDS: set[int] = _load_allowed_chat_ids()


def is_authorized(chat_id: int) -> bool:
    """Verifica si un chat_id está autorizado para usar el bot."""
    return chat_id in ALLOWED_CHAT_IDS


def require_auth(func: Callable) -> Callable:
    """
    Decorador para handlers de Telegram.
    Rechaza mensajes de chat_ids no autorizados antes de ejecutar el handler.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        if not update.effective_chat:
            return None

        chat_id = update.effective_chat.id
        if not is_authorized(chat_id):
            logger.warning("Acceso no autorizado desde chat_id=%s", chat_id)
            await update.effective_message.reply_text(  # type: ignore[union-attr]
                "⛔ No tienes permiso para usar este bot."
            )
            return None

        return await func(update, context, *args, **kwargs)

    return wrapper
