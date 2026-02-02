"""
Обработчики команд Telegram-бота.
"""

import logging
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from db_client import db_client, Cocktail
from analytics import analytics
from config import Config
from llm_client import llm_client

logger = logging.getLogger(__name__)

# Константы для callback_data
CALLBACK_RANDOM = "random"


async def send_cocktail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    cocktail: Cocktail,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Отправка информации о коктейле пользователю."""
    message = cocktail.to_message()

    # Создаём клавиатуру с кнопкой "Ещё коктейль"
    if reply_markup is None:
        keyboard = [
            [InlineKeyboardButton("🎲 Ещё коктейль", callback_data=CALLBACK_RANDOM)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Проверяем наличие локального изображения
        if cocktail.image_path and Path(cocktail.image_path).exists():
            # Отправляем локальный файл
            with open(cocktail.image_path, "rb") as photo_file:
                await update.effective_message.reply_photo(
                    photo=InputFile(photo_file),
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
        elif cocktail.image_url:
            # Fallback на URL, если локальный файл не найден
            await update.effective_message.reply_photo(
                photo=cocktail.image_url,
                caption=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        else:
            # Отправляем только текст, если нет изображения
            await update.effective_message.reply_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error sending cocktail: {e}")
        # Пробуем отправить без Markdown в случае ошибки
        await update.effective_message.reply_text(
            f"🍹 {cocktail.name}\n\n"
            f"К сожалению, возникла ошибка при форматировании. "
            f"Попробуйте ещё раз: /random",
            reply_markup=reply_markup,
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    analytics.log_event(
        user_id=user.id,
        username=user.username,
        event_type="command_start",
    )

    welcome_message = (
        "🍹 *Добро пожаловать в Cocktail Bot!*\n\n"
        "Я помогу вам найти рецепты вкусных коктейлей.\n\n"
        "*Доступные команды:*\n"
        "🎲 /random — случайный коктейль\n"
        "🔍 /search \\[название\\] — поиск по названию\n"
        "🍷 /toast\\_toxic \\[повод\\] — токсичный тост\n"
        "❓ /help — справка\n\n"
        "Попробуйте нажать /random для начала!"
    )

    keyboard = [[InlineKeyboardButton("🎲 Случайный коктейль", callback_data=CALLBACK_RANDOM)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    user = update.effective_user
    logger.info(f"User {user.id} requested help")
    analytics.log_event(
        user_id=user.id,
        username=user.username,
        event_type="command_help",
    )

    help_message = (
        "🍹 *Cocktail Bot — Справка*\n\n"
        "*Команды:*\n\n"
        "🎲 /random\n"
        "Получить случайный коктейль с фото и рецептом.\n\n"
        "🔍 /search \\[название\\]\n"
        "Найти коктейль по названию.\n"
        "_Пример:_ `/search margarita`\n\n"
        "🍷 /toast\\_toxic \\[повод\\]\n"
        "Сгенерировать токсичный тост для повода.\n"
        "_Пример:_ `/toast_toxic пятница`\n\n"
        "📊 *О боте:*\n"
        "База данных содержит более 400 рецептов коктейлей.\n\n"
        "💡 *Совет:* Используйте английские названия для лучшего поиска!"
    )

    await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /random."""
    user = update.effective_user
    user_id = user.id
    logger.info(f"User {user_id} requested random cocktail")
    analytics.log_event(
        user_id=user_id,
        username=user.username,
        event_type="command_random",
    )

    # Отправляем сообщение о загрузке
    loading_message = await update.message.reply_text("🔄 Ищу для вас коктейль...")

    try:
        cocktail = db_client.get_random_cocktail()

        # Удаляем сообщение о загрузке
        await loading_message.delete()

        if cocktail:
            await send_cocktail(update, context, cocktail)
        else:
            await update.message.reply_text(
                "😔 Не удалось получить коктейль. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔄 Попробовать снова", callback_data=CALLBACK_RANDOM)]]
                ),
            )
    except Exception as e:
        logger.error(f"Error in random_command: {e}")
        await loading_message.edit_text(
            "❌ Произошла ошибка при получении коктейля. Попробуйте позже."
        )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /search."""
    user = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text(
            "🔍 *Поиск коктейля*\n\n"
            "Укажите название после команды.\n"
            "_Пример:_ `/search mojito`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    query = " ".join(context.args)
    logger.info(f"User {user_id} searching for: {query}")

    analytics.log_event(
        user_id=user_id,
        username=user.username,
        event_type="command_search",
        payload={"query": query},
    )

    loading_message = await update.message.reply_text(f"🔍 Ищу коктейли по запросу «{query}»...")

    try:
        cocktails = db_client.search_by_name(query)
        await loading_message.delete()

        if not cocktails:
            await update.message.reply_text(
                f"😔 Коктейли по запросу «{query}» не найдены.\n\n"
                "💡 Попробуйте другое название или нажмите /random для случайного коктейля.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🎲 Случайный коктейль", callback_data=CALLBACK_RANDOM)]]
                ),
            )
            return

        # Показываем первый найденный коктейль
        await send_cocktail(update, context, cocktails[0])

    except Exception as e:
        logger.error(f"Error in search_command: {e}")
        await loading_message.edit_text(
            "❌ Произошла ошибка при поиске. Попробуйте позже."
        )


async def toast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /toast_toxic."""
    user = update.effective_user
    user_id = user.id

    # Проверяем аргументы: /toast_toxic <повод>
    if not context.args:
        await update.message.reply_text(
            "🍷 *Токсичный тост*\n\n"
            "Использование: `/toast_toxic <повод>`\n\n"
            "_Примеры:_\n"
            "`/toast_toxic работа`\n"
            "`/toast_toxic пятница`\n"
            "`/toast_toxic день программиста`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    reason = " ".join(context.args)
    logger.info(f"User {user_id} requested toxic toast for: {reason}")

    analytics.log_event(
        user_id=user_id,
        username=user.username,
        event_type="command_toast_toxic",
        payload={"reason": reason},
    )

    # Проверяем наличие API ключа
    if not Config.OPENAI_API_KEY:
        await update.message.reply_text(
            "⚠️ Функция тостов временно недоступна.\n"
            "Администратору необходимо настроить OPENAI\\_API\\_KEY.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    loading_message = await update.message.reply_text("🍷 Готовлю токсичный тост...")

    try:
        toast = await llm_client.generate_toxic_toast(reason)
        await loading_message.delete()

        if toast:
            await update.message.reply_text(
                f"🍷 *Тост за «{reason}»*\n\n{toast}",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(
                "😔 Не удалось сгенерировать тост. Попробуйте позже."
            )

    except ValueError as e:
        logger.error(f"Config error in toast_command: {e}")
        await loading_message.edit_text(
            "⚠️ Функция тостов не настроена. Обратитесь к администратору."
        )
    except Exception as e:
        logger.error(f"Error in toast_command: {e}")
        await loading_message.edit_text(
            "❌ Произошла ошибка при генерации тоста. Попробуйте позже."
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user = update.effective_user
    user_id = user.id

    logger.info(f"User {user_id} pressed button: {data}")

    if data == CALLBACK_RANDOM:
        # Запрос случайного коктейля
        analytics.log_event(
            user_id=user_id,
            username=user.username,
            event_type="button_random",
        )
        cocktail = db_client.get_random_cocktail()

        if cocktail:
            await send_cocktail(update, context, cocktail)
        else:
            await query.message.reply_text(
                "😔 Не удалось получить коктейль. Попробуйте позже."
            )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик неизвестных команд."""
    user = update.effective_user
    analytics.log_event(
        user_id=user.id,
        username=user.username,
        event_type="unknown_command",
    )

    await update.message.reply_text(
        "🤔 Не понимаю эту команду.\n\n"
        "Используйте /help для списка доступных команд.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎲 Случайный коктейль", callback_data=CALLBACK_RANDOM)]]
        ),
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок."""
    logger.error(f"Exception while handling an update: {context.error}")

    try:
        if update and update.effective_user:
            analytics.log_event(
                user_id=update.effective_user.id,
                username=update.effective_user.username,
                event_type="error",
                payload={"error": str(context.error)},
            )
    except Exception as exc:  # безопасность: не роняем error_handler
        logger.error(f"Failed to log analytics error event: {exc}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        )
