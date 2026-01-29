"""
Обработчики команд Telegram-бота.
"""

import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from api_client import api_client, Cocktail

logger = logging.getLogger(__name__)

# Константы для callback_data
CALLBACK_RANDOM = "random"
CALLBACK_COCKTAIL_PREFIX = "cocktail_"


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
        if cocktail.image_url:
            # Отправляем фото с описанием
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
    logger.info(f"User {update.effective_user.id} started the bot")

    welcome_message = (
        "🍹 *Добро пожаловать в Cocktail Bot!*\n\n"
        "Я помогу вам найти рецепты вкусных коктейлей.\n\n"
        "*Доступные команды:*\n"
        "🎲 /random — случайный коктейль\n"
        "🔍 /search \\[название\\] — поиск по названию\n"
        "🧪 /ingredient \\[ингредиент\\] — поиск по ингредиенту\n"
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
    logger.info(f"User {update.effective_user.id} requested help")

    help_message = (
        "🍹 *Cocktail Bot — Справка*\n\n"
        "*Команды:*\n\n"
        "🎲 /random\n"
        "Получить случайный коктейль с фото и рецептом.\n\n"
        "🔍 /search \\[название\\]\n"
        "Найти коктейль по названию.\n"
        "_Пример:_ `/search margarita`\n\n"
        "🧪 /ingredient \\[ингредиент\\]\n"
        "Найти коктейли с определённым ингредиентом.\n"
        "_Пример:_ `/ingredient vodka`\n\n"
        "📊 *О боте:*\n"
        "Бот использует базу данных TheCocktailDB с тысячами рецептов коктейлей.\n\n"
        "💡 *Совет:* Используйте английские названия для лучшего поиска!"
    )

    await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /random."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested random cocktail")

    # Отправляем сообщение о загрузке
    loading_message = await update.message.reply_text("🔄 Ищу для вас коктейль...")

    try:
        cocktail = await api_client.get_random_cocktail()

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
    user_id = update.effective_user.id

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

    loading_message = await update.message.reply_text(f"🔍 Ищу коктейли по запросу «{query}»...")

    try:
        cocktails = await api_client.search_by_name(query)
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

        if len(cocktails) == 1:
            # Если найден только один коктейль, показываем его сразу
            await send_cocktail(update, context, cocktails[0])
        else:
            # Показываем список найденных коктейлей
            keyboard = []
            for cocktail in cocktails[:10]:  # Ограничиваем до 10 результатов
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"{cocktail.get_alcoholic_emoji()} {cocktail.name}",
                            callback_data=f"{CALLBACK_COCKTAIL_PREFIX}{cocktail.id}",
                        )
                    ]
                )

            message = f"🔍 *Найдено коктейлей: {len(cocktails)}*\n\n" "Выберите коктейль:"

            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    except Exception as e:
        logger.error(f"Error in search_command: {e}")
        await loading_message.edit_text(
            "❌ Произошла ошибка при поиске. Попробуйте позже."
        )


async def ingredient_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик команды /ingredient."""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "🧪 *Поиск по ингредиенту*\n\n"
            "Укажите ингредиент после команды.\n"
            "_Пример:_ `/ingredient rum`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ingredient = " ".join(context.args)
    logger.info(f"User {user_id} searching by ingredient: {ingredient}")

    loading_message = await update.message.reply_text(
        f"🧪 Ищу коктейли с ингредиентом «{ingredient}»..."
    )

    try:
        results = await api_client.search_by_ingredient(ingredient)
        await loading_message.delete()

        if not results:
            await update.message.reply_text(
                f"😔 Коктейли с ингредиентом «{ingredient}» не найдены.\n\n"
                "💡 Попробуйте написать ингредиент на английском.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🎲 Случайный коктейль", callback_data=CALLBACK_RANDOM)]]
                ),
            )
            return

        # Показываем список найденных коктейлей
        keyboard = []
        for item in results[:10]:  # Ограничиваем до 10 результатов
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🍹 {item['name']}",
                        callback_data=f"{CALLBACK_COCKTAIL_PREFIX}{item['id']}",
                    )
                ]
            )

        message = (
            f"🧪 *Коктейли с «{ingredient}»: {len(results)}*\n\n"
            "Выберите коктейль для просмотра рецепта:"
        )

        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception as e:
        logger.error(f"Error in ingredient_command: {e}")
        await loading_message.edit_text(
            "❌ Произошла ошибка при поиске. Попробуйте позже."
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    logger.info(f"User {user_id} pressed button: {data}")

    if data == CALLBACK_RANDOM:
        # Запрос случайного коктейля
        cocktail = await api_client.get_random_cocktail()

        if cocktail:
            await send_cocktail(update, context, cocktail)
        else:
            await query.message.reply_text(
                "😔 Не удалось получить коктейль. Попробуйте позже."
            )

    elif data.startswith(CALLBACK_COCKTAIL_PREFIX):
        # Запрос конкретного коктейля по ID
        cocktail_id = data[len(CALLBACK_COCKTAIL_PREFIX):]
        cocktail = await api_client.get_cocktail_by_id(cocktail_id)

        if cocktail:
            await send_cocktail(update, context, cocktail)
        else:
            await query.message.reply_text(
                "😔 Не удалось получить информацию о коктейле. Попробуйте позже."
            )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик неизвестных команд."""
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

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        )
