import pytest
from unittest.mock import patch
import pandas as pd
from utils.price_fetcher import fetch_current_price

def make_mock_df(price=4875.0):
    idx = pd.date_range('2025-01-01', periods=3)
    df = pd.DataFrame({'Close': [4800.0, 4850.0, price]}, index=idx)
    return df

@pytest.mark.asyncio
async def test_returns_last_close():
    """Verify function returns the final Close value retrieved as a float."""
    with patch('utils.price_fetcher.yf.download', return_value=make_mock_df(4875.0)):
        price = await fetch_current_price('BBRI')
    assert price == 4875.0

@pytest.mark.asyncio
async def test_returns_zero_on_exception():
    """Verify exceptions inside yf.download result in 0.0 without crashing."""
    with patch('utils.price_fetcher.yf.download', side_effect=Exception('network error')):
        price = await fetch_current_price('BBRI')
    assert price == 0.0

@pytest.mark.asyncio
async def test_returns_zero_on_empty_df():
    """Verify empty DataFrame safely returns 0.0."""
    empty = pd.DataFrame({'Close': []})
    with patch('utils.price_fetcher.yf.download', return_value=empty):
        price = await fetch_current_price('BBRI')
    assert price == 0.0

@pytest.mark.asyncio
async def test_returns_zero_on_malformed_ticker():
    """Verify tickers returning empty strings or weird shapes are safely handled."""
    with patch('utils.price_fetcher.yf.download', side_effect=ValueError('Invalid Ticker')):
        price = await fetch_current_price('INVALID%$')
    assert price == 0.0

@pytest.mark.asyncio
async def test_multiindex_dataframe_extraction():
    """Verify yfinance newer version MultiIndex returns are properly extracted."""
    # Sometimes yfinance returns a MultiIndex when downloading multiple, or occasionally single.
    mi = pd.MultiIndex.from_tuples([('Close', 'BBRI')])
    df = pd.DataFrame([[4800.0], [4875.0]], columns=mi)
    with patch('utils.price_fetcher.yf.download', return_value=df):
        price = await fetch_current_price('BBRI')
    assert price == 4875.0

def test_no_local_fetch_in_orchestrator():
    """Verify fetch_current_price is fully decoupled and not defined in orchestrator."""
    import inspect
    import orchestrator
    src = inspect.getsource(orchestrator)
    assert 'def fetch_current_price' not in src, "fetch_current_price is still locally defined in orchestrator.py"

# Coverage target: utils.price_fetcher, orchestrator (import verification)
