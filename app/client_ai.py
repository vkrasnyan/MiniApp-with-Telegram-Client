import logging

import openai

from app.config import settings

logger = logging.getLogger(__name__)

clientAI = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def summarize_text(text: str) -> str:
    try:
        response = await clientAI.chat.completions.create(
            model="gpt-3.5-turbo",  # Используйте нужную модель
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes Telegram channel messages."},
                {"role": "user", "content": f"Суммаризируй следующие сообщения:\n\n{text}"}
            ],
            max_tokens=2000,  # Ограничение на выходные токены
            temperature=0.7,
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        logger.error(f"Ошибка при суммаризации: {e}")
        return "Не удалось получить суммаризацию."

