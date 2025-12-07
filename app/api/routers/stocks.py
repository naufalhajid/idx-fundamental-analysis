from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependency_injections.db import get_db
from repositories.stock_repository import StockRepository
from schemas.stock import Stock as StockSchema

router = APIRouter(tags=["stocks"], prefix="/stocks")


@router.get("/{ticker}", response_model=StockSchema)
async def get_stock_by_ticker(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    repository = StockRepository(db)
    stock = await repository.get_by_ticker(ticker)
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")

    return StockSchema(
        ticker=stock.ticker,
        name=stock.name,
        ipo_date=stock.ipo_date,
        note=stock.note,
        market_cap=stock.market_cap,
        home_page=stock.home_page,
        fundamental=None,
        key_analysis=None,
        sentiment=None,
        stock_price=None,
    )
