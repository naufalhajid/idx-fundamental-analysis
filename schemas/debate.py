"""
schemas/debate.py — State & Schema definitions for the IHSG Swing Trade Debate Chamber.

Swing Trade update (this session):
- CIOVerdict rebuilt for 1-3 month swing trade frame:
    • fair_value, entry_price_range, target_price, stop_loss (concrete prices)
    • expected_return auto-calculated from entry midpoint → target_price
    • is_overvalued auto-flag when current_price > fair_value
    • risk_reward_ratio auto-calculated; rating forced to HOLD/AVOID when < 1.0
    • wait_and_see kept (confidence < 0.60 gate)
- DebateChamberState gains `current_price` field for margin-of-safety logic
- SwingTradeValidator helper: standalone function for the Synthesizer / CIO nodes
"""

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Base helper
# ---------------------------------------------------------------------------

class BaseDataClass(BaseModel):
    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# Core message type
# ---------------------------------------------------------------------------

class DebateMessage(BaseDataClass):
    """Single argument in the stock debate chamber."""

    role: Literal[
        "scout",
        "bull",
        "bear",
        "synthesizer",
        "devils_advocate",
        "system",
    ] = "scout"
    content: str = ""
    round_num: int = 0


# ---------------------------------------------------------------------------
# CIO Verdict — Swing Trade edition, Pydantic-validated, Svelte-ready
# ---------------------------------------------------------------------------

