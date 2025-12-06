from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session
