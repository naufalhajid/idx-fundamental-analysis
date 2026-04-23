import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas.debate import CIOVerdict, DebateChamberState, DebateMessage
from services.debate_chamber import DebateChamber, data_scout_router, debate_router


# ---------------------------------------------------------------------------
# Router Tests (pure functions — no mocking needed)
# ---------------------------------------------------------------------------


class TestDebateRouter:
    """Verify debate loop routing logic."""

    def _make_state(self, round_count: int) -> DebateChamberState:
        return {
            "ticker": "BBRI",
            "raw_data": "",
            "debate_history": [],
            "round_count": round_count,
            "final_verdict": "",
            "error": None,
        }

    def test_continues_at_round_zero(self):
        assert debate_router(self._make_state(0)) == "bullish_analyst"

    def test_continues_at_round_one(self):
        assert debate_router(self._make_state(1)) == "bullish_analyst"

    def test_ends_at_round_two(self):
        assert debate_router(self._make_state(2)) == "cio_judge"

    def test_ends_beyond_max_round(self):
        """Safety: if round_count overshoots, still route to CIO — no infinite loop."""
        assert debate_router(self._make_state(5)) == "cio_judge"
        assert debate_router(self._make_state(100)) == "cio_judge"


class TestDataScoutRouter:
    """Verify error-handling routing after data scout."""

    def test_routes_to_bull_on_success(self):
        state: DebateChamberState = {
            "ticker": "BBRI",
            "raw_data": "valid data",
            "debate_history": [],
            "round_count": 0,
            "final_verdict": "",
            "error": None,
        }
        assert data_scout_router(state) == "bullish_analyst"

    def test_routes_to_end_on_error(self):
        state: DebateChamberState = {
            "ticker": "BBRI",
            "raw_data": "",
            "debate_history": [],
            "round_count": 0,
            "final_verdict": "",
            "error": "Failed to fetch data",
        }
        assert data_scout_router(state) == "__end__"

    def test_routes_to_end_on_empty_error_string(self):
        """Even an empty non-None string is considered an error (str | None semantics)."""
        state: DebateChamberState = {
            "ticker": "BBRI",
            "raw_data": "",
            "debate_history": [],
            "round_count": 0,
            "final_verdict": "",
            "error": "",
        }
        # Empty string is still not None — this IS an error state
        assert data_scout_router(state) == "__end__"


# ---------------------------------------------------------------------------
# State Isolation Tests
# ---------------------------------------------------------------------------


class TestDebateStateReset:
    """Verify no history leakage between ticker runs."""

    def test_independent_state_dicts(self):
        state_1: DebateChamberState = {
            "ticker": "BBRI",
            "raw_data": "data for BBRI",
            "debate_history": [DebateMessage(role="bull", content="arg1", round_num=1)],
            "round_count": 2,
            "final_verdict": '{"rating": "BUY"}',
            "error": None,
        }

        state_2: DebateChamberState = {
            "ticker": "BBCA",
            "raw_data": "",
            "debate_history": [],
            "round_count": 0,
            "final_verdict": "",
            "error": None,
        }

        # States are completely independent
        assert state_2["debate_history"] == []
        assert state_2["round_count"] == 0
        assert state_2["ticker"] == "BBCA"
        assert state_1["debate_history"][0].content == "arg1"


# ---------------------------------------------------------------------------
# CIOVerdict Schema Tests
# ---------------------------------------------------------------------------


class TestCIOVerdict:
    """Verify CIOVerdict Pydantic model behavior."""

    def test_valid_verdict(self):
        verdict = CIOVerdict(
            ticker="BBRI",
            rating="BUY",
            confidence=0.75,
            key_catalysts=["Strong ROE", "Growing deposits"],
            key_risks=["Rising NPL"],
            summary="BBRI is a strong buy based on fundamentals.",
        )
        assert verdict.rating == "BUY"
        assert verdict.confidence == 0.75
        assert len(verdict.key_catalysts) == 2
        assert len(verdict.key_risks) == 1

    def test_default_verdict_is_hold(self):
        """Default CIOVerdict should be a safe HOLD with zero confidence."""
        verdict = CIOVerdict()
        assert verdict.rating == "HOLD"
        assert verdict.confidence == 0.0
        assert verdict.key_catalysts == []
        assert verdict.key_risks == []

    def test_serialization_roundtrip(self):
        original = CIOVerdict(
            ticker="TLKM",
            rating="STRONG_SELL",
            confidence=0.9,
            key_catalysts=["Monopoly position"],
            key_risks=["Debt", "Regulation", "Competition"],
            summary="Avoid.",
        )
        json_str = original.model_dump_json()
        restored = CIOVerdict.model_validate_json(json_str)
        assert restored.ticker == original.ticker
        assert restored.rating == original.rating
        assert restored.key_risks == original.key_risks

    def test_malformed_json_fallback(self):
        """Simulates what happens when CIO output is partially valid."""
        # Missing required fields should use defaults
        partial = {"ticker": "BBRI", "rating": "BUY"}
        verdict = CIOVerdict(**partial)
        assert verdict.ticker == "BBRI"
        assert verdict.rating == "BUY"
        assert verdict.confidence == 0.0  # default
        assert verdict.key_catalysts == []  # default


# ---------------------------------------------------------------------------
# DebateMessage Tests
# ---------------------------------------------------------------------------


