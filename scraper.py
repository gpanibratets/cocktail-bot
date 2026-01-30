#!/usr/bin/env python3
"""
Парсер коктейлей из TheCocktailDB.
Скачивает все коктейли, ингредиенты и изображения.

Запуск:
    python scraper.py

Для возобновления после прерывания просто запустите скрипт снова.
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import string

import aiohttp

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Конфигурация
BASE_URL = "https://www.thecocktaildb.com/api/json/v1/1"
DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"
COCKTAIL_IMAGES_DIR = IMAGES_DIR / "cocktails"
INGREDIENT_IMAGES_DIR = IMAGES_DIR / "ingredients"
DB_PATH = DATA_DIR / "cocktails.db"
PROGRESS_FILE = DATA_DIR / "scraper_progress.json"

# Rate limiting (секунды между запросами)
REQUEST_DELAY = 2.0  # 2 секунды между запросами
IMAGE_DELAY = 1.0    # 1 секунда между скачиванием изображений


@dataclass
class ScraperProgress:
    """Прогресс скачивания."""
    cocktails_downloaded: list[str]  # список ID скачанных коктейлей
    ingredients_downloaded: list[str]  # список скачанных ингредиентов
    cocktail_images_downloaded: list[str]  # список ID коктейлей с изображениями
    ingredient_images_downloaded: list[str]  # список ингредиентов с изображениями
    started_at: str
    last_updated: str

    @classmethod
    def load(cls) -> "ScraperProgress":
        """Загрузка прогресса из файла."""
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return cls(**data)
            except Exception as e:
                logger.warning(f"Не удалось загрузить прогресс: {e}")

        return cls(
            cocktails_downloaded=[],
            ingredients_downloaded=[],
            cocktail_images_downloaded=[],
            ingredient_images_downloaded=[],
            started_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
        )

    def save(self) -> None:
        """Сохранение прогресса в файл."""
        self.last_updated = datetime.now().isoformat()
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)


class CocktailScraper:
    """Парсер коктейлей."""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.progress = ScraperProgress.load()
        self.db_conn: Optional[sqlite3.Connection] = None

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def setup(self) -> None:
        """Инициализация."""
        # Создаём директории
        DATA_DIR.mkdir(exist_ok=True)
        COCKTAIL_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        INGREDIENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

        # Создаём HTTP сессию
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)

        # Инициализируем БД
        self._init_db()

        logger.info("Scraper инициализирован")
        logger.info(f"Прогресс: {len(self.progress.cocktails_downloaded)} коктейлей, "
                   f"{len(self.progress.ingredients_downloaded)} ингредиентов")

    async def cleanup(self) -> None:
        """Очистка ресурсов."""
        if self.session:
            await self.session.close()
        if self.db_conn:
            self.db_conn.close()
        self.progress.save()
        logger.info("Scraper завершён")

    def _init_db(self) -> None:
        """Инициализация базы данных."""
        self.db_conn = sqlite3.connect(DB_PATH)
        cursor = self.db_conn.cursor()

        # Таблица коктейлей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cocktails (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                alcoholic TEXT,
                glass TEXT,
                instructions TEXT,
                instructions_ru TEXT,
                instructions_de TEXT,
                instructions_fr TEXT,
                instructions_es TEXT,
                instructions_it TEXT,
                image_url TEXT,
                image_local_path TEXT,
                tags TEXT,
                video_url TEXT,
                iba TEXT,
                date_modified TEXT,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица ингредиентов коктейля
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cocktail_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cocktail_id TEXT NOT NULL,
                ingredient TEXT NOT NULL,
                measure TEXT,
                position INTEGER,
                FOREIGN KEY (cocktail_id) REFERENCES cocktails(id)
            )
        """)

        # Таблица ингредиентов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingredients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                type TEXT,
                alcohol TEXT,
                abv TEXT,
                image_url TEXT,
                image_local_path TEXT,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Индексы
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cocktails_name ON cocktails(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cocktails_category ON cocktails(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ingredients_cocktail ON cocktail_ingredients(cocktail_id)")

        self.db_conn.commit()
        logger.info("База данных инициализирована")

    async def _fetch_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Выполнение HTTP запроса с rate limiting."""
        try:
            await asyncio.sleep(REQUEST_DELAY)
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"HTTP {response.status} для {url}")
                    return None
        except Exception as e:
            logger.error(f"Ошибка запроса {url}: {e}")
            return None

    async def _download_image(self, url: str, save_path: Path) -> bool:
        """Скачивание изображения."""
        if save_path.exists():
            return True

        try:
            await asyncio.sleep(IMAGE_DELAY)
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(save_path, "wb") as f:
                        f.write(content)
                    return True
                else:
                    logger.warning(f"Не удалось скачать {url}: HTTP {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Ошибка скачивания {url}: {e}")
            return False

    async def get_all_cocktail_ids(self) -> list[str]:
        """Получение ID всех коктейлей через поиск по буквам."""
        all_ids = set()

        # Поиск по каждой букве алфавита
        letters = string.ascii_lowercase + string.digits

        for letter in letters:
            logger.info(f"Поиск коктейлей на букву '{letter}'...")
            data = await self._fetch_json(f"{BASE_URL}/search.php", {"f": letter})

            if data and data.get("drinks"):
                for drink in data["drinks"]:
                    drink_id = drink.get("idDrink")
                    if drink_id:
                        all_ids.add(drink_id)
                logger.info(f"  Найдено {len(data['drinks'])} коктейлей")
            else:
                logger.info(f"  Коктейлей не найдено")

        logger.info(f"Всего уникальных коктейлей: {len(all_ids)}")
        return sorted(all_ids)

    async def get_all_ingredients(self) -> list[str]:
        """Получение списка всех ингредиентов."""
        data = await self._fetch_json(f"{BASE_URL}/list.php", {"i": "list"})

        if data and data.get("drinks"):
            ingredients = [d.get("strIngredient1") for d in data["drinks"] if d.get("strIngredient1")]
            logger.info(f"Найдено {len(ingredients)} ингредиентов")
            return sorted(ingredients)

        return []

    async def download_cocktail(self, cocktail_id: str) -> bool:
        """Скачивание данных коктейля."""
        if cocktail_id in self.progress.cocktails_downloaded:
            return True

        data = await self._fetch_json(f"{BASE_URL}/lookup.php", {"i": cocktail_id})

        if not data or not data.get("drinks"):
            logger.warning(f"Коктейль {cocktail_id} не найден")
            return False

        drink = data["drinks"][0]

        # Собираем ингредиенты
        ingredients = []
        for i in range(1, 16):
            ingredient = drink.get(f"strIngredient{i}")
            measure = drink.get(f"strMeasure{i}")
            if ingredient and ingredient.strip():
                ingredients.append((ingredient.strip(), (measure or "").strip(), i))

        # Сохраняем в БД
        cursor = self.db_conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO cocktails
            (id, name, category, alcoholic, glass, instructions, instructions_ru,
             instructions_de, instructions_fr, instructions_es, instructions_it,
             image_url, tags, video_url, iba, date_modified, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            drink.get("idDrink"),
            drink.get("strDrink"),
            drink.get("strCategory"),
            drink.get("strAlcoholic"),
            drink.get("strGlass"),
            drink.get("strInstructions"),
            drink.get("strInstructionsRU"),
            drink.get("strInstructionsDE"),
            drink.get("strInstructionsFR"),
            drink.get("strInstructionsES"),
            drink.get("strInstructionsIT"),
            drink.get("strDrinkThumb"),
            drink.get("strTags"),
            drink.get("strVideo"),
            drink.get("strIBA"),
            drink.get("dateModified"),
            json.dumps(drink, ensure_ascii=False),
        ))

        # Удаляем старые ингредиенты и добавляем новые
        cursor.execute("DELETE FROM cocktail_ingredients WHERE cocktail_id = ?", (cocktail_id,))
        for ingredient, measure, pos in ingredients:
            cursor.execute("""
                INSERT INTO cocktail_ingredients (cocktail_id, ingredient, measure, position)
                VALUES (?, ?, ?, ?)
            """, (cocktail_id, ingredient, measure, pos))

        self.db_conn.commit()

        self.progress.cocktails_downloaded.append(cocktail_id)
        self.progress.save()

        logger.info(f"Скачан коктейль: {drink.get('strDrink')} ({cocktail_id})")
        return True

    async def download_ingredient(self, ingredient_name: str) -> bool:
        """Скачивание данных ингредиента."""
        if ingredient_name in self.progress.ingredients_downloaded:
            return True

        data = await self._fetch_json(f"{BASE_URL}/search.php", {"i": ingredient_name})

        if not data or not data.get("ingredients"):
            logger.warning(f"Ингредиент '{ingredient_name}' не найден")
            return False

        ing = data["ingredients"][0]

        # URL изображения ингредиента
        image_url = f"https://www.thecocktaildb.com/images/ingredients/{ingredient_name}-Medium.png"

        cursor = self.db_conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO ingredients
            (id, name, description, type, alcohol, abv, image_url, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ing.get("idIngredient"),
            ing.get("strIngredient"),
            ing.get("strDescription"),
            ing.get("strType"),
            ing.get("strAlcohol"),
            ing.get("strABV"),
            image_url,
            json.dumps(ing, ensure_ascii=False),
        ))
        self.db_conn.commit()

        self.progress.ingredients_downloaded.append(ingredient_name)
        self.progress.save()

        logger.info(f"Скачан ингредиент: {ingredient_name}")
        return True

    async def download_cocktail_image(self, cocktail_id: str) -> bool:
        """Скачивание изображения коктейля."""
        if cocktail_id in self.progress.cocktail_images_downloaded:
            return True

        cursor = self.db_conn.cursor()
        cursor.execute("SELECT image_url FROM cocktails WHERE id = ?", (cocktail_id,))
        row = cursor.fetchone()

        if not row or not row[0]:
            return False

        image_url = row[0]
        # Добавляем /preview для уменьшенной версии (быстрее скачивается)
        # Можно убрать /preview для полного размера
        image_path = COCKTAIL_IMAGES_DIR / f"{cocktail_id}.jpg"

        if await self._download_image(image_url, image_path):
            cursor.execute(
                "UPDATE cocktails SET image_local_path = ? WHERE id = ?",
                (str(image_path), cocktail_id)
            )
            self.db_conn.commit()
            self.progress.cocktail_images_downloaded.append(cocktail_id)
            self.progress.save()
            logger.info(f"Скачано изображение коктейля {cocktail_id}")
            return True

        return False

    async def download_ingredient_image(self, ingredient_name: str) -> bool:
        """Скачивание изображения ингредиента."""
        if ingredient_name in self.progress.ingredient_images_downloaded:
            return True

        # URL изображения ингредиента (Medium размер)
        safe_name = ingredient_name.replace(" ", "%20").replace("/", "-")
        image_url = f"https://www.thecocktaildb.com/images/ingredients/{safe_name}-Medium.png"

        # Безопасное имя файла
        safe_filename = ingredient_name.replace("/", "-").replace(" ", "_")
        image_path = INGREDIENT_IMAGES_DIR / f"{safe_filename}.png"

        if await self._download_image(image_url, image_path):
            cursor = self.db_conn.cursor()
            cursor.execute(
                "UPDATE ingredients SET image_local_path = ? WHERE name = ?",
                (str(image_path), ingredient_name)
            )
            self.db_conn.commit()
            self.progress.ingredient_images_downloaded.append(ingredient_name)
            self.progress.save()
            logger.info(f"Скачано изображение ингредиента: {ingredient_name}")
            return True

        return False

    async def run(self) -> None:
        """Запуск полного скачивания."""
        logger.info("=" * 60)
        logger.info("Начало скачивания базы коктейлей")
        logger.info("=" * 60)

        # 1. Получаем список всех коктейлей
        logger.info("\n[1/5] Получение списка коктейлей...")
        all_cocktail_ids = await self.get_all_cocktail_ids()

        # 2. Скачиваем данные коктейлей
        logger.info(f"\n[2/5] Скачивание данных коктейлей ({len(all_cocktail_ids)} шт.)...")
        remaining = [cid for cid in all_cocktail_ids if cid not in self.progress.cocktails_downloaded]
        logger.info(f"Осталось скачать: {len(remaining)} коктейлей")

        for i, cocktail_id in enumerate(remaining, 1):
            await self.download_cocktail(cocktail_id)
            if i % 10 == 0:
                logger.info(f"Прогресс: {i}/{len(remaining)} коктейлей")

        # 3. Получаем и скачиваем ингредиенты
        logger.info("\n[3/5] Скачивание данных ингредиентов...")
        all_ingredients = await self.get_all_ingredients()
        remaining_ing = [ing for ing in all_ingredients if ing not in self.progress.ingredients_downloaded]
        logger.info(f"Осталось скачать: {len(remaining_ing)} ингредиентов")

        for i, ingredient in enumerate(remaining_ing, 1):
            await self.download_ingredient(ingredient)
            if i % 10 == 0:
                logger.info(f"Прогресс: {i}/{len(remaining_ing)} ингредиентов")

        # 4. Скачиваем изображения коктейлей
        logger.info("\n[4/5] Скачивание изображений коктейлей...")
        remaining_img = [cid for cid in all_cocktail_ids if cid not in self.progress.cocktail_images_downloaded]
        logger.info(f"Осталось скачать: {len(remaining_img)} изображений коктейлей")

        for i, cocktail_id in enumerate(remaining_img, 1):
            await self.download_cocktail_image(cocktail_id)
            if i % 20 == 0:
                logger.info(f"Прогресс: {i}/{len(remaining_img)} изображений")

        # 5. Скачиваем изображения ингредиентов
        logger.info("\n[5/5] Скачивание изображений ингредиентов...")
        remaining_ing_img = [ing for ing in all_ingredients if ing not in self.progress.ingredient_images_downloaded]
        logger.info(f"Осталось скачать: {len(remaining_ing_img)} изображений ингредиентов")

        for i, ingredient in enumerate(remaining_ing_img, 1):
            await self.download_ingredient_image(ingredient)
            if i % 20 == 0:
                logger.info(f"Прогресс: {i}/{len(remaining_ing_img)} изображений")

        # Итоги
        logger.info("\n" + "=" * 60)
        logger.info("Скачивание завершено!")
        logger.info(f"Коктейлей: {len(self.progress.cocktails_downloaded)}")
        logger.info(f"Ингредиентов: {len(self.progress.ingredients_downloaded)}")
        logger.info(f"Изображений коктейлей: {len(self.progress.cocktail_images_downloaded)}")
        logger.info(f"Изображений ингредиентов: {len(self.progress.ingredient_images_downloaded)}")
        logger.info("=" * 60)

        # Экспорт в JSON
        await self.export_to_json()

    async def export_to_json(self) -> None:
        """Экспорт данных в JSON файлы."""
        logger.info("Экспорт данных в JSON...")

        cursor = self.db_conn.cursor()

        # Экспорт коктейлей
        cursor.execute("""
            SELECT c.*, GROUP_CONCAT(ci.ingredient || '::' || COALESCE(ci.measure, ''), '||') as ingredients_list
            FROM cocktails c
            LEFT JOIN cocktail_ingredients ci ON c.id = ci.cocktail_id
            GROUP BY c.id
        """)

        columns = [desc[0] for desc in cursor.description]
        cocktails = []
        for row in cursor.fetchall():
            cocktail = dict(zip(columns, row))
            # Парсим ингредиенты
            if cocktail.get("ingredients_list"):
                cocktail["ingredients"] = [
                    {"ingredient": i.split("::")[0], "measure": i.split("::")[1] if "::" in i else ""}
                    for i in cocktail["ingredients_list"].split("||") if i
                ]
            del cocktail["ingredients_list"]
            cocktails.append(cocktail)

        with open(DATA_DIR / "cocktails.json", "w", encoding="utf-8") as f:
            json.dump(cocktails, f, ensure_ascii=False, indent=2)
        logger.info(f"Экспортировано {len(cocktails)} коктейлей в cocktails.json")

        # Экспорт ингредиентов
        cursor.execute("SELECT * FROM ingredients")
        columns = [desc[0] for desc in cursor.description]
        ingredients = [dict(zip(columns, row)) for row in cursor.fetchall()]

        with open(DATA_DIR / "ingredients.json", "w", encoding="utf-8") as f:
            json.dump(ingredients, f, ensure_ascii=False, indent=2)
        logger.info(f"Экспортировано {len(ingredients)} ингредиентов в ingredients.json")


async def main():
    """Главная функция."""
    async with CocktailScraper() as scraper:
        await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
