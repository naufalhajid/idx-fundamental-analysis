from builders.analysers import Analyser as MainAnalyser
from builders.analysers.fundamental_analyser import (
    FundamentalAnalyser,
)
from builders.analysers.sentiment_analyser import (
    SentimentAnalyser,
)
from builders.analysers.stock_price_analyser import (
    StockPriceAnalyser,
)
from builders.analysers.key_analysis_analyser import (
    KeyAnalysisAnalyser,
)

from schemas.stock import Stock as StockSchema


def _build_schema_stock_from_orm(stock_orm):
    return StockSchema.from_orm(stock_orm)


def test_fundamental_analyser_sheets_with_stock_factory(stock_factory) -> None:
    stock_orm = stock_factory()
    stock_schema = _build_schema_stock_from_orm(stock_orm)

    analyser = FundamentalAnalyser(stocks=[stock_schema])

    stocks_sheet = analyser.stocks_sheet()
    key_stats_sheet = analyser.key_statistics_sheet()

    assert len(stocks_sheet) == 2
    assert stocks_sheet[0][0] == "Ticker"
    assert stocks_sheet[1][0] == stock_schema.ticker

    assert len(key_stats_sheet) == 2
    assert key_stats_sheet[0][0] == "Ticker"
    assert key_stats_sheet[1][0] == stock_schema.ticker


def test_sentiment_analyser_sheet_with_stock_factory(stock_factory) -> None:
    stock_orm = stock_factory()
    stock_schema = _build_schema_stock_from_orm(stock_orm)

    analyser = SentimentAnalyser(stocks=[stock_schema])
    sheet = analyser.sentiment_sheet()

    assert len(sheet) == 2
    assert sheet[0] == ["Ticker", "Content", "Rate", "Category", "Posted At"]
    assert sheet[1][0] == stock_schema.ticker


def test_stock_price_analyser_sheet_with_stock_factory(stock_factory) -> None:
    stock_orm = stock_factory()
    stock_schema = _build_schema_stock_from_orm(stock_orm)

    analyser = StockPriceAnalyser(stocks=[stock_schema])
    sheet = analyser.stock_price_sheet()

    assert len(sheet) == 2
    assert sheet[0][0] == "Ticker"
    assert sheet[0][-1] == "Created At"
    assert sheet[1][0] == stock_schema.ticker
    assert sheet[1][-1] == stock_schema.stock_price.created_at.strftime("%Y-%m-%d")


def test_key_analysis_analyser_populates_key_analysis(stock_factory) -> None:
    stock_orm = stock_factory()
    stock_schema = _build_schema_stock_from_orm(stock_orm)

    KeyAnalysisAnalyser(stocks=[stock_schema])

    assert stock_schema.key_analysis is not None
    assert stock_schema.key_analysis.normal_price is not None
