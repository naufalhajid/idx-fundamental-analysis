from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from db import database
from core.settings import settings
from app.api.routers import api_router


@asynccontextmanager
async def register_init(app: FastAPI) -> AsyncGenerator[None, None]:
    """

    :param app: FastAPI
    :return:
    """
    database.setup_db(is_drop_table=settings.DATABASE_SETUP_DROP_TABLE)

    yield


def register_app() -> FastAPI:
    class MyFastAPI(FastAPI):
        if settings.MIDDLEWARE_CORS:

            def build_middleware_stack(self) -> ASGIApp:
                return CORSMiddleware(
                    super().build_middleware_stack(),
                    allow_origins=settings.CORS_ALLOWED_ORIGINS,
                    allow_credentials=True,
                    allow_methods=["*"],
                    allow_headers=["*"],
                    expose_headers=settings.CORS_EXPOSE_HEADERS,
                )

    app = MyFastAPI(
        title=settings.FASTAPI_TITLE,
        version=settings.FASTAPI_APP_VERSION,
        description=settings.FASTAPI_DESCRIPTION,
        docs_url=settings.FASTAPI_DOCS_URL,
        redoc_url=settings.FASTAPI_REDOC_URL,
        openapi_url=settings.FASTAPI_OPENAPI_URL,
        lifespan=register_init,
    )

    app.include_router(api_router, prefix=settings.FASTAPI_API_V1_PATH)

    return app
