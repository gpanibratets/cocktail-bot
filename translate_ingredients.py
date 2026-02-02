#!/usr/bin/env python3
"""
Скрипт для перевода ингредиентов и мер на русский язык.
"""

import re
import sqlite3
import asyncio
import json
from pathlib import Path
from openai import AsyncOpenAI
from config import Config

# Конверсия единиц измерения
MEASURE_CONVERSIONS = {
    # Объёмные меры → миллилитры
    "oz": ("мл", 30),       # 1 oz ≈ 30 мл
    "cl": ("мл", 10),       # 1 cl = 10 мл
    "ml": ("мл", 1),
    "dl": ("мл", 100),      # 1 dl = 100 мл
    "L": ("л", 1),
    "l": ("л", 1),
    "pint": ("мл", 470),    # 1 pint ≈ 470 мл
    "qt": ("л", 0.95),      # 1 qt ≈ 0.95 л
    "gal": ("л", 3.8),      # 1 gal ≈ 3.8 л
    "cup": ("мл", 240),     # 1 cup ≈ 240 мл
    "glass": ("стакан", 1),

    # Ложки
    "tsp": ("ч.л.", 1),           # чайная ложка
    "tblsp": ("ст.л.", 1),        # столовая ложка
    "tbsp": ("ст.л.", 1),

    # Порции
    "shot": ("шот", 1),           # ~45 мл
    "shots": ("шота", 1),
    "jigger": ("джиггер", 1),     # ~45 мл
    "part": ("часть", 1),
    "parts": ("части", 1),
    "measure": ("мера", 1),
    "measures": ("меры", 1),
    "fifth": ("бутылки", 0.2),    # 1/5 бутылки

    # Штучные
    "dash": ("дэш", 1),           # капля/немного
    "dashes": ("дэша", 1),
    "drop": ("капля", 1),
    "drops": ("капель", 1),
    "pinch": ("щепотка", 1),
    "splash": ("немного", 1),
    "splashes": ("немного", 1),

    # Штуки
    "slice": ("долька", 1),
    "slices": ("дольки", 1),
    "wedge": ("долька", 1),
    "wedges": ("дольки", 1),
    "sprig": ("веточка", 1),
    "sprigs": ("веточки", 1),
    "piece": ("кусочек", 1),
    "pieces": ("кусочка", 1),
    "cube": ("кубик", 1),
    "cubes": ("кубика", 1),
    "stick": ("палочка", 1),
    "bottle": ("бутылка", 1),
    "bottles": ("бутылки", 1),
    "can": ("банка", 1),
    "cans": ("банки", 1),
    "package": ("пакет", 1),
    "packages": ("пакета", 1),
    "scoop": ("шарик", 1),
    "scoops": ("шарика", 1),
    "chunk": ("кусок", 1),
    "chunks": ("куска", 1),
    "strip": ("полоска", 1),
    "strips": ("полоски", 1),
    "lb": ("г", 450),            # 1 lb ≈ 450 г
    "gr": ("г", 1),
    "whole": ("целый", 1),
    "inch": ("см", 2.5),
}

# Дополнительные слова для перевода в мерах
MEASURE_WORDS = {
    "Fresh": "свежий",
    "fresh": "свежий",
    "frozen": "замороженный",
    "crushed": "дроблёный",
    "ground": "молотый",
    "chopped": "нарезанный",
    "dried": "сушёный",
    "hot": "горячий",
    "cold": "холодный",
    "chilled": "охлаждённый",
    "boiling": "кипящий",
    "iced": "со льдом",
    "strong": "крепкий",
    "black": "чёрный",
    "white": "белый",
    "plain": "обычный",
    "instant": "растворимый",
    "sweetened": "подслащённый",
    "unsweetened": "без сахара",
    "skimmed": "обезжиренный",
    "superfine": "мелкий",
    "large": "большой",
    "small": "маленький",
    "Top": "долить",
    "top": "долить",
    "Fill": "наполнить",
    "fill": "наполнить",
    "Garnish": "для украшения",
    "garnish": "для украшения",
    "Garnish with": "для украшения",
    "garnish with": "для украшения",
    "Add": "добавить",
    "Juice of": "сок",
    "Twist of": "цедра",
    "Squeeze": "выжать сок",
    "Rimmed": "на ободке",
    "rimmed": "на ободке",
    "with": "",
}

