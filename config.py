"""
Конфигурация Telegram-бота для коктейлей.
"""

import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()


class Config:
    """Класс конфигурации приложения."""

    # Telegram Bot Token
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # TheCocktailDB API
    COCKTAIL_API_BASE_URL: str = "https://www.thecocktaildb.com/api/json/v1/1"

    # API Endpoints
    RANDOM_COCKTAIL_URL: str = f"{COCKTAIL_API_BASE_URL}/random.php"
    SEARCH_BY_NAME_URL: str = f"{COCKTAIL_API_BASE_URL}/search.php"
    SEARCH_BY_INGREDIENT_URL: str = f"{COCKTAIL_API_BASE_URL}/filter.php"
    LOOKUP_BY_ID_URL: str = f"{COCKTAIL_API_BASE_URL}/lookup.php"

    # Timeouts (в секундах)
    API_TIMEOUT: int = 10

    # Настройки кеширования
    CACHE_TTL: int = 300  # 5 минут

    # Локальная база данных коктейлей
    DB_PATH: str = os.getenv("DB_PATH", "data/cocktails.db")

    # Google Cloud Translation API (опционально)
    GOOGLE_TRANSLATE_API_KEY: str = os.getenv("GOOGLE_TRANSLATE_API_KEY", "")
    TRANSLATION_TARGET_LANG: str = os.getenv("TRANSLATION_TARGET_LANG", "ru")

    # OpenAI API (для генерации тостов)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @classmethod
    def validate(cls) -> bool:
        """Проверка наличия обязательных переменных окружения."""
        if not cls.BOT_TOKEN:
            raise ValueError(
                "BOT_TOKEN не установлен! "
                "Создайте файл .env с переменной BOT_TOKEN=ваш_токен"
            )
        return True
