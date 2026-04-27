"""Tests for schemas/debate.py — CIOVerdict validation and DebateChamberState fields."""

import pytest

from schemas.debate import CIOVerdict, DebateMessage, validate_swing_targets


# ---------------------------------------------------------------------------
# CIOVerdict — model_validator auto-computation
# ---------------------------------------------------------------------------

class TestCIOVerdict:

    def test_expected_return_auto_calculated(self):
        """expected_return should be derived from entry midpoint → target_price."""
        v = CIOVerdict(
            ticker="BBRI",
            rating="BUY",
            confidence=0.75,
            fair_value=5200.0,
            entry_price_range="4800 - 5000",
            target_price=5280.0,
            stop_loss=4650.0,
            current_price=4900.0,
        )
        # Entry mid = (4800+5000)/2 = 4900
        # Expected return = (5280-4900)/4900 = 7.76%
        assert v.expected_return is not None
        assert "+7.8%" in v.expected_return or "+7.7%" in v.expected_return

    def test_risk_reward_auto_calculated(self):
        v = CIOVerdict(
            ticker="BBRI",
            rating="BUY",
            confidence=0.75,
            fair_value=5200.0,
            entry_price_range="4800 - 5000",
            target_price=5280.0,
            stop_loss=4650.0,
            current_price=4900.0,
        )
        # gain = 7.76%, loss = (4900-4650)/4900 = 5.10%
        # R/R = 7.76/5.10 ≈ 1.52
        assert v.risk_reward_ratio is not None
        assert v.risk_reward_ratio > 1.0

    def test_overvalued_flag_when_price_above_fv(self):
        v = CIOVerdict(
            ticker="UNVR",
            rating="HOLD",
            confidence=0.40,
            fair_value=3000.0,
            entry_price_range="3200 - 3400",
            target_price=3500.0,
            stop_loss=3100.0,
            current_price=3500.0,
        )
        assert v.is_overvalued is True

    def test_not_overvalued_when_price_below_fv(self):
        v = CIOVerdict(
            ticker="BBRI",
            rating="BUY",
            confidence=0.80,
            fair_value=5200.0,
            entry_price_range="4800 - 5000",
            target_price=5100.0,
            stop_loss=4700.0,
            current_price=4900.0,
        )
        assert v.is_overvalued is False

    def test_downgrade_to_hold_when_rr_below_1(self):
        """Rating forced to HOLD when R/R < 1.0."""
        v = CIOVerdict(
            ticker="GOTO",
            rating="BUY",
            confidence=0.70,
            fair_value=200.0,
            entry_price_range="180 - 190",
            target_price=192.0,   # tiny upside
            stop_loss=160.0,      # large downside
            current_price=185.0,
        )
        # gain = (192-185)/185 ≈ 3.78%, loss = (185-160)/185 ≈ 13.5%
        # R/R ≈ 0.28 → should force HOLD
        assert v.rating == "HOLD"

    def test_wait_and_see_when_low_confidence(self):
        v = CIOVerdict(
            ticker="BBCA",
            rating="HOLD",
            confidence=0.45,
            fair_value=10000.0,
            current_price=9500.0,
        )
        assert v.wait_and_see is True

    def test_actionability_guardrail_strips_levels(self):
        """AVOID with bad R/R should have trade levels stripped."""
        v = CIOVerdict(
            ticker="TEST",
            rating="AVOID",
            confidence=0.30,
            fair_value=None,
            entry_price_range="100 - 110",
            target_price=112.0,
            stop_loss=90.0,
            current_price=105.0,
        )
        assert v.target_price is None
        assert v.stop_loss is None
        assert v.entry_price_range is None

    def test_to_trade_card_keys(self):
        v = CIOVerdict(
            ticker="BMRI",
            rating="BUY",
            confidence=0.72,
            fair_value=7500.0,
            entry_price_range="7000 - 7200",
            target_price=7700.0,
            stop_loss=6800.0,
            current_price=7100.0,
        )
        card = v.to_trade_card()
        required_keys = {
            "ticker", "rating", "buy_at", "sell_at", "cut_loss",
            "fair_value", "expected_return", "risk_reward",
            "is_overvalued", "wait_and_see", "confidence",
            "summary", "critical_risk",
        }
        assert required_keys.issubset(set(card.keys()))


# ---------------------------------------------------------------------------
# validate_swing_targets — standalone Python validator
# ---------------------------------------------------------------------------

class TestValidateSwingTargets:

    def test_overvalued_produces_warning(self):
        result = validate_swing_targets(
            current_price=5500.0,
            fair_value=5000.0,
            target_price=5800.0,
            entry_price_range="5400 - 5600",
            stop_loss=5200.0,
        )
        assert not result["is_valid"]
        assert "OVERVALUED" in result["warning_text"]

    def test_low_upside_produces_warning(self):
        result = validate_swing_targets(
            current_price=4900.0,
            fair_value=5200.0,
            target_price=5010.0,   # ~2% gain → below 3% minimum
            entry_price_range="4850 - 4950",
            stop_loss=4700.0,
        )
        assert not result["is_valid"]
        assert "LOW UPSIDE" in result["warning_text"]

    def test_valid_setup_passes(self):
        result = validate_swing_targets(
            current_price=4900.0,
            fair_value=5200.0,
            target_price=5200.0,
            entry_price_range="4800 - 5000",
            stop_loss=4650.0,
        )
        assert result["is_valid"]


# ---------------------------------------------------------------------------
# DebateMessage
# ---------------------------------------------------------------------------

class TestDebateMessage:

    def test_default_role(self):
        msg = DebateMessage()
        assert msg.role == "scout"
        assert msg.round_num == 0

    def test_custom_role(self):
        msg = DebateMessage(role="bull", content="Testing", round_num=1)
        assert msg.role == "bull"
        assert msg.content == "Testing"
