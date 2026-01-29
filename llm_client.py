"""
Клиент для генерации тостов через OpenAI API.
"""

import logging
from typing import Optional

from openai import AsyncOpenAI

from config import Config

logger = logging.getLogger(__name__)

# Системный промпт для генерации токсичных тостов
TOXIC_TOAST_SYSTEM_PROMPT = """Ты — язвительный, циничный автор тостов.
Твой стиль — сарказм, лёгкая токсичность, экзистенциальный юмор.

Правила (обязательные):
- допускается сарказм, цинизм, пассивная агрессия
- НЕ оскорбляй людей или группы людей
- НЕ используй ненависть, угрозы или призывы к вреду
- НЕ упоминай зависимость или чрезмерное употребление
- не объясняй шутку
- не упоминай, что ты ИИ
- не морализируй
- без объяснений и дисклеймеров

Тон:
«Жизнь странная, всё идёт не по плану, но мы всё ещё здесь».

Формат ответа:
- строго 2–3 предложения
- можно использовать 0–1 emoji в конце
- никаких заголовков, списков или пояснений
- только сам тост"""


class LLMClient:
    """Клиент для работы с OpenAI API."""

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        """Ленивая инициализация клиента."""
        if self._client is None:
            if not Config.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY не установлен!")
            self._client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        return self._client

    async def generate_toxic_toast(self, reason: str) -> Optional[str]:
        """
        Генерирует токсичный тост для указанного повода.

        Args:
            reason: Повод для тоста (например, "работа", "пятница")

        Returns:
            Сгенерированный тост или None в случае ошибки
        """
        try:
            client = self._get_client()

            user_prompt = f"Сгенерировать короткий токсичный тост (2–3 предложения) для повода: «{reason}»"

            response = await client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": TOXIC_TOAST_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=200,
                temperature=0.9,
            )

            toast = response.choices[0].message.content
            if toast:
                return toast.strip()
            return None

        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error generating toast: {e}")
            return None


# Глобальный экземпляр клиента
llm_client = LLMClient()
