import logging
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from app.config import settings

logger = logging.getLogger(__name__)

# Инициализация клиента
client = TelegramClient(settings.SESSION_NAME, settings.API_ID, settings.API_HASH)


async def start_client():
    """Запускаем Telethon-клиент, который отправляет сообщение в OpenAI и получает ответ"""
    @client.on(events.NewMessage)
    async def handle_new_message(event):
        chat_type = "Личный"
        if event.is_group:
            chat_type = "Группа"
        elif event.is_channel:
            chat_type = "Канал"

        sender = await event.get_sender()
        sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or "Неизвестный"
        sender_id = sender.id

        chat = await event.get_chat()
        chat_title = chat.title or "Личное сообщение"

        # Текст сообщения
        message_text = event.message.message

        # Отправляем сообщение в OpenAI для обработки
        openai_response = await process_message_with_openai(message_text)

        # Сохраняем данные в список для отображения
        messages_data.append({
            "chat_type": chat_type,
            "chat_title": chat_title,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "message_text": message_text,
            "openai_response": openai_response
        })

        # # Отправка ответа пользователю в чат
        # await event.reply(openai_response)
        #
        # # Логируем информацию о сообщении и ответе
        # logger.info(f"Обработано сообщение от {sender_name} ({sender_id}) в чате {chat_title} ({chat_type}).")
        # logger.info(f"Исходное сообщение: {message_text}")
        # logger.info(f"Ответ от OpenAI: {openai_response}")

    await client.start()
    await client.run_until_disconnected()