class CIOVerdict(BaseDataClass):
    """
    Structured output from the CIO Judge — Swing Trade frame (1-3 months, 3-10% target).

    Auto-computed fields (model_validator, never sent by the LLM):
        expected_return   — % gain from entry_mid to target_price
        risk_reward_ratio — expected_return / stop_loss_pct
        is_overvalued     — current_price > fair_value
        wait_and_see      — confidence < 0.60  OR  risk_reward_ratio < 1.0

    Used with LangChain's `.with_structured_output()`.
    Svelte reads this JSON directly — field names are the UI contract.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    ticker: str = ""

    # ── Core verdict ─────────────────────────────────────────────────────────
    rating: Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "AVOID"] = "HOLD"

    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="CIO confidence in the verdict, 0-1.",
    )

    # ── Swing-trade price levels (LLM must supply these) ─────────────────────
    fair_value: float | None = Field(
        default=None,
        description=(
            "Intrinsic value calculated from Relative Valuation. "
            "Pass null if INSUFFICIENT_DATA or 0."
        ),
    )

    entry_price_range: str | None = Field(
        default=None,
        description="Safe accumulation zone. Format: 'XXXX - YYYY'. Null if invalid.",
    )

    target_price: float | None = Field(
        default=None,
        description="Swing-trade profit target for 1-3 months. Null if void.",
    )

    stop_loss: float | None = Field(
        default=None,
        description="Hard cut-loss price. Null if void.",
    )

    current_price: float | None = Field(
        default=None,
        description="Last traded price at analysis time (IDR).",
    )

    # ── Narrative fields (LLM must supply these) ──────────────────────────────
    timeframe: str = Field(default="1-3 Months")

    weighted_reasoning: str = Field(
        default="",
        description=(
            "CIO's explicit explanation of how Technical entry logic and "
            "Fundamental fair value were combined to reach this verdict."
        ),
    )

    critical_risk_factor: str = Field(
        default="",
        description="The single factor most likely to invalidate this swing trade.",
    )

    key_catalysts: list[str] = Field(
        default_factory=list,
        description="Top 2-3 reasons the trade should work within 1-3 months.",
    )

    key_risks: list[str] = Field(
        default_factory=list,
        description="Top 2-3 risks that could trigger the stop-loss.",
    )

    summary: str = Field(
        default="",
        description="3-sentence executive summary for the Svelte trade card.",
    )

    # ── Auto-computed (never sent by LLM; derived post-validation) ────────────
    expected_return: str | None = Field(
        default=None,
        description="Auto-calculated: % gain from entry midpoint to target_price. null if invalid.",
    )

    risk_reward_ratio: float | None = Field(
        default=None,
        description="Auto-calculated: potential_gain_pct / potential_loss_pct. null if invalid.",
    )

    is_overvalued: bool | None = Field(
        default=None,
        description="Auto-flag: True when current_price > fair_value.",
    )

    wait_and_see: bool = Field(
        default=False,
        description=(
            "Auto-flag: True when confidence < 0.60 OR risk_reward_ratio < 1.0. "
            "Svelte renders a yellow caution banner when this is True."
        ),
    )

    @model_validator(mode="after")
    def _derive_computed_fields(self) -> "CIOVerdict":
        """
        All business-logic enforcement lives here so the LLM never has to compute
        percentages correctly — it just supplies raw prices.
        """
        # 1. Parse entry midpoint from 'XXXX - YYYY' string
        entry_mid = self._parse_entry_mid()

        # 2. Expected return (entry mid → target)
        if entry_mid > 0 and self.target_price is not None and self.target_price > 0:
            gain_pct = ((self.target_price - entry_mid) / entry_mid) * 100
            self.expected_return = f"{gain_pct:+.1f}%"
        else:
            self.expected_return = None
            gain_pct = 0.0

        # 3. Risk/reward ratio
        if entry_mid > 0 and self.stop_loss is not None and self.stop_loss > 0 and entry_mid > self.stop_loss:
            loss_pct = ((entry_mid - self.stop_loss) / entry_mid) * 100
            self.risk_reward_ratio = round(gain_pct / loss_pct, 2) if loss_pct > 0 else 0.0
        else:
            self.risk_reward_ratio = None

        # 4. Overvaluation flag — Margin of Safety check
        if self.current_price is not None and self.fair_value is not None and self.fair_value > 0:
            self.is_overvalued = self.current_price > self.fair_value
        else:
            self.is_overvalued = None

        # 5. Force downgrade if profit potential is outside 3-10% band
        #    or if risk/reward is unfavourable
        bad_rr = (self.risk_reward_ratio is None or self.risk_reward_ratio < 1.0)
        if gain_pct < 3.0 or gain_pct > 10.0 or bad_rr or self.fair_value is None:
            if self.rating in ("STRONG_BUY", "BUY"):
                self.rating = "HOLD"

        # 6. Wait-and-see gate
        if self.confidence < 0.60 or bad_rr or self.fair_value is None:
            self.wait_and_see = True
            
        # 7. Actionability Guardrail: If AVOID or HOLD due to missing data, strip setup
        if self.rating in ("AVOID", "HOLD") and (self.fair_value is None or bad_rr):
            self.target_price = None
            self.stop_loss = None
            self.entry_price_range = None
            self.expected_return = None
            self.risk_reward_ratio = None
            self.summary += " (Setup trade disembunyikan/dibatalkan secara sistematis karena data fundamental tidak lengkap atau Risk/Reward tidak ideal)."

        return self

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_entry_mid(self) -> float:
        """Parse 'XXXX - YYYY' → midpoint float. Returns 0.0 on failure."""
        if not self.entry_price_range:
            return 0.0
        try:
            parts = [p.strip().replace(",", "") for p in self.entry_price_range.split("-")]
            lo, hi = float(parts[0]), float(parts[1])
            return (lo + hi) / 2
        except Exception:
            return 0.0

    def to_trade_card(self) -> dict:
        """
        Convenience method: returns the minimal dict the Svelte trade card needs.
        Call this in the API response handler instead of model_dump() if you want
        a leaner payload.
        """
        return {
            "ticker":             self.ticker,
            "rating":             self.rating,
            "buy_at":             self.entry_price_range,
            "sell_at":            self.target_price,
            "cut_loss":           self.stop_loss,
            "fair_value":         self.fair_value,
            "expected_return":    self.expected_return,
            "risk_reward":        self.risk_reward_ratio,
            "is_overvalued":      self.is_overvalued,
            "wait_and_see":       self.wait_and_see,
            "confidence":         self.confidence,
            "summary":            self.summary,
            "critical_risk":      self.critical_risk_factor,
        }


# ---------------------------------------------------------------------------
# Standalone validator (used by Synthesizer node — no LLM call needed)
# ---------------------------------------------------------------------------

def validate_swing_targets(
    current_price: float,
    fair_value: float,
    target_price: float,
    entry_price_range: str,
    stop_loss: float,
) -> dict:
    """
    Pure-Python margin-of-safety check injected by the Synthesizer node
    BEFORE the debate starts.  Returns a warning string the agents can read.

    This keeps the token-expensive Pro model focused on reasoning,
    not arithmetic.
    """
    warnings: list[str] = []

    # Overvaluation
    if fair_value > 0 and current_price > fair_value:
        premium = ((current_price - fair_value) / fair_value) * 100
        warnings.append(
            f"⚠️ OVERVALUED: Current price ({current_price:,.0f}) is "
            f"{premium:.1f}% above fair value ({fair_value:,.0f}). "
            "Swing trade is HIGH RISK — margin of safety is negative."
        )

    # Profit range gate
    try:
        parts = [p.strip().replace(",", "") for p in entry_price_range.split("-")]
        entry_mid = (float(parts[0]) + float(parts[1])) / 2
        if target_price > 0 and entry_mid > 0:
            gain_pct = ((target_price - entry_mid) / entry_mid) * 100
            if gain_pct < 3.0:
                warnings.append(
                    f"⚠️ LOW UPSIDE: Projected gain ({gain_pct:.1f}%) is below the "
                    "3% swing-trade minimum. Consider a different entry or target."
                )
            elif gain_pct > 10.0:
                warnings.append(
                    f"⚠️ AGGRESSIVE TARGET: Projected gain ({gain_pct:.1f}%) exceeds "
                    "10%. Verify target is below a strong resistance level."
                )
    except Exception:
        pass

    # R/R check
    if stop_loss > 0 and fair_value > 0:
        try:
            loss_pct = ((entry_mid - stop_loss) / entry_mid) * 100
            gain_pct_f = ((target_price - entry_mid) / entry_mid) * 100
            rr = gain_pct_f / loss_pct if loss_pct > 0 else 0
            if rr < 1.0:
                warnings.append(
                    f"⚠️ POOR R/R: Risk/Reward ratio is {rr:.2f} (below 1.0). "
                    "The potential loss exceeds the potential gain."
                )
        except Exception:
            pass

    return {
        "is_valid": len(warnings) == 0,
        "warnings": warnings,
        "warning_text": "\n".join(warnings) if warnings else "✅ Swing trade parameters within acceptable range.",
    }


# ---------------------------------------------------------------------------
# Custom reducer
# ---------------------------------------------------------------------------

def history_updater(
    left: list[DebateMessage] | None,
    right: list[DebateMessage] | None,
) -> list[DebateMessage]:
    """
    Append-by-default reducer for debate_history.

    Special case: if the first message in `right` has round_num == -1,
    it triggers a *replacement* (used by the State Cleaner node to prune
    the context window and prevent bloat).
    """
    left_list = left or []
    right_list = right or []
    if not right_list:
        return left_list
    if right_list[0].round_num == -1:
        # The sentinel message is discarded; the rest become the new history.
        return right_list[1:]
    return left_list + right_list


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class DebateChamberState(TypedDict):
    """
    Canonical LangGraph state for the IHSG Swing Trade Debate Chamber.

    New field vs. previous version:
        current_price — last traded price, injected at run() time.
                        Used by the Synthesizer for the margin-of-safety warning
                        and passed through to CIOVerdict for auto-validation.

    Reducer notes
    -------------
    - debate_history  → history_updater  (append + prune support)
    - All other fields → default (last-write wins)
    """

    # Identity
    ticker: str
    current_price: float          # ← NEW: last traded price (IDR)

    # Parallel data collection outputs (Phase 1)
    fundamental_data: str
    technical_data: str
    sentiment_data: str

    # Merged string fed into the debate (includes margin-of-safety warnings)
    raw_data: str

    # Debate engine
    debate_history: Annotated[list[DebateMessage], history_updater]
    round_count: int
    consensus_reached: bool

    # Adaptive nodes
    devils_advocate_question: str

    # Final output
    final_verdict: str            # JSON-serialized CIOVerdict

    # Error propagation
    error: str | None
