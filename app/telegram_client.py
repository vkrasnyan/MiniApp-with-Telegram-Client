from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import settings


async def get_telegram_client(session_str: str = None) -> TelegramClient:
    """
    Функция для получения клиента Telegram. Если передан session_str, используется существующая сессия,
    если нет - создается новая.
    """
    if session_str:
        return TelegramClient(StringSession(session_str), settings.API_ID, settings.API_HASH)
    else:
        return TelegramClient(StringSession(), settings.API_ID, settings.API_HASH)
