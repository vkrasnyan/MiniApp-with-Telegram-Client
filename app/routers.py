import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from telethon import functions, types
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from app.database import get_db
from app.dependencies import get_current_user, summarize_text
from app.models import UserSession
from app.config import settings
from app.telegram_client import get_all_chats, messages_data

logger = logging.getLogger(__name__)

# Инициализация шаблонов
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Общий роутер
router = APIRouter()


# Страница авторизации - ввод номера телефона
@router.get("/authenticate", response_class=HTMLResponse)
async def authenticate_form(request: Request):
    return templates.TemplateResponse("authenticate.html", {"request": request, "message": ""})


# Обработка ввода номера телефона
@router.post("/authenticate", response_class=HTMLResponse)
async def authenticate_submit(request: Request, phone_number: str = Form(...)):
    user_client = TelegramClient(StringSession(), settings.API_ID, settings.API_HASH)
    await user_client.connect()
    try:
        # Отправка запроса на код подтверждения и получение phone_code_hash
        send_code_response = await user_client(functions.auth.SendCodeRequest(
            phone_number=phone_number,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            settings=types.CodeSettings()
        ))

        # Сохранение временной сессии, номера телефона и phone_code_hash в сессии пользователя
        request.session["temp_session"] = user_client.session.save()
        request.session["phone_number"] = phone_number
        request.session["phone_code_hash"] = send_code_response.phone_code_hash

        await user_client.disconnect()
        return RedirectResponse(url="/complete-login", status_code=303)
    except Exception as e:
        await user_client.disconnect()
        logger.error(f"Ошибка при отправке кода подтверждения: {e}")
        return templates.TemplateResponse("authenticate.html", {"request": request, "message": f"Ошибка: {e}"})


# Страница ввода кода подтверждения
@router.get("/complete-login", response_class=HTMLResponse)
async def complete_login_form(request: Request):
    temp_session = request.session.get("temp_session")
    phone_number = request.session.get("phone_number")
    if not temp_session or not phone_number:
        return RedirectResponse(url="/authenticate")
    return templates.TemplateResponse("complete_login.html", {"request": request, "message": ""})


# Обработка ввода кода подтверждения
@router.post("/complete-login", response_class=HTMLResponse)
async def complete_login_submit(request: Request, code: str = Form(...)):
    temp_session = request.session.get("temp_session")
    phone_number = request.session.get("phone_number")
    phone_code_hash = request.session.get("phone_code_hash")

    if not temp_session or not phone_number or not phone_code_hash:
        return RedirectResponse(url="/authenticate")

    user_client = TelegramClient(StringSession(temp_session), settings.API_ID, settings.API_HASH)
    await user_client.connect()
    try:
        # Завершение авторизации с использованием phone_code_hash
        await user_client.sign_in(phone_number, code, phone_code_hash=phone_code_hash)

        session_str = user_client.session.save()

        # Сохранение строки сессии в сессии пользователя
        request.session["session_str"] = session_str

        # Очистка временных данных
        request.session.pop("temp_session", None)
        request.session.pop("phone_number", None)
        request.session.pop("phone_code_hash", None)

        await user_client.disconnect()
        logger.info("Пользователь успешно авторизовался.")
        return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        await user_client.disconnect()
        logger.error(f"Ошибка при завершении авторизации: {e}")
        return templates.TemplateResponse("complete_login.html", {"request": request, "message": f"Ошибка: {e}"})


