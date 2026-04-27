"""
tests/test_debate_chamber_hardening.py

Regression tests for the "Deep-Dive Audit" hardening changes:

1. Budget guard (``core.budget``) raises ``BudgetExhaustedError`` at the
   configured ceiling and mutates no state on raise.
2. Permanent errors (e.g. "invalid API key") are NOT retried by the
   ``_is_transient_error`` predicate.
3. The deterministic ``_state_cleaner_node`` preserves every Rp price
   mentioned in the debate history (regression against the LLM-based
   cleaner which sometimes dropped numbers).
4. ``_classify_signals`` handles null fair-value gracefully and flags
   the 8–10% MA50 overextension band.
"""

from __future__ import annotations

import asyncio

import pytest

from core import budget
from core.budget import (
    BudgetExhaustedError,
    check_and_increment_pro_budget,
    get_usage,
    reset_budget,
)
from services.debate_chamber import DebateChamber, _is_transient_error
from schemas.debate import DebateMessage


# ---------------------------------------------------------------------------
# Budget guard
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_budget():
    """Reset per-process budget counters between tests."""

    reset_budget()
    yield
    reset_budget()


def test_budget_guard_raises_at_ceiling(monkeypatch):
    """Once the Pro counter reaches the ceiling, the guard must raise."""

    monkeypatch.setattr(budget, "MAX_PRO_CALLS_PER_RUN", 3)

    async def _drive() -> None:
        for _ in range(3):
            await check_and_increment_pro_budget()
        # 4th call must raise
        with pytest.raises(BudgetExhaustedError):
            await check_and_increment_pro_budget()

    asyncio.run(_drive())

    # State should reflect EXACTLY 3 successful calls — the failed call
    # must not have incremented the counter.
    assert get_usage()["pro_calls"] == 3


def test_budget_exhausted_is_not_transient():
    """BudgetExhaustedError must NEVER be retried by tenacity."""

    exc = BudgetExhaustedError("budget blown")
    assert _is_transient_error(exc) is False


# ---------------------------------------------------------------------------
# Permanent-error whitelist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "401 Invalid API key",
        "Authentication failed for Gemini endpoint",
        "Billing account suspended",
        "permission_denied: quota consumed",
        "response blocked due to SAFETY policy",
    ],
)
def test_permanent_errors_never_retried(message):
    assert _is_transient_error(Exception(message)) is False


@pytest.mark.parametrize(
    "message",
    [
        "429 Too Many Requests",
        "503 Service Unavailable",
        "Deadline exceeded while generating",
        "Resource exhausted: please retry",
    ],
)
def test_transient_errors_are_retried(message):
    assert _is_transient_error(Exception(message)) is True


# ---------------------------------------------------------------------------
# Deterministic state cleaner — must preserve every Rp price
# ---------------------------------------------------------------------------


def _make_chamber_without_llm() -> DebateChamber:
    """Build a DebateChamber stub that never calls the network."""

    class _Noop:
        async def ainvoke(self, _messages):  # pragma: no cover - never called here
            raise AssertionError("LLM should not be invoked in cleaner test")

        def with_structured_output(self, _schema):
            return self

    return DebateChamber(flash_llm=_Noop(), pro_llm=_Noop(), stockbit_client=object())


def test_state_cleaner_preserves_all_prices():
    chamber = _make_chamber_without_llm()

    bull = DebateMessage(
        role="bull",
        content=(
            "Entry zone at Rp 4,850 with fair value Rp 5,200. "
            "Target Rp 5,400 against support at Rp 4,700."
        ),
        round_num=1,
    )
    bear = DebateMessage(
        role="bear",
        content=(
            "Stop at Rp 4,600 is too tight. Historic breakdown to Rp 4,400 "
            "wipes margin of safety."
        ),
        round_num=1,
    )

    state = {"debate_history": [bull, bear]}
    update = asyncio.run(chamber._state_cleaner_node(state))  # type: ignore[arg-type]

    new_history = update["debate_history"]
    assert new_history[0].round_num == -1  # replace sentinel

    evidence = new_history[1].content
    for expected in ("4,850", "5,200", "5,400", "4,700", "4,600", "4,400"):
        assert expected in evidence, f"{expected} dropped from cleaned history"


# ---------------------------------------------------------------------------
# Signal classifier tolerance bands
# ---------------------------------------------------------------------------


def test_classify_signals_null_fair_value_returns_none():
    chamber = _make_chamber_without_llm()
    f_ok, t_ok, flag, reason = chamber._classify_signals(
        current_price=5_000, fair_value=0.0, ma50=4_900
    )
    assert f_ok is None
    assert t_ok is True
    assert flag is False
    assert "fair_value=null" in reason


def test_classify_signals_overextended_soft_zone():
    chamber = _make_chamber_without_llm()
    # 9% above MA50 — soft zone (still ✅ but flagged)
    f_ok, t_ok, flag, _ = chamber._classify_signals(
        current_price=1_090, fair_value=1_200, ma50=1_000
    )
    assert f_ok is True
    assert t_ok is True
    assert flag is True


def test_classify_signals_overextended_hard_reject():
    chamber = _make_chamber_without_llm()
    # 15% above MA50 — hard reject
    f_ok, t_ok, flag, reason = chamber._classify_signals(
        current_price=1_150, fair_value=1_400, ma50=1_000
    )
    assert t_ok is False
    assert flag is False
    assert "EXTENDED" in reason