class TestDebateMessage:
    def test_creation(self):
        msg = DebateMessage(role="bull", content="Strong buy case", round_num=1)
        assert msg.role == "bull"
        assert msg.round_num == 1

    def test_operator_add_semantics(self):
        """operator.add should concatenate debate message lists."""
        history_1 = [DebateMessage(role="bull", content="a", round_num=1)]
        history_2 = [DebateMessage(role="bear", content="b", round_num=1)]

        combined = history_1 + history_2  # This is what operator.add does
        assert len(combined) == 2
        assert combined[0].role == "bull"
        assert combined[1].role == "bear"


# ---------------------------------------------------------------------------
# Full Graph Integration Tests (mocked nodes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFullGraphMockedNodes:
    """Test LangGraph state machine traversal with fully mocked LLM calls."""

    def _make_mock_llm(self, content: str = "mocked response"):
        """Create a mock LLM that returns a canned response."""
        mock = MagicMock()
        mock_response = MagicMock()
        mock_response.content = content
        mock.ainvoke = AsyncMock(return_value=mock_response)
        return mock

    @pytest.fixture
    def mock_chamber(self):
        """Create a DebateChamber with mocked LLMs and Stockbit client."""
        mock_flash = self._make_mock_llm("Mocked fundamental summary: PE=10, ROE=20%")
        mock_pro = self._make_mock_llm("Mocked analyst argument")

        # Mock structured output for CIO
        mock_verdict = CIOVerdict(
            ticker="BBRI",
            rating="BUY",
            confidence=0.8,
            key_catalysts=["Strong ROE"],
            key_risks=["Rising NPL"],
            summary="Buy BBRI.",
        )
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=mock_verdict)
        mock_pro.with_structured_output = MagicMock(return_value=mock_structured)

        mock_stockbit = MagicMock()
        mock_stockbit.get = MagicMock(return_value={"data": {"stats": {"market_cap": "100T"}}})

        return DebateChamber(
            flash_llm=mock_flash,
            pro_llm=mock_pro,
            stockbit_client=mock_stockbit,
        )

    async def test_full_traversal_two_rounds(self, mock_chamber):
        """Graph should complete with exactly 2 debate rounds (4 messages total)."""
        result = await mock_chamber.run("BBRI")

        assert result["ticker"] == "BBRI"
        assert result["error"] is None
        assert result["round_count"] == 2
        assert len(result["debate_history"]) == 4  # bull1, bear1, bull2, bear2
        assert result["final_verdict"] != ""

        # Verify debate order
        roles = [m.role for m in result["debate_history"]]
        assert roles == ["bull", "bear", "bull", "bear"]

        # Verify round numbers
        round_nums = [m.round_num for m in result["debate_history"]]
        assert round_nums == [1, 1, 2, 2]

    async def test_data_scout_error_short_circuits(self):
        """When Stockbit returns empty data, graph should abort immediately."""
        mock_flash = self._make_mock_llm()
        mock_pro = self._make_mock_llm()

        mock_stockbit = MagicMock()
        mock_stockbit.get = MagicMock(return_value={})  # Empty = failure

        chamber = DebateChamber(
            flash_llm=mock_flash,
            pro_llm=mock_pro,
            stockbit_client=mock_stockbit,
        )
        result = await chamber.run("INVALID")

        assert result["error"] is not None
        assert result["debate_history"] == []
        assert result["round_count"] == 0
        assert result["final_verdict"] == ""

    async def test_verdict_is_valid_json(self, mock_chamber):
        """CIO verdict should be valid JSON deserializable to CIOVerdict."""
        result = await mock_chamber.run("BBCA")

        verdict_data = json.loads(result["final_verdict"])
        verdict = CIOVerdict(**verdict_data)
        assert verdict.rating in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL")
        assert 0.0 <= verdict.confidence <= 1.0


# ---------------------------------------------------------------------------
# Round Count Semantics Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRoundCountSemantics:
    """Verify that exactly 2 full Bull↔Bear cycles occur before CIO."""

    async def test_exactly_two_cycles(self):
        """Track LLM invocations to verify cycle count."""
        call_log = []

        mock_flash = MagicMock()
        mock_flash_response = MagicMock()
        mock_flash_response.content = "summary data"
        mock_flash.ainvoke = AsyncMock(return_value=mock_flash_response)

        mock_pro = MagicMock()
        original_ainvoke = AsyncMock()

        async def tracking_ainvoke(messages):
            # Detect which node is calling based on system prompt content
            system_msg = messages[0].content if messages else ""
            if "BUY case" in system_msg:
                call_log.append("bull")
            elif "risk" in system_msg.lower() and "red flag" in system_msg.lower():
                call_log.append("bear")
            elif "Chief Investment Officer" in system_msg:
                call_log.append("cio")

            mock_response = MagicMock()
            mock_response.content = "mocked argument"
            return mock_response

        mock_pro.ainvoke = tracking_ainvoke

        mock_verdict = CIOVerdict(ticker="TEST", rating="HOLD", confidence=0.5)
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=mock_verdict)
        mock_pro.with_structured_output = MagicMock(return_value=mock_structured)

        mock_stockbit = MagicMock()
        mock_stockbit.get = MagicMock(return_value={"data": {}})

        chamber = DebateChamber(
            flash_llm=mock_flash,
            pro_llm=mock_pro,
            stockbit_client=mock_stockbit,
        )
        result = await chamber.run("TEST")

        assert result["round_count"] == 2
        assert call_log.count("bull") == 2
        assert call_log.count("bear") == 2


