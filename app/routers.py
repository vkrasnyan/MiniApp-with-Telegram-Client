import json
import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from telethon import functions, types
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import unquote

from telethon.tl.types import PeerUser, PeerChannel

from app.dependencies import get_current_user
from app.client_ai import summarize_text
from app.config import settings


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


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, sort_by: str = "participants"):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    # Получение списка всех диалогов (каналы, группы, личные чаты)
    try:
        dialogs = await user_client.get_dialogs()
        all_channels = []
        all_groups = []
        all_private_chats = []

        for dialog in dialogs:
            entity = dialog.entity

            # Каналы
            if dialog.is_channel and entity.username:
                all_channels.append({
                    "id": entity.id,
                    "name": f"@{entity.username}",
                    "participants_count": getattr(entity, "participants_count", 0),
                    "unread_count": dialog.unread_count
                })

            # Группы (супергруппы и обычные группы)
            elif dialog.is_group:
                group_name = getattr(entity, 'title', f"Группа {entity.id}")
                all_groups.append({
                    "id": entity.id,
                    "name": group_name,
                    "participants_count": getattr(entity, "participants_count", 0),
                    "unread_count": dialog.unread_count
                })

            # Личные чаты
            elif dialog.is_user:
                user_name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                all_private_chats.append({
                    "id": entity.id,
                    "name": user_name,
                    "participants_count": 1,
                    "unread_count": dialog.unread_count
                })

        logger.info(
            f"Найдено {len(all_channels)} каналов, {len(all_groups)} групп и {len(all_private_chats)} личных чатов.")

    except Exception as e:
        all_channels = []
        all_groups = []
        all_private_chats = []
        logger.error(f"Ошибка при получении диалогов: {e}")

    # Сортировка
    if sort_by == "participants":
        all_channels.sort(key=lambda x: x["participants_count"], reverse=True)
        all_groups.sort(key=lambda x: x["participants_count"], reverse=True)
        all_private_chats.sort(key=lambda x: x["participants_count"], reverse=True)
    elif sort_by == "unread":
        all_channels.sort(key=lambda x: x["unread_count"], reverse=True)
        all_groups.sort(key=lambda x: x["unread_count"], reverse=True)
        all_private_chats.sort(key=lambda x: x["unread_count"], reverse=True)

    # Получение существующих папок (фильтров диалогов)
    groups_with_channels = []
    try:
        dialog_filters = await user_client(functions.messages.GetDialogFiltersRequest())
        existing_filters = dialog_filters.filters if dialog_filters.filters else []
        logger.info(f"Получено {len(existing_filters)} фильтров диалогов.")

        # Создание списка групп с их каналами
        for dialog_filter in existing_filters:
            group_channels = []
            filter_title = getattr(dialog_filter, 'title', f"Фильтр {getattr(dialog_filter, 'id', 'unknown')}")
            include_peers = getattr(dialog_filter, 'include_peers', [])

            logger.info(f"Фильтр: {filter_title}, количество include_peers: {len(include_peers)}")

            for included_peer in include_peers:
                try:
                    entity = None

                    if isinstance(included_peer, types.InputPeerChannel):
                        entity = await user_client.get_input_entity(included_peer)
                    elif isinstance(included_peer, types.InputPeerUser):
                        entity = await user_client.get_input_entity(included_peer)
                    elif isinstance(included_peer, types.InputPeerChat):
                        entity = await user_client.get_input_entity(included_peer)
                    else:
                        logger.warning(f"Неизвестный тип peer: {included_peer}")
                        continue

                    if isinstance(entity, types.Channel):
                        group_channels.append(
                            f"@{entity.username}" if entity.username else f"{entity.title} (ID: {entity.id})")
                    elif isinstance(entity, types.User):
                        name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                        group_channels.append(f"{name} (ID: {entity.id})")
                    elif isinstance(entity, types.Chat):
                        group_channels.append(f"{entity.title} (ID: {entity.id})")
                    else:
                        logger.warning(f"Неизвестный тип сущности: {type(entity)}")

                except ValueError:
                    logger.error(f"Ошибка: не найден entity для {included_peer}. Возможно, отсутствует access_hash.")
                except Exception as e:
                    logger.error(f"Ошибка при обработке peer {included_peer}: {e}")
                    continue

            groups_with_channels.append({
                "filter_name": filter_title,
                "channels": group_channels
            })

            request.session["channels"] = all_channels
            request.session["groups"] = all_groups
            request.session["private_chats"] = all_private_chats

    except Exception as e:
        logger.error(f"Ошибка при получении фильтров диалогов: {e}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "channels": all_channels,
        "groups": all_groups,
        "private_chats": all_private_chats,
        "groups_with_channels": groups_with_channels,
        "filters": existing_filters,
        "sort_by": sort_by,
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



@router.get("/last-messages/group/{group_id}", response_class=HTMLResponse)
async def last_group_messages(request: Request, group_id: int):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    try:
        entity = await user_client.get_entity(group_id)
        messages = []
        async for message in user_client.iter_messages(entity, limit=10):
            messages.append({
                "id": message.id,
                "text": message.text,
                "date": message.date.strftime("%Y-%m-%d %H:%M:%S")
            })

        return templates.TemplateResponse("messages.html", {
            "request": request,
            "chat_name": entity.title,
            "messages": messages
        })
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений из группы {group_id}: {e}")
        return RedirectResponse(url="/dashboard")


@router.get("/last-messages/chat/{chat_id}", response_class=HTMLResponse)
async def last_chat_messages(request: Request, chat_id: int):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    try:
        entity = await user_client.get_entity(chat_id)
        messages = []
        async for message in user_client.iter_messages(entity, limit=10):
            messages.append({
                "id": message.id,
                "text": message.text,
                "date": message.date.strftime("%Y-%m-%d %H:%M:%S")
            })

        return templates.TemplateResponse("messages.html", {
            "request": request,
            "chat_name": f"{entity.first_name or ''} {entity.last_name or ''}".strip(),
            "messages": messages
        })
    except Exception as e:
        logger.error(f"Ошибка при получении сообщений из чата {chat_id}: {e}")
        return RedirectResponse(url="/dashboard")


@router.get("/summarize", response_class=HTMLResponse)
async def summarize_form(request: Request, channels: str = "", groups: str = "", private_chats: str = ""):
    try:
        channels = json.loads(unquote(channels)) if channels else []
        groups = json.loads(unquote(groups)) if groups else []
        private_chats = json.loads(unquote(private_chats)) if private_chats else []
    except json.JSONDecodeError:
        channels, groups, private_chats = [], [], []

    return templates.TemplateResponse("summarize_form.html", {
        "request": request,
        "channels": channels,
        "groups": groups,
        "private_chats": private_chats,
        "message": ""
    })


@router.post("/summarize", response_class=HTMLResponse)
async def summarize_submit(
        request: Request,
        source: str = Form(...),
        summary_type: str = Form(...),
        period_start: Optional[str] = Form(None),
        period_end: Optional[str] = Form(None)
):
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    messages_to_summarize = []

    try:
        # Конвертируем ID в число
        source_id = int(source)

        # Проверяем, является ли source пользователем, каналом или чатом
        if isinstance(source_id, int):
            if source_id < 0:
                # Это, вероятно, пользователь
                entity = await user_client.get_entity(PeerUser(source_id))
            elif source_id > 0:
                # Это канал, группа или чат
                entity = await user_client.get_entity(PeerChannel(source_id))
            else:
                raise ValueError("Некорректный ID источника")

        logger.info(f"Получение сообщений из {entity.title if hasattr(entity, 'title') else 'неизвестного источника'}")

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
        return templates.TemplateResponse(
            "summarize_form.html",
            {"request": request, "message": f"Ошибка: {e}"}
        )

    # Объединяем текст для суммаризации
    combined_messages = "\n\n".join(messages_to_summarize)

    if not combined_messages:
        return templates.TemplateResponse(
            "summarize_form.html",
            {"request": request, "message": "Нет сообщений для суммаризации."}
        )

    # Разбиваем на части, если текст слишком длинный
    MAX_CHARS = 3000
    parts = [combined_messages[i:i + MAX_CHARS] for i in range(0, len(combined_messages), MAX_CHARS)]

    summaries = [await summarize_text(part) for part in parts]  # Суммаризируем по частям

    final_summary = "\n\n".join(summaries)

    return templates.TemplateResponse(
        "summary_result.html",
        {"request": request, "summary": final_summary}
    )


# Выход из системы
@router.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.clear()
    logger.info("Пользователь вышел из системы.")
    return RedirectResponse(url="/", status_code=303)
