"""
Punto de entrada del bot de Telegram bidireccional.
Ejecutar con: python -m telegram_bot.bot
"""

import logging
import os
import sys

from dotenv import load_dotenv

# Cargar .env ANTES de importar módulos propios que leen variables de entorno al importarse
load_dotenv()

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from telegram_bot.handlers import (
    ayuda_handler,
    cleanup_job,
    limpiar_handler,
    message_handler,
    resumen_handler,
    semana_handler,
    start_handler,
    status_handler,
)
from telegram_bot.security import ALLOWED_CHAT_IDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("telegram-bot")


def build_app(token: str) -> Application:
    """Construye y configura la aplicación del bot."""
    app = ApplicationBuilder().token(token).build()

    # Registrar handlers de comandos
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("resumen", resumen_handler))
    app.add_handler(CommandHandler("semana", semana_handler))
    app.add_handler(CommandHandler("ayuda", ayuda_handler))
    app.add_handler(CommandHandler("help", ayuda_handler))
    app.add_handler(CommandHandler("limpiar", limpiar_handler))

    # Handler de texto libre — chat con IA (después de los comandos)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
    )

    # Job periódico: limpiar conversaciones inactivas cada 10 minutos
    app.job_queue.run_repeating(  # type: ignore[union-attr]
        cleanup_job,
        interval=600,   # segundos
        first=60,       # primera ejecución después de 1 minuto
        name="cleanup_stale_conversations",
    )

    return app


def main() -> None:
    """Arranca el bot de Telegram en modo polling."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN no configurado en .env")
        sys.exit(1)

    if not ALLOWED_CHAT_IDS:
        logger.warning(
            "TELEGRAM_CHAT_ID no configurado — ningún usuario podrá usar el bot"
        )

    api_url = os.getenv("API_URL", "http://localhost:8888")
    logger.info("Bot iniciando | API: %s | chat_ids autorizados: %s", api_url, ALLOWED_CHAT_IDS)

    app = build_app(token)
    logger.info("Bot listo — escuchando mensajes (Ctrl+C para detener)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
