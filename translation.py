"""
Интеграция с Google Cloud Translation API.

Используется для перевода инструкций коктейлей на нужный язык (по умолчанию — ru).
Перевод опционален: если не задан GOOGLE_TRANSLATE_API_KEY, функции
возвращают None и не ломают работу бота.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import aiohttp

from config import Config

logger = logging.getLogger(__name__)

# Простейший in-memory кеш: (text, target_lang) -> translated_text
_cache: Dict[Tuple[str, str], str] = {}


async def translate_text(text: str, target_lang: Optional[str] = None) -> Optional[str]:
    """
    Перевод текста через Google Cloud Translation API.

    Возвращает переведённый текст или None в случае ошибки / отключённого API.
    """
    api_key = Config.GOOGLE_TRANSLATE_API_KEY
    if not api_key:
        return None

    if not text.strip():
        return text

    lang = target_lang or Config.TRANSLATION_TARGET_LANG or "ru"
    cache_key = (text, lang)
    if cache_key in _cache:
        return _cache[cache_key]

    url = "https://translation.googleapis.com/language/translate/v2"
    params = {"key": api_key}
    payload = {
        "q": text,
        "target": lang,
        "format": "text",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, json=payload) as resp:
                if resp.status != 200:
                    logger.error(
                        "Google Translate API returned status %s: %s",
                        resp.status,
                        await resp.text(),
                    )
                    return None

                data = await resp.json()
                translations = data.get("data", {}).get("translations") or []
                if not translations:
                    logger.error("Google Translate API returned empty translations: %s", data)
                    return None

                translated = translations[0].get("translatedText")
                if not translated:
                    logger.error("Google Translate API response without translatedText: %s", data)
                    return None

                _cache[cache_key] = translated
                return translated
    except Exception as exc:
        logger.error("Error while calling Google Translate API: %s", exc)
        return None

