"""Tests for utils/technicals.py — RSI, ATR, and IHSG tick snapping."""

import pandas as pd
import pytest

from utils.technicals import compute_atr, compute_rsi, snap_to_tick


# ---------------------------------------------------------------------------
# snap_to_tick — IHSG price fraction table
# ---------------------------------------------------------------------------

class TestSnapToTick:
    """Verify each tier of the IHSG price fraction table."""

    def test_zero_returns_zero(self):
        assert snap_to_tick(0) == 0.0

    def test_negative_returns_zero(self):
        assert snap_to_tick(-100) == 0.0

    def test_tier_1_below_200_tick_1(self):
        assert snap_to_tick(153.7) == 154.0
        assert snap_to_tick(99.0) == 99.0
        assert snap_to_tick(1.0) == 1.0

    def test_tier_2_200_to_500_tick_2(self):
        assert snap_to_tick(201.0) == 200.0  # round(100.5) = 100 → 200 (banker's rounding)
        assert snap_to_tick(203.0) == 204.0  # round(101.5) = 102 → 204
        assert snap_to_tick(333.0) == 332.0  # round(166.5) = 166 → 332 (banker's rounding)
        assert snap_to_tick(334.0) == 334.0

    def test_tier_3_500_to_2000_tick_5(self):
        assert snap_to_tick(502.0) == 500.0
        assert snap_to_tick(503.0) == 505.0
        assert snap_to_tick(1247.0) == 1245.0
        assert snap_to_tick(1248.0) == 1250.0

    def test_tier_4_2000_to_5000_tick_10(self):
        assert snap_to_tick(2005.0) == 2000.0  # round(200.5) = 200 → 2000 (banker's rounding)
        assert snap_to_tick(2006.0) == 2010.0
        assert snap_to_tick(4875.0) == 4880.0
        assert snap_to_tick(4870.0) == 4870.0

    def test_tier_5_above_5000_tick_25(self):
        assert snap_to_tick(5010.0) == 5000.0
        assert snap_to_tick(5013.0) == 5025.0
        assert snap_to_tick(10_050.0) == 10_050.0
        assert snap_to_tick(10_060.0) == 10_050.0
        assert snap_to_tick(10_063.0) == 10_075.0

    def test_returns_float(self):
        result = snap_to_tick(1000)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# compute_rsi — Wilder's EMA
# ---------------------------------------------------------------------------

class TestComputeRSI:
    """Verify RSI is computed using EMA, produces valid range, handles edge cases."""

    @pytest.fixture
    def sample_prices(self) -> pd.Series:
        """30 days of synthetic price data with a clear uptrend then pullback."""
        prices = [
            100, 102, 104, 103, 105, 107, 106, 108, 110, 109,
            111, 113, 112, 114, 116, 115, 117, 119, 118, 120,
            119, 118, 117, 116, 115, 116, 117, 118, 119, 120,
        ]
        return pd.Series(prices, dtype=float)

    def test_rsi_in_valid_range(self, sample_prices):
        rsi = compute_rsi(sample_prices)
        assert rsi.min() >= 0.0
        assert rsi.max() <= 100.0

    def test_rsi_uses_ema_not_sma(self, sample_prices):
        """RSI computed with EMA should differ from naive SMA-based RSI."""
        rsi_ema = compute_rsi(sample_prices)

        # Compute SMA-based RSI for comparison
        diff = sample_prices.diff(1).dropna()
        gain = diff.where(diff > 0, 0.0)
        loss = -diff.where(diff < 0, 0.0)
        avg_gain_sma = gain.rolling(window=14, min_periods=1).mean()
        avg_loss_sma = loss.rolling(window=14, min_periods=1).mean()
        rs_sma = avg_gain_sma / avg_loss_sma
        rsi_sma = 100 - (100 / (1 + rs_sma))

        # They must differ (EMA vs SMA produce different values)
        assert not rsi_ema.iloc[-1] == pytest.approx(rsi_sma.iloc[-1], abs=0.01), \
            "RSI should use EMA, but produced same result as SMA"

    def test_rsi_returns_series(self, sample_prices):
        result = compute_rsi(sample_prices)
        assert isinstance(result, pd.Series)

    def test_rsi_strong_uptrend_above_50(self):
        """A pure uptrend should have RSI well above 50."""
        prices = pd.Series([100 + i * 2 for i in range(30)], dtype=float)
        rsi = compute_rsi(prices)
        assert rsi.iloc[-1] > 70

    def test_rsi_strong_downtrend_below_50(self):
        """A pure downtrend should have RSI well below 50."""
        prices = pd.Series([200 - i * 2 for i in range(30)], dtype=float)
        rsi = compute_rsi(prices)
        assert rsi.iloc[-1] < 30


# ---------------------------------------------------------------------------
# compute_atr — Average True Range
# ---------------------------------------------------------------------------

class TestComputeATR:

    @pytest.fixture
    def ohlcv_data(self) -> tuple[pd.Series, pd.Series, pd.Series]:
        """20 days of synthetic high/low/close."""
        close = pd.Series([100 + i for i in range(20)], dtype=float)
        high = close + 3
        low = close - 3
        return high, low, close

    def test_atr_positive(self, ohlcv_data):
        high, low, close = ohlcv_data
        atr = compute_atr(high, low, close)
        # The last value should be a valid positive number
        assert atr.iloc[-1] > 0

    def test_atr_returns_series(self, ohlcv_data):
        high, low, close = ohlcv_data
        result = compute_atr(high, low, close)
        assert isinstance(result, pd.Series)

    def test_atr_reflects_volatility(self):
        """Higher volatility → higher ATR."""
        # Low volatility
        close_low = pd.Series([100 + i * 0.5 for i in range(20)], dtype=float)
        high_low = close_low + 1
        low_low = close_low - 1

        # High volatility
        close_high = pd.Series([100 + i * 0.5 for i in range(20)], dtype=float)
        high_high = close_high + 10
        low_high = close_high - 10

        atr_low = compute_atr(high_low, low_low, close_low)
        atr_high = compute_atr(high_high, low_high, close_high)

        assert atr_high.iloc[-1] > atr_low.iloc[-1]
