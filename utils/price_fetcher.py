import asyncio
import yfinance as yf
import pandas as pd
from utils.logger_config import logger

async def fetch_current_price(ticker: str) -> float:
    """Fetch last close price for an IHSG (.JK) ticker. Returns 0.0 on failure.

    Handles yfinance 1.3+ MultiIndex columns:
      Older yfinance returned a DataFrame with plain column names ('Close', 'High', ...).
      yfinance 1.3+ returns MultiIndex columns for single-ticker downloads:
        ('Close', 'ADRO.JK'), ('High', 'ADRO.JK'), ...
      Without flattening, data['Close'] raises a KeyError, silently returning 0.0
      and degrading the CIO trade envelope to price=0.
    """
    try:
        data = await asyncio.to_thread(
            yf.download, f"{ticker}.JK", period="5d", progress=False
        )
        if data is None or len(data) == 0:
            logger.warning(f"[PriceFetch] {ticker}: empty response from yfinance")
            return 0.0

        # Flatten MultiIndex columns if present (yfinance 1.3+)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        price = float(data["Close"].squeeze().iloc[-1])
        logger.info(f"[PriceFetch] {ticker} -> Rp {price:,.0f}")
        return price
    except Exception as e:
        logger.warning(f"[PriceFetch] Failed for {ticker}: {e}")
    return 0.0