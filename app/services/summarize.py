import logging
from datetime import datetime
from telethon.tl.types import PeerUser, PeerChannel

from app.client_ai import summarize_text

logger = logging.getLogger(__name__)


async def get_entity_by_source(user_client, source_id):
    try:
        if source_id < 0:
            # Это пользователь
            return await user_client.get_entity(PeerUser(source_id))
        elif source_id > 0:
            # Это канал, группа или чат
            return await user_client.get_entity(PeerChannel(source_id))
        else:
            raise ValueError("Некорректный ID источника")
    except Exception as e:
        logger.error(f"Ошибка при получении сущности для {source_id}: {e}")
        return None


async def get_messages_to_summarize(user_client, entity, summary_type, period_start, period_end):
    messages_to_summarize = []
    try:
        if summary_type == "last_10":
            async for message in user_client.iter_messages(entity, limit=10):
                if message.text:
                    messages_to_summarize.append(message.text)

        elif summary_type == "period" and period_start and period_end:
            start_date = datetime.strptime(period_start, "%Y-%m-%d")
            end_date = datetime.strptime(period_end, "%Y-%m-%d")
            async for message in user_client.iter_messages(entity, offset_date=end_date, reverse=True):
                if message.date < start_date:
                    break
                if message.text:
                    messages_to_summarize.append(message.text)

    except Exception as e:
        logger.error(f"Ошибка при получении сообщений: {e}")
    return messages_to_summarize


def split_text_for_summary(text: str, max_chars: int = 3000):
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


async def summarize_messages(messages_to_summarize):
    combined_messages = "\n\n".join(messages_to_summarize)

    if not combined_messages:
        return "Нет сообщений для суммаризации."

    parts = split_text_for_summary(combined_messages)
    summaries = [await summarize_text(part) for part in parts]

    return "\n\n".join(summaries)
