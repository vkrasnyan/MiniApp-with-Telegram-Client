import logging

from fastapi import Request
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import settings
from app.telegram_client import get_telegram_client

logger = logging.getLogger(__name__)


# Функция для получения текущего пользователя из сессии
async def get_current_user(request: Request):
    session_str = request.session.get("session_str")
    if not session_str:
        return None
    try:
        logger.debug(f"Session String in FastAPI: {session_str}")
        user_client = await get_telegram_client(session_str)
        await user_client.connect()
        if not await user_client.is_user_authorized():
            logger.warning("User is not authorized.")
            return None
        return user_client
    except Exception as e:
        logger.error(f"Authorization Error: {e}")
        return None


async def get_messages(user_client, entity, limit: int = 10):
    messages = []
    async for message in user_client.iter_messages(entity, limit=limit):
        messages.append({
            "id": message.id,
            "text": message.text,
            "date": message.date.strftime("%Y-%m-%d %H:%M:%S")
        })
    return messages