# Словарь переводов ингредиентов (будет дополнен через LLM)
INGREDIENT_TRANSLATIONS = {}


def convert_measure(measure: str) -> str:
    """Конвертация меры в русский формат."""
    if not measure or not measure.strip():
        return ""

    original = measure.strip()
    result = original

    # Специальные случаи
    if result.lower() in ("to taste", "as needed"):
        return "по вкусу"
    if result.lower() == "garnish":
        return "для украшения"
    if result.lower() in ("top", "top up", "top up with", "fill", "fill with", "fill to top with"):
        return "долить"

    # Обработка "Juice of X"
    juice_match = re.match(r"Juice of\s+(\d+(?:/\d+)?)\s*(.*)?", result, re.IGNORECASE)
    if juice_match:
        num = juice_match.group(1)
        rest = juice_match.group(2) or ""
        return f"сок {num} шт. {rest}".strip()

    # Обработка "Twist of" и "1 twist of"
    if re.match(r"^(\d+\s+)?twist of", result, re.IGNORECASE):
        return "цедра"

    # Конвертируем единицы измерения
    # Сначала обрабатываем дроби вида "1/2 oz", "3/4 cl"
    fraction_pattern = rf"(\d+)\s+(\d+)/(\d+)\s*(oz|cl|ml|tsp|tblsp|tbsp)(?!\w)"

    def replace_mixed_fraction(m):
        whole = int(m.group(1))
        num = int(m.group(2))
        denom = int(m.group(3))
        unit = m.group(4).lower()
        value = whole + num / denom

        if unit in MEASURE_CONVERSIONS:
            ru_unit, mult = MEASURE_CONVERSIONS[unit]
            if mult != 1 and ru_unit == "мл":
                return f"{int(value * mult)} {ru_unit}"
            return f"{value:.1f}".rstrip('0').rstrip('.') + f" {ru_unit}"
        return m.group(0)

    result = re.sub(fraction_pattern, replace_mixed_fraction, result, flags=re.IGNORECASE)

    # Обрабатываем простые дроби "1/2 oz"
    simple_frac_pattern = rf"(\d+)/(\d+)\s*(oz|cl|ml|tsp|tblsp|tbsp)(?!\w)"

    def replace_simple_fraction(m):
        num = int(m.group(1))
        denom = int(m.group(2))
        unit = m.group(3).lower()
        value = num / denom

        if unit in MEASURE_CONVERSIONS:
            ru_unit, mult = MEASURE_CONVERSIONS[unit]
            if mult != 1 and ru_unit == "мл":
                return f"{int(value * mult)} {ru_unit}"
            return f"{value:.1f}".rstrip('0').rstrip('.') + f" {ru_unit}"
        return m.group(0)

    result = re.sub(simple_frac_pattern, replace_simple_fraction, result, flags=re.IGNORECASE)

    for unit, (ru_unit, multiplier) in MEASURE_CONVERSIONS.items():
        # Паттерн для числа + единицы (например "1 oz", "1.5 cl", "2-3 oz")
        pattern = rf"(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?)\s*{re.escape(unit)}(?!\w)"

        def replace_unit(m, mult=multiplier, ru=ru_unit):
            num_str = m.group(1)
            # Если это диапазон
            if "-" in num_str or "–" in num_str:
                parts = re.split(r"[-–]", num_str)
                if mult != 1 and ru == "мл":
                    converted = [str(int(float(p.strip()) * mult)) for p in parts]
                    return f"{'-'.join(converted)} {ru}"
                return f"{num_str} {ru}"
            else:
                num = float(num_str)
                if mult != 1 and ru == "мл":
                    converted = int(num * mult)
                    return f"{converted} {ru}"
                return f"{num_str} {ru}"

        result = re.sub(pattern, replace_unit, result, flags=re.IGNORECASE)

    # Обрабатываем одиночные слова (dash, splash, etc.)
    standalone_words = {
        "dash": "дэш",
        "splash": "немного",
        "pinch": "щепотка",
        "garnish": "для украшения",
        "fill": "наполнить",
    }
    for en, ru in standalone_words.items():
        result = re.sub(rf"^{en}$", ru, result, flags=re.IGNORECASE)

    # Переводим дополнительные слова
    for en, ru in MEASURE_WORDS.items():
        result = re.sub(rf"\b{re.escape(en)}\b", ru, result)

    return result.strip()


