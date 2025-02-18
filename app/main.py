import logging
import os
import uvicorn
import asyncio
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.requests import Request


from app.config import settings
from app.database import Base, engine
from app.routers import router
from app.dependencies import get_current_user
from app.telegram_client import start_client

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание таблиц в БД
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Настройка шаблонов
template_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=template_dir)

# Настройка middleware для сессий
app.add_middleware(SessionMiddleware, secret_key=os.getenv(settings.SECRET_KEY, "your_default_secret_key"))


# Подключение роутов
app.include_router(router)
static_dir = os.path.join(os.path.dirname(__file__), 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def startup_event():
    """Запуск фоновой задачи Telethon-клиента."""
    asyncio.create_task(start_client())


# Главная страница
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_client = await get_current_user(request)
    if user_client:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("index.html", {"request": request})



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
