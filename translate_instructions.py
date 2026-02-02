#!/usr/bin/env python3
"""
Скрипт для перевода инструкций приготовления коктейлей на русский язык.
"""

import sqlite3
import asyncio
import json
from pathlib import Path
from openai import AsyncOpenAI
from config import Config


async def translate_instructions_batch(
    instructions: list[tuple[str, str]],  # (id, instruction)
    client: AsyncOpenAI
) -> dict[str, str]:
    """Перевод инструкций через OpenAI."""

    system_prompt = """Ты переводчик рецептов коктейлей на русский язык.
Переводи инструкции приготовления естественным русским языком.
Используй повелительное наклонение (например: "Смешайте", "Добавьте", "Украсьте").
Сохраняй барную терминологию (шейкер, джиггер, мадлер и т.д.).
Отвечай только JSON объектом где ключ - ID коктейля, значение - перевод."""

    # Разбиваем на батчи по 20 инструкций
    batch_size = 20
    all_translations = {}

    for i in range(0, len(instructions), batch_size):
        batch = instructions[i:i + batch_size]
        batch_text = "\n\n".join(
            f"ID: {cid}\nInstruction: {instr}"
            for cid, instr in batch
        )

        print(f"  Перевод батча {i // batch_size + 1}/{(len(instructions) + batch_size - 1) // batch_size}...")

        try:
            response = await client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Переведи следующие инструкции:\n\n{batch_text}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            result = json.loads(response.choices[0].message.content)
            all_translations.update(result)

        except Exception as e:
            print(f"    Ошибка при переводе батча: {e}")
            # Для ошибочных - оставляем пустую строку
            for cid, _ in batch:
                if cid not in all_translations:
                    all_translations[cid] = ""

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

    # Получаем все коктейли без русских инструкций
    cursor.execute("""
        SELECT id, instructions
        FROM cocktails
        WHERE (instructions_ru IS NULL OR instructions_ru = '')
          AND instructions IS NOT NULL AND instructions != ''
    """)
    rows = cursor.fetchall()
    instructions = [(row["id"], row["instructions"]) for row in rows]
    print(f"Найдено {len(instructions)} коктейлей для перевода")

    if not instructions:
        print("Все инструкции уже переведены!")
        return

    # Проверяем наличие файла с кешем переводов
    cache_file = Path("data/instructions_translations.json")
    if cache_file.exists():
        print("Загружаю кеш переводов...")
        with open(cache_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
    else:
        translations = {}

    # Находим непереведённые
    untranslated = [(cid, instr) for cid, instr in instructions if cid not in translations]

    if untranslated:
        print(f"Нужно перевести {len(untranslated)} инструкций")

        if not Config.OPENAI_API_KEY:
            print("OPENAI_API_KEY не настроен! Установите ключ в .env")
            return

        client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        new_translations = await translate_instructions_batch(untranslated, client)
        translations.update(new_translations)

        # Сохраняем кеш
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)
        print(f"Кеш сохранён в {cache_file}")

    # Обновляем базу данных
    print("\nОбновление базы данных...")
    updated = 0
    for cid, _ in instructions:
        if cid in translations and translations[cid]:
            cursor.execute(
                "UPDATE cocktails SET instructions_ru = ? WHERE id = ?",
                (translations[cid], cid)
            )
            updated += 1

    conn.commit()
    print(f"Обновлено {updated} записей")

    # Показываем примеры
    print("\nПримеры переводов:")
    cursor.execute("""
        SELECT name, substr(instructions, 1, 60) as instr,
               substr(instructions_ru, 1, 60) as instr_ru
        FROM cocktails
        WHERE instructions_ru IS NOT NULL AND instructions_ru != ''
        LIMIT 5
    """)
    for row in cursor.fetchall():
        print(f"  {row['name']}:")
        print(f"    EN: {row['instr']}...")
        print(f"    RU: {row['instr_ru']}...")
        print()

    conn.close()
    print("Готово!")


if __name__ == "__main__":
    asyncio.run(main())
