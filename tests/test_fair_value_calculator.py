"""Tests for services/fair_value_calculator.py — DDM spread and historical multiples extraction."""

import pytest

from services.fair_value_calculator import (
    FairValueCalculator,
    KeyStats,
    extract_historical_multiples,
    get_historical_multiples,
)


# ---------------------------------------------------------------------------
# DDM minimum spread (ke - g >= 3%)
# ---------------------------------------------------------------------------

class TestDDMSpread:

    def test_ddm_returns_none_when_spread_below_3_percent(self):
        """DDM should return None when ke - g < 0.03 to avoid noise sensitivity."""
        stats = KeyStats(
            ticker="TEST",
            dps=200.0,
            cost_of_equity=0.10,
            growth_rate=0.08,  # spread = 2% → too narrow
        )
        calc = FairValueCalculator(stats)
        assert calc.fair_value_ddm() is None

    def test_ddm_valid_when_spread_at_3_percent(self):
        """DDM should work when ke - g = exactly 0.03."""
        stats = KeyStats(
            ticker="TEST",
            dps=200.0,
            cost_of_equity=0.10,
            growth_rate=0.07,  # spread = 3%
            current_price=5000.0,
        )
        calc = FairValueCalculator(stats)
        result = calc.fair_value_ddm()
        assert result is not None
        # DDM = 200 / 0.03 = 6666.67 → rounded to 6667
        assert result == pytest.approx(6667, abs=1)

    def test_ddm_valid_when_spread_above_3_percent(self):
        stats = KeyStats(
            ticker="TEST",
            dps=200.0,
            cost_of_equity=0.12,
            growth_rate=0.05,  # spread = 7%
            current_price=3000.0,
        )
        calc = FairValueCalculator(stats)
        result = calc.fair_value_ddm()
        assert result is not None
        # DDM = 200 / 0.07 ≈ 2857
        assert result == pytest.approx(2857, abs=1)


# ---------------------------------------------------------------------------
# extract_historical_multiples — API response parsing
# ---------------------------------------------------------------------------

class TestExtractHistoricalMultiples:

    def test_fallback_to_hardcoded_on_empty_response(self):
        """When API response has no data, should return hardcoded defaults."""
        result = extract_historical_multiples({}, "BBCA")
        # Should match HISTORICAL_MULTIPLES["BBCA"]
        assert result["pe"] == 25.0
        assert result["pb"] == 4.5

    def test_fallback_to_generic_defaults_for_unknown_ticker(self):
        result = extract_historical_multiples({}, "UNKNOWN_TICKER")
        assert result["pe"] == 15.0
        assert result["pb"] == 2.0

    def test_extracts_from_yearly_dict_pattern(self):
        """Pattern 1: data.{year}.PE / data.{year}.PBV."""
        api_response = {
            "data": {
                "2024": {"PE": 14.0, "PBV": 2.1},
                "2023": {"PE": 12.0, "PBV": 1.8},
                "2022": {"PE": 16.0, "PBV": 2.5},
                "2021": {"PE": 13.0, "PBV": 2.0},
                "2020": {"PE": 11.0, "PBV": 1.6},
            }
        }
        result = extract_historical_multiples(api_response, "NEWSTOCK")
        # Medians: PE sorted [11,12,13,14,16] → 13.0, PB sorted [1.6,1.8,2.0,2.1,2.5] → 2.0
        assert result["pe"] == 13.0
        assert result["pb"] == 2.0

    def test_extracts_from_historical_ratio_list_pattern(self):
        """Pattern 2: data.historicalRatio as a list of dicts."""
        api_response = {
            "data": {
                "historicalRatio": [
                    {"PE": 15.0, "PBV": 3.0},
                    {"PE": 14.0, "PBV": 2.8},
                    {"PE": 16.0, "PBV": 3.2},
                    {"PE": 13.0, "PBV": 2.5},
                    {"PE": 17.0, "PBV": 3.5},
                ]
            }
        }
        result = extract_historical_multiples(api_response, "NEWSTOCK")
        # Medians: PE sorted [13,14,15,16,17] → 15, PB sorted [2.5,2.8,3.0,3.2,3.5] → 3.0
        assert result["pe"] == 15.0
        assert result["pb"] == 3.0

    def test_needs_minimum_3_values_for_override(self):
        """With fewer than 3 data points, keep hardcoded defaults."""
        api_response = {
            "data": {
                "2024": {"PE": 14.0, "PBV": 2.1},
                "2023": {"PE": 12.0, "PBV": 1.8},
            }
        }
        result = extract_historical_multiples(api_response, "BBCA")
        # Only 2 data points → should keep hardcoded BBCA values
        assert result["pe"] == 25.0
        assert result["pb"] == 4.5

    def test_ignores_negative_and_zero_values(self):
        api_response = {
            "data": {
                "2024": {"PE": 0, "PBV": -1.0},
                "2023": {"PE": 12.0, "PBV": 1.8},
                "2022": {"PE": -5.0, "PBV": 2.0},
                "2021": {"PE": 14.0, "PBV": 2.2},
                "2020": {"PE": 13.0, "PBV": 1.9},
            }
        }
        result = extract_historical_multiples(api_response, "NEWSTOCK")
        # Valid PE: [12, 14, 13] → median = 13.0
        # Valid PB: [1.8, 2.0, 2.2, 1.9] → sorted [1.8, 1.9, 2.0, 2.2] → median = 1.9
        # (Only 3 valid PE, 4 valid PB — both >= 3 threshold)
        assert result["pe"] == 13.0
        assert result["pb"] == pytest.approx(2.0, abs=0.1)


# ---------------------------------------------------------------------------
# get_historical_multiples — hardcoded fallback
# ---------------------------------------------------------------------------

class TestGetHistoricalMultiples:

    def test_known_ticker_returns_specific_values(self):
        result = get_historical_multiples("BBRI")
        assert result["pe"] == 14.0
        assert result["pb"] == 2.2

    def test_unknown_ticker_returns_defaults(self):
        result = get_historical_multiples("ZZZZZ")
        assert result["pe"] == 15.0
        assert result["pb"] == 2.0
        assert result["cost_of_equity"] == 0.10
        assert result["growth_rate"] == 0.06
