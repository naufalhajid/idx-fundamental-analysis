from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models.stock import Stock
from db.models.fundamental import Fundamental
from repositories.base import BaseRepository


class StockRepository(BaseRepository[Stock]):
    def __init__(self, session: AsyncSession):
        super().__init__(session=session, model_class=Stock)

    async def get_by_ticker(self, ticker: str) -> Stock | None:
        stmt = (
            select(Stock)
            .options(
                # Load fundamentals and all of their component relationships
                selectinload(Stock.fundamentals).selectinload(Fundamental.stat),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.current_valuation
                ),
                selectinload(Stock.fundamentals).selectinload(Fundamental.per_share),
                selectinload(Stock.fundamentals).selectinload(Fundamental.solvency),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.management_effectiveness
                ),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.profitability
                ),
                selectinload(Stock.fundamentals).selectinload(Fundamental.growth),
                selectinload(Stock.fundamentals).selectinload(Fundamental.dividend),
                selectinload(Stock.fundamentals).selectinload(Fundamental.market_rank),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.income_statement
                ),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.balance_sheet
                ),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.cash_flow_statement
                ),
                selectinload(Stock.fundamentals).selectinload(
                    Fundamental.price_performance
                ),
                # Other Stock relations
                selectinload(Stock.stock_prices),
                selectinload(Stock.sentiments),
                selectinload(Stock.key_analyses),
            )
            .where(Stock.ticker == ticker)
        )
        result = await self.session.scalars(stmt)
        return result.first()