# Страница панели управления
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    # Получение списка всех каналов
    try:
        dialogs = await user_client.get_dialogs()
        all_channels = [dialog.entity.username for dialog in dialogs if dialog.is_channel and dialog.entity.username]
        logger.info(f"Найдено {len(all_channels)} каналов.")
    except Exception as e:
        all_channels = []
        logger.error(f"Ошибка при получении каналов: {e}")

    # Получение существующих папок (фильтров диалогов)
    try:
        # Обновление кэша диалогов
        await user_client.get_dialogs()

        dialog_filters = await user_client(functions.messages.GetDialogFiltersRequest())
        existing_filters = dialog_filters.filters  # Список фильтров
        logger.info(f"Получено {len(existing_filters)} фильтров диалогов.")
    except Exception as e:
        existing_filters = []
        logger.error(f"Ошибка при получении фильтров диалогов: {e}")

    # Создание списка групп с их каналами
    groups_with_channels = []
    for dialog_filter in existing_filters:
        group_channels = []
        filter_title = getattr(dialog_filter, 'title', f"Фильтр {getattr(dialog_filter, 'id', 'unknown')}")
        include_peers = getattr(dialog_filter, 'include_peers', [])
        logger.info(f"Фильтр: {filter_title}, количество include_peers: {len(include_peers)}")

        # Логирование содержимого include_peers
        for peer in include_peers:
            logger.debug(f"Include Peer: {peer.to_dict()}")

        for included_peer in include_peers:
            try:
                if isinstance(included_peer, types.InputPeerChannel):
                    channel_id = included_peer.channel_id
                    entity = await user_client.get_entity(channel_id)
                    if isinstance(entity, types.Channel):
                        if entity.username:
                            group_channels.append(f"@{entity.username}")
                        else:
                            group_channels.append(f"{entity.title} (ID: {entity.id})")
                elif isinstance(included_peer, types.InputPeerUser):
                    user_id = included_peer.user_id
                    entity = await user_client.get_entity(user_id)
                    if isinstance(entity, types.User):
                        name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                        group_channels.append(f"{name} (ID: {entity.id})")
                elif isinstance(included_peer, types.InputPeerChat):
                    chat_id = included_peer.chat_id
                    entity = await user_client.get_entity(chat_id)
                    if isinstance(entity, types.Chat):
                        group_channels.append(f"{entity.title} (ID: {entity.id})")
                else:
                    logger.info(f"Неизвестный тип peer: {included_peer}")
            except Exception as e:
                logger.error(f"Ошибка при обработке peer {included_peer}: {e}")
                continue

        groups_with_channels.append({
            "filter_name": filter_title,
            "channels": group_channels
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "channels": all_channels,
        "groups": groups_with_channels,
        "filters": existing_filters,
        "message": ""
    })


# Страница отображения сообщений из канала
@router.get("/last-messages/{channel_link}", response_class=HTMLResponse)
async def last_messages(request: Request, channel_link: str):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")
    try:
        entity = await user_client.get_entity(channel_link)
        messages = []
        async for message in user_client.iter_messages(entity, limit=10):
            messages.append({
                "id": message.id,
                "text": message.text,
                "date": message.date.strftime("%Y-%m-%d %H:%M:%S")
            })
        return templates.TemplateResponse("messages.html",
                                          {"request": request, "channel": channel_link, "messages": messages})
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений из канала {channel_link}: {e}")
        # Попытка повторно получить данные для отображения панели управления с сообщением об ошибке
        try:
            dialogs = await user_client.get_dialogs()
            all_channels = [dialog.entity.username for dialog in dialogs if
                            dialog.is_channel and dialog.entity.username]
        except Exception as e:
            logger.error(f"Ошибка при повторном получении каналов: {e}")
            all_channels = []

        try:
            dialog_filters = await user_client(functions.messages.GetDialogFiltersRequest())
            existing_filters = dialog_filters.filters
        except Exception as e:
            logger.error(f"Ошибка при повторном получении фильтров диалогов: {e}")
            existing_filters = []

        groups_with_channels = []
        for filter in existing_filters:
            group_channels = []
            # Получение названия фильтра, если есть, иначе задаём дефолтное
            filter_title = getattr(filter, 'title', f"Фильтр {getattr(filter, 'id', 'unknown')}")

            # Получение включённых диалогов, если есть
            includes = getattr(filter, 'includes', [])

            # Обработка каждого включённого диалога
            for included in includes:
                try:
                    # Получаем peer из DialogFilterIncluded
                    peer = included.peer
                    # Проверяем тип peer
                    if isinstance(peer, types.PeerChannel):
                        channel_id = peer.channel_id
                        # Получаем сущность канала по ID
                        entity = await user_client.get_entity(channel_id)
                        if isinstance(entity, types.Channel):
                            logger.info(f"Найден канал: @{entity.username} (ID: {entity.id})")
                            if entity.username:
                                group_channels.append(entity.username)
                            else:
                                group_channels.append(f"{entity.title} (ID: {entity.id})")
                except Exception as e:
                    logger.error(f"Ошибка при получении сущности по Peer {peer}: {e}")
                    continue

            groups_with_channels.append({
                "filter_name": filter_title,
                "channels": group_channels
            })

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "channels": all_channels,
            "groups": groups_with_channels,
            "filters": existing_filters,
            "message": f"Ошибка: {e}"
        })


