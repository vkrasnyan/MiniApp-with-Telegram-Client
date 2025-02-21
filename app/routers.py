import json
import os
import logging
from typing import Optional
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from telethon import functions, types
from urllib.parse import unquote

from app.services.dashboard import get_dialogs_info, sort_dialogs, get_dialog_filters
from app.services.dependencies import get_current_user, get_messages
from app.config import settings
from app.services.summarize import get_entity_by_source, summarize_messages, get_messages_to_summarize
from app.telegram_client import get_telegram_client


logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
router = APIRouter()


@router.get("/authenticate", response_class=HTMLResponse)
async def authenticate_form(request: Request):
    """Отображение страницы авторизации пользователя и ввода номера телефона"""
    return templates.TemplateResponse("authenticate.html", {"request": request, "message": ""})


@router.post("/authenticate", response_class=HTMLResponse)
async def authenticate_submit(request: Request, phone_number: str = Form(...)):
    """Роутер для обработки ввода номера телефона"""
    user_client = await get_telegram_client()
    await user_client.connect()
    try:
        send_code_response = await user_client(functions.auth.SendCodeRequest(
            phone_number=phone_number,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            settings=types.CodeSettings()
        ))

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

    user_client = get_telegram_client(session_str=temp_session)
    await user_client.connect()
    try:
        await user_client.sign_in(phone_number, code, phone_code_hash=phone_code_hash)

        session_str = user_client.session.save()

        request.session["session_str"] = session_str

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
    """Роутер для отображения панели управления"""
    user_client = await get_current_user(request)
    if not user_client:
        return RedirectResponse(url="/authenticate")

    all_channels, all_groups, all_private_chats = await get_dialogs_info(user_client)

    sort_dialogs(all_channels, all_groups, all_private_chats, sort_by)

    groups_with_channels, existing_filters = await get_dialog_filters(user_client)

    request.session["channels"] = all_channels
    request.session["groups"] = all_groups
    request.session["private_chats"] = all_private_chats

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
        messages = await get_messages(user_client, entity)
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
        messages = await get_messages(user_client, entity)

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
        messages = await get_messages(user_client, entity)

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

    try:
        source_id = int(source)
        entity = await get_entity_by_source(user_client, source_id)

        if not entity:
            return templates.TemplateResponse(
                "summarize_form.html", {"request": request, "message": "Ошибка: не удалось найти источник."}
            )

        logger.info(f"Получение сообщений из {entity.title if hasattr(entity, 'title') else 'неизвестного источника'}")

        messages_to_summarize = await get_messages_to_summarize(user_client, entity, summary_type, period_start, period_end)

    except Exception as e:
        logger.error(f"Ошибка при получении сообщений: {e}")
        return templates.TemplateResponse(
            "summarize_form.html", {"request": request, "message": f"Ошибка: {e}"}
        )

    final_summary = await summarize_messages(messages_to_summarize)

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
