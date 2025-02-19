import logging

from fastapi import Request
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import settings
from app.telegram_client import clientAI

logger = logging.getLogger(__name__)


# Функция для получения текущего пользователя из сессии
async def get_current_user(request: Request):
    session_str = request.session.get("session_str")
    if not session_str:
        return None
    try:
        logger.debug(f"Session String in FastAPI: {session_str}")
        user_client = TelegramClient(StringSession(session_str), settings.API_ID, settings.API_HASH)
        await user_client.connect()
        if not await user_client.is_user_authorized():
            logger.warning("User is not authorized.")
            return None
        return user_client
    except Exception as e:
        logger.error(f"Authorization Error: {e}")
        return None


async def get_messages_from_chat(client: TelegramClient, chat_id: int):
    """Загрузка сообщений из чата (включая 100 предыдущих)"""
    chat = await client.get_entity(chat_id)
    messages = []
    async for message in client.iter_messages(chat, limit=10):
        messages.append(message.text)
    return messages



# Функция для суммаризации текста с учётом ограничений токенов
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
