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
