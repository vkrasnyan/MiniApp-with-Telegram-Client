import logging
import openai
from openai import AsyncOpenAI
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError


from app.config import settings

logger = logging.getLogger(__name__)

# Инициализация клиента
client = TelegramClient(settings.SESSION_NAME, settings.API_ID, settings.API_HASH)

clientAI = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

messages_data = []


async def get_all_chats():
    """
    Получить список всех чатов (личные сообщения, группы и каналы).
    """
    try:
        # Подключение к Telegram
        await client.start()

        # # Если требуется двухфакторная аутентификация
        # if not await client.is_user_authorized():
        #     print("Пожалуйста, введите код для входа.")
        #     await client.send_code_request(settings.PHONE_NUMBER)  # Укажите номер телефона в настройках
        #     await client.sign_in(settings.PHONE_NUMBER, input("Введите код: "))

        dialogs = await client.get_dialogs()  # Получение всех чатов

        result = []
        for dialog in dialogs:
            result.append({
                "title": dialog.name or "Без названия",
                "id": dialog.id,
                "type": type(dialog.entity).__name__,  # Тип чата
            })

        return result

    except SessionPasswordNeededError:
        print("Для входа требуется пароль. Введите его ниже.")
        await client.sign_in(password=input("Введите пароль: "))
    except Exception as e:
        logger.error(f"Ошибка при получении чатов: {e}", exc_info=True)

    finally:
        await client.disconnect()


async def process_message_with_openai(message_text: str):
    """Отправка сообщения в OpenAI и обработка ответа."""
    try:
        # Отправка текста в OpenAI
        response = await clientAI.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message_text},
            ]
        )

        # Получение текста из ответа
        openai_response = response.choices[0].message.content.strip()

        # Проверка структуры ответа
        if not response.choices or 'message' not in response.choices[0]:
            logger.warning("Некорректная структура ответа OpenAI.")
            return "Не удалось получить корректный ответ от OpenAI."

        # Проверка на корректность ответа (например, на длину)
        if len(openai_response) < 10:
            openai_response = "Ответ слишком короткий или некорректный."

        return openai_response

    except openai.APIError as e:
        logger.error(f"OpenAI API вернул API Error: {e}")
        return "Произошла ошибка при взаимодействии с OpenAI."

    except openai.RateLimitError as e:
        logger.error(f"OpenAI API Превышен лимит запросов: {e}")
        return "Превышен лимит запросов. Попробуйте позже."
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        return "Не удалось получить ответ от OpenAI."


# Обработчик нового сообщения
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

        # Отправка ответа пользователю в чат
        await event.reply(openai_response)

        # Логируем информацию о сообщении и ответе
        logger.info(f"Обработано сообщение от {sender_name} ({sender_id}) в чате {chat_title} ({chat_type}).")
        logger.info(f"Исходное сообщение: {message_text}")
        logger.info(f"Ответ от OpenAI: {openai_response}")

    await client.start()
    await client.run_until_disconnected()

