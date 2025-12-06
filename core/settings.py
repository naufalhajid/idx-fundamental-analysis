from functools import lru_cache
from typing import Any, Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_PATH = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=f"{BASE_PATH}/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # .env
    ENVIRONMENT: Literal["dev", "prod"] = "dev"

    # FastAPI
    FASTAPI_APP_VERSION: str = "0.0.1"
    FASTAPI_API_V1_PATH: str = "/api/v1"
    FASTAPI_TITLE: str = "IDX-Fundamental API"
    FASTAPI_DESCRIPTION: str = "IDX-Fundamental API and endpoints"
    FASTAPI_DOCS_URL: str = "/docs"
    FASTAPI_REDOC_URL: str = "/redoc"
    FASTAPI_OPENAPI_URL: str | None = "/openapi"
    FASTAPI_STATIC_FILES: bool = True

    # .env
    DATABASE_TYPE: Literal["sqlite", "postgresql"] = "sqlite"
    DATABASE_HOST: Optional[str] = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "db_user"
    DATABASE_PASSWORD: str = "db_password"
    DATABASE_ECHO: bool | Literal["debug"] = False
    DATABASE_POOL_ECHO: bool | Literal["debug"] = False
    DATABASE_SETUP_DROP_TABLE: bool = False

    # CORS
    MIDDLEWARE_CORS: bool = True
    CORS_ALLOWED_ORIGINS: list[str] = [
        "http://127.0.0.1:8000",
        "http://localhost:5173",
    ]
    CORS_EXPOSE_HEADERS: list[str] = [
        "X-Request-ID",
    ]

    DATETIME_TIMEZONE: str = "Asia/Jakarta"
    DATETIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</> | <level>{level: <8}</> | <cyan>{file}</>:<cyan>{line}</> <cyan>{function}</> | <level>{message}</>"
    LOG_FILE_ACCESS_LEVEL: str = "INFO"
    LOG_FILE_ERROR_LEVEL: str = "ERROR"
    LOG_ACCESS_FILENAME: str = "logs/success.log"
    LOG_ERROR_FILENAME: str = "logs/error.log"
    LOG_APP_FILENAME: str = "logs/app.log"

    GOOGLE_SERVICE_ACCOUNT: str = "{}"
    GOOGLE_DRIVE_EMAILS: str = '["example@gmail.com"]'

    @model_validator(mode="before")
    @classmethod
    def check_env(cls, values: Any) -> Any:
        if values.get("ENVIRONMENT") == "prod":
            values["FASTAPI_OPENAPI_URL"] = None
            values["FASTAPI_STATIC_FILES"] = False

        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
