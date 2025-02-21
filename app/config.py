import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", "22940855"))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "f725fd23eb9e90d3f618c4308fe36bca")
    SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "your_default_secret_key")
    DATABASE_URL: str = "sqlite:///./telegram_summary.db"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "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")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your_default_secret_key")
    SESSION_NAME: str = os.getenv("SESSION_NAME", "your_default_session_name")


settings = Settings()
