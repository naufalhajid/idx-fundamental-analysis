from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependency_injections.db import get_db
from repositories.stock_price_repository import StockPriceRepository
from schemas.stock_price import StockPrice as StockPriceSchema


router = APIRouter(tags=["stock_prices"], prefix="/stock-prices")


@router.get("/{ticker}", response_model=list[StockPriceSchema])
async def list_stock_prices_by_ticker(
    ticker: str, db: AsyncSession = Depends(get_db)
) -> list[StockPriceSchema]:
    repository = StockPriceRepository(db)
    prices = await repository.list_by_stock_ticker(ticker)

    return [StockPriceSchema.from_orm(price) for price in prices]
