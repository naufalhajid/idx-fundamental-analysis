from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependency_injections.db import get_db
from repositories.sentiment_repository import SentimentRepository
from schemas.sentiment import Sentiment as SentimentSchema


router = APIRouter(tags=["sentiments"], prefix="/sentiments")


@router.get("/{ticker}", response_model=list[SentimentSchema])
async def list_sentiments_by_ticker(
    ticker: str, db: AsyncSession = Depends(get_db)
) -> list[SentimentSchema]:
    repository = SentimentRepository(db)
    sentiments = await repository.list_by_stock_ticker(ticker)

    return [SentimentSchema.from_orm(sentiment) for sentiment in sentiments]
