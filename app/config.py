import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", "111111"))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "111111111")
    SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "your_default_secret_key")
    DATABASE_URL: str = "sqlite:///./telegram_summary.db"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "11111111")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your_default_secret_key")
    SESSION_NAME: str = os.getenv("SESSION_NAME", "your_default_session_name")


settings = Settings()
