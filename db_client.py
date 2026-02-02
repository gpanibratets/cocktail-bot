"""
Клиент для работы с локальной базой данных коктейлей.
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
    image_path: Optional[str]  # Путь к локальному изображению
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


class CocktailDBClient:
    """Клиент для работы с локальной SQLite базой данных."""

    def __init__(self) -> None:
        self._db_path = Path(Config.DB_PATH)
        self._connection: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Получение соединения с базой данных."""
        if self._connection is None:
            if not self._db_path.exists():
                raise FileNotFoundError(f"База данных не найдена: {self._db_path}")
            self._connection = sqlite3.connect(self._db_path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _get_ingredients(self, cocktail_id: str) -> list[tuple[str, str]]:
        """Получение ингредиентов коктейля (на русском языке)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ingredient, ingredient_ru, measure, measure_ru
            FROM cocktail_ingredients
            WHERE cocktail_id = ?
            ORDER BY position
            """,
            (cocktail_id,),
        )
        # Используем русские переводы, если есть
        return [
            (
                row["ingredient_ru"] or row["ingredient"],
                row["measure_ru"] or row["measure"] or ""
            )
            for row in cursor.fetchall()
        ]

    def _row_to_cocktail(self, row: sqlite3.Row) -> Cocktail:
        """Преобразование строки БД в объект Cocktail."""
        ingredients = self._get_ingredients(row["id"])
        # Используем русскую категорию, если есть
        category = row["category_ru"] or row["category"] or "Unknown"
        return Cocktail(
            id=row["id"],
            name=row["name"] or "Unknown",
            category=category,
            alcoholic=row["alcoholic"] or "Unknown",
            glass=row["glass"] or "Unknown",
            instructions=row["instructions"] or "Нет инструкций",
            instructions_ru=row["instructions_ru"],
            image_url=row["image_url"] or "",
            image_path=row["image_local_path"],
            ingredients=ingredients,
        )

    def get_random_cocktail(self) -> Optional[Cocktail]:
        """Получение случайного коктейля."""
        logger.info("Fetching random cocktail from database")
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM cocktails
                ORDER BY RANDOM()
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_cocktail(row)
            return None
        except Exception as e:
            logger.error(f"Error fetching random cocktail: {e}")
            return None

    def search_by_name(self, name: str) -> list[Cocktail]:
        """Поиск коктейлей по названию."""
        logger.info(f"Searching cocktails by name: {name}")
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM cocktails
                WHERE name LIKE ?
                ORDER BY name
                LIMIT 10
                """,
                (f"%{name}%",),
            )
            return [self._row_to_cocktail(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error searching cocktails: {e}")
            return []

    def close(self) -> None:
        """Закрытие соединения с базой данных."""
        if self._connection:
            self._connection.close()
            self._connection = None


# Глобальный экземпляр клиента
db_client = CocktailDBClient()
