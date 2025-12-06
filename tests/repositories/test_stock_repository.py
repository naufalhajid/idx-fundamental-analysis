import asyncio

import pytest

from db import database
from db.models.stock import Stock as StockModel
from db.session import get_async_session
from repositories.stock_repository import StockRepository


TEST_TICKER = "REPO_TEST_TICKER"


@pytest.fixture(scope="module", autouse=True)
def setup_database() -> None:
    database.setup_db(is_drop_table=False)


@pytest.fixture(autouse=True)
def clean_stock() -> None:
    async def _clean() -> None:
        async with get_async_session() as session:
            repository = StockRepository(session)

            existing = await repository.get_by_ticker(TEST_TICKER)
            if existing is not None:
                await repository.delete(existing)

    asyncio.run(_clean())
    yield
    asyncio.run(_clean())


def test_add_and_get_by_ticker() -> None:
    async def _test() -> None:
        async with get_async_session() as session:
            repository = StockRepository(session)

            stock = StockModel(
                ticker=TEST_TICKER,
                name="Repo Test Company",
                ipo_date="2020-01-01",
                note="",
                market_cap=123.45,
                home_page="https://example.com/repo",
            )

            await repository.add(stock)

        async with get_async_session() as session:
            repository = StockRepository(session)
            stored = await repository.get_by_ticker(TEST_TICKER)

            assert stored is not None
            assert stored.ticker == TEST_TICKER
            assert stored.name == "Repo Test Company"
            assert stored.market_cap == 123.45

    asyncio.run(_test())


def test_base_repository_get_and_list() -> None:
    async def _test() -> None:
        async with get_async_session() as session:
            repository = StockRepository(session)

            stock = StockModel(
                ticker=TEST_TICKER,
                name="Repo Test Company 2",
                ipo_date="2020-01-01",
                note="",
                market_cap=200.0,
                home_page="https://example.com/repo2",
            )

            await repository.add(stock)
            await session.flush()
            stock_id = stock.id

            fetched = await repository.get(stock_id)
            assert fetched is not None
            assert fetched.id == stock_id

            stocks = await repository.list()
            assert any(s.id == stock_id for s in stocks)

    asyncio.run(_test())
