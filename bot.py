#!/usr/bin/env python3
"""
Telegram-бот для коктейлей.
Отправляет рецепты коктейлей с изображениями из локальной базы данных.
"""

import logging
import sys

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import Config
from db_client import db_client
from handlers import (
    start_command,
    help_command,
    random_command,
    search_command,
    toast_command,
    button_callback,
    unknown_command,
    error_handler,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)

# Уменьшаем уровень логирования для httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Действия после инициализации бота."""
    logger.info("Bot initialized successfully")
    bot_info = await application.bot.get_me()
    logger.info(f"Bot username: @{bot_info.username}")


async def post_shutdown(application: Application) -> None:
    """Действия при завершении работы бота."""
    logger.info("Shutting down bot...")
    db_client.close()
    logger.info("Bot shutdown complete")


def main() -> None:
    """Главная функция запуска бота."""
    logger.info("Starting Cocktail Bot...")

    # Проверяем конфигурацию
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Создаём приложение
    application = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("toast_toxic", toast_command))

    # Обработчик inline-кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    # Обработчик неизвестных команд
    application.add_handler(
        MessageHandler(filters.COMMAND, unknown_command)
    )

    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
