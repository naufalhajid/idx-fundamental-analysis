from db.models.fundamental import Fundamental as FundamentalModel
from db.models.key_analysis import KeyAnalysis as KeyAnalysisModel
from db.models.sentiment import Sentiment as SentimentModel
from db.models.stock import Stock as StockModel
from db.models.stock_price import StockPrice as StockPriceModel


def test_stock_factory_creates_stock_instance(stock_factory) -> None:
    stock = stock_factory(
        ticker="FACTORY_TEST_TICKER",
        name="Factory Test Company",
        ipo_date="2021-01-01",
        note="Test note",
        market_cap=250.0,
        home_page="https://example.com/factory",
    )

    assert isinstance(stock, StockModel)
    assert stock.ticker == "FACTORY_TEST_TICKER"
    assert stock.name == "Factory Test Company"
    assert stock.ipo_date == "2021-01-01"
    assert stock.note == "Test note"
    assert stock.market_cap == 250.0
    assert stock.home_page == "https://example.com/factory"


def test_stock_factory_generates_unique_ticker(stock_factory) -> None:
    stock1 = stock_factory()
    stock2 = stock_factory()

    assert isinstance(stock1, StockModel)
    assert isinstance(stock2, StockModel)
    assert stock1.ticker != stock2.ticker
    assert stock1.ticker.startswith("TEST_")
    assert stock2.ticker.startswith("TEST_")


def test_stock_factory_creates_relations_by_default(stock_factory) -> None:
    stock = stock_factory()

    assert len(stock.stock_prices) == 1
    assert isinstance(stock.stock_prices[0], StockPriceModel)
    assert stock.stock_prices[0].stock_ticker == stock.ticker

    assert len(stock.fundamentals) == 1
    assert isinstance(stock.fundamentals[0], FundamentalModel)
    assert stock.fundamentals[0].stock_ticker == stock.ticker

    assert len(stock.sentiments) == 1
    assert isinstance(stock.sentiments[0], SentimentModel)
    assert stock.sentiments[0].stock_ticker == stock.ticker

    assert len(stock.key_analyses) == 1
    assert isinstance(stock.key_analyses[0], KeyAnalysisModel)
    assert stock.key_analyses[0].stock_ticker == stock.ticker


def test_stock_factory_without_relations(stock_factory) -> None:
    stock = stock_factory(with_relations=False)

    assert stock.stock_prices == []
    assert stock.fundamentals == []
    assert stock.sentiments == []
    assert stock.key_analyses == []


def test_stock_factory_populates_dummy_fundamental_values(stock_factory) -> None:
    stock = stock_factory()

    fundamental = stock.fundamentals[0]

    assert fundamental.stat.market_cap == 1_000_000_000.0
    assert fundamental.current_valuation.current_pe_ratio_ttm == 12.0
    assert fundamental.per_share.current_eps_ttm == 10.0
    assert fundamental.solvency.current_ratio_quarter == 2.0
    assert fundamental.management_effectiveness.return_on_equity_ttm == 0.2
    assert fundamental.profitability.net_profit_margin_quarter == 0.15
    assert fundamental.growth.revenue_quarter_yoy_growth == 0.1
    assert fundamental.dividend.dividend == 1.0
    assert fundamental.market_rank.piotroski_f_score == 8.0
    assert fundamental.income_statement.revenue_ttm == 1_000_000_000.0
    assert fundamental.balance_sheet.total_debt_quarter == 500_000_000.0
    assert fundamental.cash_flow_statement.free_cash_flow_ttm == 220_000_000.0
    assert fundamental.price_performance.one_year_price_returns == 0.25
