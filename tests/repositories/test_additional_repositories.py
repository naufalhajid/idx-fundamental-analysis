import asyncio
from datetime import datetime
from uuid import uuid4

import pytest

from db import database
from db.models.fundamental import (
    Fundamental as FundamentalModel,
    CurrentValuation,
    PerShare,
    Solvency,
    ManagementEffectiveness,
    Profitability,
    Growth,
    Dividend,
    MarketRank,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    PricePerformance,
    Stat,
)
from db.models.key_analysis import KeyAnalysis as KeyAnalysisModel
from db.models.stock_price import StockPrice as StockPriceModel
from db.models.sentiment import Sentiment as SentimentModel
from db.session import get_async_session
from repositories.fundamental_repository import FundamentalRepository
from repositories.key_analysis_repository import KeyAnalysisRepository
from repositories.stock_price_repository import StockPriceRepository
from repositories.sentiment_repository import SentimentRepository


@pytest.fixture(scope="module", autouse=True)
def setup_database() -> None:
    database.setup_db(is_drop_table=False)


def test_fundamental_repository_get_by_stock_ticker() -> None:
    async def _test() -> None:
        ticker = f"FUND_REPO_{uuid4().hex[:8]}"

        async with get_async_session() as session:
            stat = Stat(
                current_share_outstanding=1.0,
                market_cap=2.0,
                enterprise_value=3.0,
            )
            current_valuation = CurrentValuation()
            per_share = PerShare()
            solvency = Solvency()
            management_effectiveness = ManagementEffectiveness()
            profitability = Profitability()
            growth = Growth()
            dividend = Dividend()
            market_rank = MarketRank()
            income_statement = IncomeStatement()
            balance_sheet = BalanceSheet()
            cash_flow_statement = CashFlowStatement()
            price_performance = PricePerformance()

            fundamental = FundamentalModel(
                stat=stat,
                current_valuation=current_valuation,
                per_share=per_share,
                solvency=solvency,
                management_effectiveness=management_effectiveness,
                profitability=profitability,
                growth=growth,
                dividend=dividend,
                market_rank=market_rank,
                income_statement=income_statement,
                balance_sheet=balance_sheet,
                cash_flow_statement=cash_flow_statement,
                price_performance=price_performance,
                stock_ticker=ticker,
            )

            session.add(fundamental)

        async with get_async_session() as session:
            repository = FundamentalRepository(session)
            stored = await repository.get_by_stock_ticker(ticker)

            assert stored is not None
            assert stored.stock_ticker == ticker

    asyncio.run(_test())


def test_key_analysis_repository_get_by_stock_ticker() -> None:
    async def _test() -> None:
        ticker = f"KEY_REPO_{uuid4().hex[:8]}"

        async with get_async_session() as session:
            key = KeyAnalysisModel(
                normal_price=10.0,
                price_to_equity_discount=5.0,
                relative_pe_ratio_ttm=1.5,
                eps_growth=0.1,
                debt_to_total_assets_ratio=0.2,
                liquidity_differential=1.1,
                cce=0.3,
                operating_efficiency=0.4,
                dividend_payout_efficiency=0.5,
                yearly_price_change=0.6,
                composite_rank=0.7,
                net_debt_to_equity_ratio=0.8,
                stock_ticker=ticker,
            )
            session.add(key)

        async with get_async_session() as session:
            repository = KeyAnalysisRepository(session)
            stored = await repository.get_by_stock_ticker(ticker)

            assert stored is not None
            assert stored.stock_ticker == ticker
            assert stored.normal_price == 10.0

    asyncio.run(_test())


def test_stock_price_repository_list_by_stock_ticker() -> None:
    async def _test() -> None:
        ticker = f"PRICE_REPO_{uuid4().hex[:8]}"

        async with get_async_session() as session:
            first = StockPriceModel(
                stock_ticker=ticker,
                price=100.0,
                change=1.0,
                percentage_change=1.0,
                average=100.0,
                close=100.0,
                high=101.0,
                low=99.0,
                open=100.0,
                ara=0.0,
                arb=0.0,
                frequency=1.0,
                fsell=0.0,
                fbuy=0.0,
            )
            second = StockPriceModel(
                stock_ticker=ticker,
                price=101.0,
                change=1.0,
                percentage_change=1.0,
                average=100.5,
                close=101.0,
                high=102.0,
                low=100.0,
                open=100.5,
                ara=0.0,
                arb=0.0,
                frequency=2.0,
                fsell=0.0,
                fbuy=0.0,
            )
            session.add_all([first, second])

        async with get_async_session() as session:
            repository = StockPriceRepository(session)
            prices = await repository.list_by_stock_ticker(ticker)

            assert len(prices) >= 2
            assert all(p.stock_ticker == ticker for p in prices)

    asyncio.run(_test())


def test_sentiment_repository_list_by_stock_ticker() -> None:
    async def _test() -> None:
        ticker = f"SENT_REPO_{uuid4().hex[:8]}"

        async with get_async_session() as session:
            first = SentimentModel(
                content="good",
                rate=1.0,
                category="positive",
                posted_at=datetime.utcnow(),
                stock_ticker=ticker,
            )
            second = SentimentModel(
                content="bad",
                rate=-1.0,
                category="negative",
                posted_at=datetime.utcnow(),
                stock_ticker=ticker,
            )
            session.add_all([first, second])

        async with get_async_session() as session:
            repository = SentimentRepository(session)
            sentiments = await repository.list_by_stock_ticker(ticker)

            assert len(sentiments) >= 2
            assert {s.content for s in sentiments} == {"good", "bad"}

    asyncio.run(_test())
