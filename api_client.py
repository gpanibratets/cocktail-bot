"""
Клиент для работы с TheCocktailDB API.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from functools import lru_cache
from time import time

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class Cocktail:
    """Класс для представления коктейля."""

    id: str
    name: str
    category: str
    alcoholic: str
    glass: str
    instructions: str
    instructions_ru: Optional[str]
    image_url: str
    ingredients: list[tuple[str, str]]  # (ингредиент, мера)

    def format_ingredients(self) -> str:
        """Форматирование списка ингредиентов для отображения."""
        lines = []
        for ingredient, measure in self.ingredients:
            if measure and measure.strip():
                lines.append(f"• {ingredient} — {measure}")
            else:
                lines.append(f"• {ingredient}")
        return "\n".join(lines)

    def get_alcoholic_emoji(self) -> str:
        """Получение эмодзи в зависимости от алкогольности."""
        if self.alcoholic.lower() == "alcoholic":
            return "🍸"
        elif self.alcoholic.lower() == "non alcoholic":
            return "🥤"
        return "🍹"

    def to_message(self) -> str:
        """Форматирование коктейля для отправки в Telegram."""
        alcoholic_ru = {
            "Alcoholic": "Алкогольный",
            "Non alcoholic": "Безалкогольный",
            "Optional alcohol": "Опционально алкогольный",
        }.get(self.alcoholic, self.alcoholic)

        # Используем русские инструкции, если есть
        instructions = self.instructions_ru or self.instructions

        message = (
            f"{self.get_alcoholic_emoji()} *{self.name}*\n\n"
            f"🏷️ *Категория:* {self.category}\n"
            f"🍷 *Тип:* {alcoholic_ru}\n"
            f"🥃 *Стакан:* {self.glass}\n\n"
            f"📋 *Ингредиенты:*\n{self.format_ingredients()}\n\n"
            f"📝 *Приготовление:*\n{instructions}\n\n"
            f"─────────────────────\n"
            f"Хотите ещё коктейль? Нажмите /random"
        )
        return message


class CocktailAPIClient:
    """Асинхронный клиент для TheCocktailDB API."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: dict[str, tuple[float, any]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение или создание HTTP-сессии."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Закрытие HTTP-сессии."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_from_cache(self, key: str) -> Optional[any]:
        """Получение данных из кеша."""
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time() - timestamp < Config.CACHE_TTL:
                logger.debug(f"Cache hit for key: {key}")
                return data
            else:
                del self._cache[key]
        return None

    def _set_cache(self, key: str, data: any) -> None:
        """Сохранение данных в кеш."""
        self._cache[key] = (time(), data)

    async def _fetch(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Выполнение HTTP-запроса к API."""
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API returned status {response.status} for {url}")
                    return None
        except aiohttp.ClientTimeout:
            logger.error(f"Timeout while fetching {url}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Client error while fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching {url}: {e}")
            return None

    def _parse_cocktail(self, data: dict) -> Optional[Cocktail]:
        """Парсинг данных коктейля из JSON."""
        try:
            # Собираем ингредиенты (до 15 возможных)
            ingredients = []
            for i in range(1, 16):
                ingredient = data.get(f"strIngredient{i}")
                measure = data.get(f"strMeasure{i}")
                if ingredient and ingredient.strip():
                    ingredients.append((ingredient.strip(), (measure or "").strip()))

            return Cocktail(
                id=data.get("idDrink", ""),
                name=data.get("strDrink", "Unknown"),
                category=data.get("strCategory", "Unknown"),
                alcoholic=data.get("strAlcoholic", "Unknown"),
                glass=data.get("strGlass", "Unknown"),
                instructions=data.get("strInstructions", "Нет инструкций"),
                instructions_ru=data.get("strInstructionsRU"),
                image_url=data.get("strDrinkThumb", ""),
                ingredients=ingredients,
            )
        except Exception as e:
            logger.error(f"Error parsing cocktail data: {e}")
            return None

    async def get_random_cocktail(self) -> Optional[Cocktail]:
        """Получение случайного коктейля."""
        logger.info("Fetching random cocktail")
        data = await self._fetch(Config.RANDOM_COCKTAIL_URL)

        if data and data.get("drinks"):
            return self._parse_cocktail(data["drinks"][0])
        return None

    async def search_by_name(self, name: str) -> list[Cocktail]:
        """Поиск коктейлей по названию."""
        logger.info(f"Searching cocktails by name: {name}")

        # Проверяем кеш
        cache_key = f"search_name_{name.lower()}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = await self._fetch(Config.SEARCH_BY_NAME_URL, params={"s": name})

        cocktails = []
        if data and data.get("drinks"):
            for drink_data in data["drinks"]:
                cocktail = self._parse_cocktail(drink_data)
                if cocktail:
                    cocktails.append(cocktail)

        self._set_cache(cache_key, cocktails)
        return cocktails

    async def search_by_ingredient(self, ingredient: str) -> list[dict]:
        """
        Поиск коктейлей по ингредиенту.
        Возвращает базовую информацию (требуется дополнительный запрос для деталей).
        """
        logger.info(f"Searching cocktails by ingredient: {ingredient}")

        # Проверяем кеш
        cache_key = f"search_ingredient_{ingredient.lower()}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = await self._fetch(
            Config.SEARCH_BY_INGREDIENT_URL, params={"i": ingredient}
        )

        results = []
        if data and data.get("drinks"):
            for drink in data["drinks"]:
                results.append(
                    {
                        "id": drink.get("idDrink"),
                        "name": drink.get("strDrink"),
                        "image_url": drink.get("strDrinkThumb"),
                    }
                )

        self._set_cache(cache_key, results)
        return results

    async def get_cocktail_by_id(self, cocktail_id: str) -> Optional[Cocktail]:
        """Получение полной информации о коктейле по ID."""
        logger.info(f"Fetching cocktail by ID: {cocktail_id}")

        # Проверяем кеш
        cache_key = f"cocktail_{cocktail_id}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = await self._fetch(Config.LOOKUP_BY_ID_URL, params={"i": cocktail_id})

        if data and data.get("drinks"):
            cocktail = self._parse_cocktail(data["drinks"][0])
            if cocktail:
                self._set_cache(cache_key, cocktail)
            return cocktail
        return None


# Глобальный экземпляр клиента
api_client = CocktailAPIClient()