# Страница формы суммаризации
@router.get("/summarize", response_class=HTMLResponse)
async def summarize_form(request: Request):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    try:
        dialog_filters = await user_client(functions.messages.GetDialogFiltersRequest())
        existing_filters = dialog_filters.filters
    except Exception as e:
        existing_filters = []
        logger.error(f"Ошибка при получении фильтров диалогов: {e}")

    # Use getattr to safely access 'title', provide a default if missing
    filter_names = [
        getattr(dialog_filter, 'title', f"Фильтр {getattr(dialog_filter, 'id', 'unknown')}")
        for dialog_filter in existing_filters
    ]

    return templates.TemplateResponse("summarize_form.html", {
        "request": request,
        "filters": filter_names,
        "message": ""
    })


@router.post("/summarize", response_class=HTMLResponse)
async def summarize_submit(
        request: Request,
        filter_name: str = Form(...),
        summary_type: str = Form(...),
        period_start: Optional[str] = Form(None),
        period_end: Optional[str] = Form(None)
):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    # Поиск фильтра по названию
    try:
        dialog_filters = await user_client(functions.messages.GetDialogFiltersRequest())
        existing_filters = dialog_filters.filters

        # Найти фильтр по названию
        selected_filter = next((f for f in existing_filters if getattr(f, 'title', None) == filter_name), None)

        if not selected_filter:
            raise ValueError("Фильтр не найден.")
    except Exception as e:
        logger.error(f"Ошибка при поиске фильтра: {e}")
        return templates.TemplateResponse(
            "summarize_form.html",
            {"request": request, "filters": [], "message": f"Ошибка: {e}"}
        )

    # Получение пиров из выбранного фильтра
    include_peers = getattr(selected_filter, 'include_peers', [])
    if not include_peers:
        return templates.TemplateResponse(
            "summarize_form.html",
            {"request": request, "filters": [], "message": "Выбранный фильтр не содержит каналов."}
        )

    messages_to_summarize = []

    for peer in include_peers:
        try:
            entity = None
            channel_link = None

            if isinstance(peer, types.InputPeerChannel):
                entity = await user_client.get_entity(peer)
                if entity.username:
                    channel_link = f"@{entity.username}"
                else:
                    channel_link = f"ID {entity.id}"
            elif isinstance(peer, types.InputPeerChat):
                entity = await user_client.get_entity(peer)
                channel_link = f"chat_id={entity.id}"
            else:
                logger.warning(f"Неизвестный тип пира: {peer}")
                continue

            # Проверяем, что entity и channel_link установлены
            if entity and channel_link:
                logger.info(f"Получение сообщений из канала {channel_link}")
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
            else:
                logger.error(f"Не удалось получить сущность для канала {channel_link}")

        except Exception as e:
            logger.error(f"Ошибка при получении сообщений из канала {channel_link}: {e}")
            continue

    # Объединение сообщений для суммаризации
    combined_messages = "\n\n".join(messages_to_summarize)

    if not combined_messages:
        return templates.TemplateResponse(
            "summarize_form.html",
            {"request": request, "filters": [], "message": "Нет сообщений для суммаризации."}
        )

    # Разделение на части, если текст слишком длинный
    MAX_CHARS = 3000  # Примерное ограничение, зависит от модели и токенов
    parts = [combined_messages[i:i + MAX_CHARS] for i in range(0, len(combined_messages), MAX_CHARS)]

    summaries = []
    for part in parts:
        summary = summarize_text(part)
        summaries.append(summary)

    final_summary = "\n\n".join(summaries)

    return templates.TemplateResponse(
        "summary_result.html",
        {"request": request, "summary": final_summary}
    )


@router.get("/chats", response_class=HTMLResponse)
async def show_chats(request: Request):
    dialogs = await get_all_chats()  # Получение списка чатов
    return templates.TemplateResponse("dialogs.html", {"request": request, "dialogs": dialogs})

@router.get("/messages")
async def get_messages(request: Request):
    """Отображение собранных сообщений."""
    return templates.TemplateResponse(
        "sender_info.html", {"request": request, "messages": messages_data}
    )


# Выход из системы
@router.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.clear()
    logger.info("Пользователь вышел из системы.")
    return RedirectResponse(url="/", status_code=303)
