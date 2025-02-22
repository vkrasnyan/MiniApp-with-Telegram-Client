import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    API_ID: int
    API_HASH: str
    SESSION_SECRET_KEY: str
    DATABASE_URL: str = "sqlite:///./telegram_summary.db"
    OPENAI_API_KEY: str
    SECRET_KEY: str
    SESSION_NAME: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
