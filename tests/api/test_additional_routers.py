from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.main import app
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
from db.models.stock import Stock as StockModel
from db.models.stock_price import StockPrice as StockPriceModel
from db.models.sentiment import Sentiment as SentimentModel
from db.session import get_session


client = TestClient(app)


def _setup_database() -> None:
    database.setup_db(is_drop_table=False)


def test_get_fundamental_by_ticker_returns_200() -> None:
    _setup_database()
    ticker = f"FUND_API_{uuid4().hex[:8]}"

    with get_session() as session:
        stock = StockModel(
            ticker=ticker,
            name="Fundamental Test",
            ipo_date="2020-01-01",
            note="",
            market_cap=100.0,
            home_page="https://example.com",
        )

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

        session.add(stock)
        session.add(fundamental)

    response = client.get(f"/fundamentals/{ticker}")
    assert response.status_code == 200


def test_get_key_analysis_by_ticker_returns_data() -> None:
    _setup_database()
    ticker = f"KEY_API_{uuid4().hex[:8]}"

    with get_session() as session:
        stock = StockModel(
            ticker=ticker,
            name="Key Analysis Test",
            ipo_date="2020-01-01",
            note="",
            market_cap=100.0,
            home_page="https://example.com",
        )
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
        session.add(stock)
        session.add(key)

    response = client.get(f"/key-analyses/{ticker}")

    assert response.status_code == 200
    data = response.json()
    assert data["normal_price"] == 10.0
    assert data["net_debt_to_equity_ratio"] == 0.8


def test_list_stock_prices_by_ticker_returns_list() -> None:
    _setup_database()
    ticker = f"PRICE_API_{uuid4().hex[:8]}"

    with get_session() as session:
        stock = StockModel(
            ticker=ticker,
            name="Price Test",
            ipo_date="2020-01-01",
            note="",
            market_cap=100.0,
            home_page="https://example.com",
        )
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
        session.add(stock)
        session.add_all([first, second])

    response = client.get(f"/stock-prices/{ticker}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    closes = {item["close"] for item in data}
    assert 100.0 in closes and 101.0 in closes


def test_list_sentiments_by_ticker_returns_list() -> None:
    _setup_database()
    ticker = f"SENT_API_{uuid4().hex[:8]}"

    with get_session() as session:
        stock = StockModel(
            ticker=ticker,
            name="Sentiment Test",
            ipo_date="2020-01-01",
            note="",
            market_cap=100.0,
            home_page="https://example.com",
        )
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
        session.add(stock)
        session.add_all([first, second])

    response = client.get(f"/sentiments/{ticker}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    contents = {item["content"] for item in data}
    assert contents == {"good", "bad"}