async def translate_ingredients_batch(ingredients: list[str], client: AsyncOpenAI) -> dict[str, str]:
    """Перевод списка ингредиентов через OpenAI."""
    prompt = """Переведи названия ингредиентов для коктейлей на русский язык.
Сохраняй контекст барной культуры. Некоторые названия брендов оставь как есть (Bacardi, Absolut, etc).
Для технических терминов используй общепринятые русские аналоги.

Верни JSON объект где ключ - английское название, значение - русский перевод.

Ингредиенты для перевода:
"""

    # Разбиваем на батчи по 50 ингредиентов
    batch_size = 50
    all_translations = {}

    for i in range(0, len(ingredients), batch_size):
        batch = ingredients[i:i + batch_size]
        batch_text = "\n".join(f"- {ing}" for ing in batch)

        print(f"  Перевод батча {i // batch_size + 1}/{(len(ingredients) + batch_size - 1) // batch_size}...")

        try:
            response = await client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты переводчик барных терминов. Отвечай только JSON."},
                    {"role": "user", "content": prompt + batch_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            result = json.loads(response.choices[0].message.content)
            all_translations.update(result)

        except Exception as e:
            print(f"    Ошибка при переводе батча: {e}")
            # Для ошибочных - оставляем оригинал
            for ing in batch:
                if ing not in all_translations:
                    all_translations[ing] = ing

    return all_translations


async def main():
    """Основная функция."""
    db_path = Path(Config.DB_PATH)
    if not db_path.exists():
        print(f"База данных не найдена: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Получаем все записи
    cursor.execute("SELECT DISTINCT ingredient FROM cocktail_ingredients ORDER BY ingredient")
    ingredients = [row[0] for row in cursor.fetchall()]
    print(f"Найдено {len(ingredients)} уникальных ингредиентов")

    # Проверяем наличие файла с кешем переводов
    cache_file = Path("data/ingredient_translations.json")
    if cache_file.exists():
        print("Загружаю кеш переводов...")
        with open(cache_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
    else:
        translations = {}

    # Находим непереведённые ингредиенты
    untranslated = [ing for ing in ingredients if ing not in translations]

    if untranslated:
        print(f"Нужно перевести {len(untranslated)} ингредиентов")

        if not Config.OPENAI_API_KEY:
            print("OPENAI_API_KEY не настроен! Установите ключ в .env")
            return

        client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        new_translations = await translate_ingredients_batch(untranslated, client)
        translations.update(new_translations)

        # Сохраняем кеш
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)
        print(f"Кеш сохранён в {cache_file}")

    # Обновляем базу данных
    print("\nОбновление базы данных...")
    cursor.execute("SELECT cocktail_id, position, ingredient, measure FROM cocktail_ingredients")
    rows = cursor.fetchall()

    updated = 0
    for row in rows:
        cocktail_id = row["cocktail_id"]
        position = row["position"]
        ingredient = row["ingredient"]
        measure = row["measure"]

        # Переводим
        ingredient_ru = translations.get(ingredient, ingredient)
        measure_ru = convert_measure(measure) if measure else ""

        cursor.execute(
            "UPDATE cocktail_ingredients SET ingredient_ru = ?, measure_ru = ? WHERE cocktail_id = ? AND position = ?",
            (ingredient_ru, measure_ru, cocktail_id, position)
        )
        updated += 1

    conn.commit()
    print(f"Обновлено {updated} записей")

    # Показываем примеры
    print("\nПримеры переводов:")
    cursor.execute("""
        SELECT ingredient, ingredient_ru, measure, measure_ru
        FROM cocktail_ingredients
        WHERE measure IS NOT NULL AND measure != ''
        LIMIT 15
    """)
    for row in cursor.fetchall():
        print(f"  {row['ingredient']}: {row['measure']} → {row['ingredient_ru']}: {row['measure_ru']}")

    conn.close()
    print("\nГотово!")


if __name__ == "__main__":
    asyncio.run(main())
