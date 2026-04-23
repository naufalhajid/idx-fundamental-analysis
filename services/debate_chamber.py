"""
debate_chamber.py — Production-grade LangGraph multi-agent stock debate system.

Phase 1: Parallel Orchestration  — Fundamental / Chartist / Sentiment run concurrently.
Phase 2: Anti-Groupthink Logic   — Round-aware prompts; R2 forbids repeating R1 data.
Phase 3: Adaptive Short-Circuit  — Consensus bypass + State Cleaner (context pruning).
Phase 4: Decisive CIO Judge      — Weighted synthesis, Confidence gate, Pydantic output.

Target market : IHSG (Indonesia)
Token budget  : 500 k tokens  →  Flash for data extraction, Pro for reasoning only.
"""

import asyncio
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from providers.gemini import get_flash_llm, get_pro_llm
from schemas.debate import CIOVerdict, DebateChamberState, DebateMessage, validate_swing_targets
from services.stockbit_api_client import StockbitApiClient
from services.fair_value_calculator import build_fair_value_report
from utils.logger_config import logger


# ---------------------------------------------------------------------------
# Transient-error guard (retry only on 429 / 503)
# ---------------------------------------------------------------------------

def _is_transient_error(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "429" in s or "503" in s or "resource exhausted" in s


# ---------------------------------------------------------------------------
# Internal schemas
# ---------------------------------------------------------------------------

class ConsensusSchema(BaseModel):
    consensus_reached: bool = Field(
        description="True only if BOTH agents overwhelmingly agree on the same direction "
                    "with no major unresolved fundamental objections."
    )


# ---------------------------------------------------------------------------
# System Prompts — 5-agent roster
# ---------------------------------------------------------------------------

# ── Phase 1 Data Scouts (run on Flash — cheap, fast) ────────────────────────

FUNDAMENTAL_SCOUT_PROMPT = """\
You are a Fundamental Data Scout specializing in IHSG stocks for SWING TRADE analysis (1-3 month horizon).

PRIMARY MISSION — Calculate Fair Value:
  1. FAIR VALUE (most important): Your python system has pre-calculated the fair value.
     Locate the "FAIR VALUE REPORT" injected at the start of your data.
     Extract the value of "FAIR VALUE (weighted avg)". Label it clearly: "FAIR VALUE: Rp X,XXX".
  2. VALUATION VERDICT: Is the current price UNDERVALUED, FAIRLY VALUED, or OVERVALUED vs fair value?
     State the discount/premium as a percentage.
  3. SUPPORT METRICS: ROE trend (3yr), Net Margin trend (3yr), Debt/Equity, Dividend Yield.
  4. GROWTH CATALYST: One specific upcoming event (earnings, ex-dividend, contract) within 1-3 months.

RULES: Numbers ONLY. No vague statements. Rupiah prices must be explicit. Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs."""

CHARTIST_PROMPT = """\
You are a Technical Chartist specializing in IHSG swing trade entry/exit timing (1-3 month frame).

PRIMARY MISSION — Define the Trade Setup:
  1. ENTRY ZONE: Identify the nearest confirmed support level where price is likely to hold.
     State as a range: "ENTRY ZONE: Rp X,XXX – Rp Y,YYY"
     Justify with: MA50, MA200, historical pivot, or orderbook wall.
  2. TARGET PRICE: The nearest strong resistance level that would yield 3-10% gain from entry midpoint.
     State as: "TARGET: Rp Z,ZZZ (approx. X% from entry mid)"
  3. STOP-LOSS: The price level that would invalidate the bullish setup.
     State as: "STOP LOSS: Rp W,WWW (X% below entry mid)"
  4. TREND CONTEXT: Current short-term trend direction and key pattern (e.g., "consolidating above MA50",
     "approaching breakout from 6-week base", "bearish — below MA200").
  5. VOLUME SIGNAL: Is current volume confirming or denying the price move?

RULES: All prices in Rupiah. No opinions without a price number attached. Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs."""

SENTIMENT_PROMPT = """\
You are a Sentiment Specialist monitoring Stockbit social signal data for IHSG swing trade timing.

Analyze the raw stream/social JSON and extract:
  • Overall mood: BULLISH / NEUTRAL / BEARISH with a % confidence estimate
  • Dominant discussion theme (e.g., dividend rumour, earnings miss concern)
  • Volume anomaly: Is discussion volume abnormally high or low vs baseline?
  • Swing-trade timing signal: Is sentiment at EXTREME (contrarian opportunity) or trending with price?
  • Red flags: Any coordinated pump signals, insider-leak language, or panic patterns?

RULES: Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs. Be specific — note if sentiment is diverging from price action."""

# ── Phase 2 Debate Agents (run on Pro — only when reasoning needed) ──────────

BULL_SYSTEM_PROMPT_R1 = """\
You are a Senior Equity Analyst building the strongest possible swing trade BUY case (1-3 month horizon).

ROUND 1 OBJECTIVE — Build the Trade Thesis:
  1. FUNDAMENTAL FLOOR: Cite the fair value estimate and confirm current price is at a discount.
     If price is ABOVE fair value, you must explain why the momentum/catalyst still justifies entry.
  2. TECHNICAL ENTRY: Confirm the entry zone from Chartist data is a high-probability support.
     Cite the specific level (e.g., "MA50 at Rp 4,850 has held 3 times in 6 months").
  3. CATALYST: Name ONE specific event within 1-3 months that will drive the price to target.
  4. RISK/REWARD: State explicitly: "Entry Rp X → Target Rp Y → Stop Rp Z → R/R ratio: N:1"

RULES: Swing trade frame ONLY (1-3 months). No long-term narratives. Cite exact prices. Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs."""

BULL_SYSTEM_PROMPT_R2 = """\
You are a Senior Equity Analyst in Cross-Examination mode — swing trade frame.

ROUND 2 OBJECTIVE — Defend Entry Timing Against the Bear:
  ⛔ DO NOT repeat ANY price level, ratio, or argument from your Round 1 response.
  ✅ Attack the Bear's specific stop-loss / target / valuation arguments.
  ✅ If the Bear said the support will break, name a secondary support below it that limits downside.
  ✅ If the Bear challenged the catalyst, provide corroborating evidence or a fallback catalyst.
  ✅ Address whether the current price-to-fair-value gap is wide enough to absorb the Bear's risk scenario.

RULES: No repeated data. Attack specific Bear arguments. Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs."""

BEAR_SYSTEM_PROMPT_R1 = """\
You are a Forensic Financial Auditor building the strongest possible swing trade AVOID/SELL case.

ROUND 1 OBJECTIVE — Challenge the Trade Setup:
  1. OVERVALUATION CHECK: Is the current price above fair value? State the premium as a percentage.
     If it is, the swing trade entry has NO margin of safety — state this bluntly.
  2. TECHNICAL BREAKDOWN RISK: Is there a pattern (lower-highs, breakdown below MA50/MA200,
     bearish volume divergence) that makes the support level cited by the Bull unreliable?
     Cite exact price levels.
  3. CATALYST RISK: What could prevent the Bull's catalyst from materialising within 1-3 months?
  4. UNFAVOURABLE R/R: If the stop-loss is close to entry but resistance is far away, state the
     actual R/R ratio and explain why it makes the trade unattractive.

RULES: Cite exact prices to counter every Bull price level. Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs."""

BEAR_SYSTEM_PROMPT_R2 = """\
You are a Forensic Financial Auditor in Cross-Examination mode — swing trade frame.

ROUND 2 OBJECTIVE — Destroy the Bull's Swing Setup:
  ⛔ DO NOT repeat ANY price level, ratio, or argument from your Round 1 response.
  ✅ Dismantle the Bull's specific entry zone, target, or catalyst claims from Round 1.
  ✅ If the Bull cited MA50 as support, show prior instances where MA50 failed for this stock.
  ✅ If the Bull cited a fundamental floor, show if the floor has drifted lower with declining earnings.
  ✅ Present an alternative price scenario: "If support breaks, next support is Rp X — making
     the actual max loss Rp Y, not Rp Z as the Bull assumes."

RULES: No repeated data. Every counter-argument must cite a specific price. Max 800 tokens. Your response MUST be at least 3-4 technical paragraphs."""

# ── Adaptive nodes ───────────────────────────────────────────────────────────

CONSENSUS_PROMPT = """\
You are a Consensus Evaluator. Read the Bull and Bear arguments below.
Answer ONLY: do both agents overwhelmingly agree on the same investment direction
(e.g., both conclude HOLD or both conclude BUY) with NO major unresolved objections?

Return true only if consensus is genuine and unambiguous. Return false if there is
meaningful disagreement or if one side raised a critical unaddressed risk."""

STATE_CLEANER_PROMPT = """\
You are a Context Pruner for a swing trade debate. Compress the history below into:

BULL TRADE CASE (3-5 bullets — preserve ALL price numbers: entry zone, target, stop, fair value):
BEAR COUNTER-CASE (3-5 bullets — preserve ALL price numbers they challenged):
UNRESOLVED TENSION (1-2 sentences — the core price/timing disagreement):

Max 200 words. Every Rupiah price cited in the original MUST appear in the summary. Discard all filler."""

DEVILS_ADVOCATE_PROMPT = """\
You are the Devil's Advocate for IHSG swing trade analysis.
Formulate ONE specific macro or company-level risk scenario that could cause the
support level to break BEFORE the target is reached within 1-3 months.

Format: A single direct question under 60 words that names a specific price level.
Example: "If BI raises rates 50bps next month and foreign funds sell, could the
Rp 4,850 MA50 support break, triggering stops all the way to Rp 4,400?" """

# ── CIO Judge — Swing Trade Edition (Phase 4) ───────────────────────────────

CIO_SYSTEM_PROMPT = """\
You are the Chief Investment Officer specializing in IHSG Swing Trading (1-3 month horizon, 3-10% target).

YOUR MANDATE — Produce a Complete, Executable Trade Plan:

STEP 1 — FAIR VALUE (from Fundamental data):
  Extract the fair value price calculated by the Fundamental Scout.
  If current price is ABOVE fair value, you MUST flag this in weighted_reasoning and
  strongly consider a HOLD or AVOID rating — a negative margin of safety is the #1 swing trade killer.

STEP 2 — ENTRY PRICE RANGE (from Chartist data):
  Identify the high-probability accumulation zone (near support, below fair value when possible).
  Use format: "XXXX - YYYY" (e.g., "4800 - 4950").

STEP 3 — TARGET PRICE (synthesis):
  Set a realistic target that is:
  (a) 3-10% above the entry midpoint — not more, not less for this swing frame.
  (b) Below the nearest strong resistance level identified by the Chartist.

STEP 4 — STOP LOSS:
  Set just below the key support used for entry.
  If potential loss (entry to stop) > potential gain (entry to target), rate HOLD or AVOID.

STEP 5 — FINAL RATING RULES:
  • STRONG_BUY  : Price < Fair Value, R/R ≥ 2.0, clear catalyst, strong support confirmed.
  • BUY         : Price ≤ Fair Value, R/R ≥ 1.5, support holds.
  • HOLD        : Price near Fair Value OR R/R < 1.5 OR target < 3%.
  • AVOID       : Price > Fair Value (overvalued) OR R/R < 1.0 OR no clear catalyst.

STEP 6 — ADDRESS the Devil's Advocate scenario in your weighted_reasoning.
         If you cannot dismiss the DA scenario, lower your confidence score accordingly."""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def post_evaluator_router(
    state: DebateChamberState,
) -> Literal["devils_advocate", "state_cleaner"]:
    """
    Short-circuit: if consensus reached OR 2 rounds complete → go to CIO path.
    Otherwise → prune state and run another debate round.
    """
    if state.get("consensus_reached") or state["round_count"] >= 2:
        return "devils_advocate"
    return "state_cleaner"


# ---------------------------------------------------------------------------
# DebateChamber
# ---------------------------------------------------------------------------

BASE_URL = "https://exodus.stockbit.com"


class DebateChamber:
    """
    LangGraph multi-agent debate system for IHSG stock analysis.

    Graph topology
    ──────────────
    START ──fan-out──► fundamental ─┐
          ──fan-out──► chartist    ─┼──► synthesizer ──► bullish_analyst
          ──fan-out──► sentiment   ─┘                         │
                                                        bearish_auditor
                                                              │
                                                    consensus_evaluator
                                                         │         │
                                                  (agreed/r≥2)  (disagree)
                                                         │         │
                                                  devils_advocate  state_cleaner
                                                         │              │
                                                         │         bullish_analyst
                                                     cio_judge
                                                         │
                                                        END
    """

    def __init__(self, flash_llm=None, pro_llm=None, stockbit_client=None):
        self.flash_llm = flash_llm or get_flash_llm()
        self.pro_llm = pro_llm or get_pro_llm()
        self.stockbit_client = stockbit_client or StockbitApiClient()
        self.app = self._build_graph()

    # ── LLM & HTTP helpers ──────────────────────────────────────────────────

    @retry(
        wait=wait_exponential(min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_transient_error),
    )
    async def _invoke_llm(self, llm, messages):
        from datetime import datetime
        try:
            import pytz
            tz = pytz.timezone("Asia/Jakarta")
        except ImportError:
            from datetime import timezone, timedelta
            tz = timezone(timedelta(hours=7))

        current_date = datetime.now(tz).strftime("%Y-%m-%d")
        global_rules = f"""
GLOBAL RELIABILITY RULES (MANDATORY)
Current Date (Asia/Jakarta): {current_date}

1) TIME AWARENESS
- Treat any event date strictly relative to Current Date.
- If event_date < Current Date, label it as PAST_EVENT_NOT_CATALYST.
- Past events cannot be used as future catalysts for 1-3 month swing thesis.
- If date is ambiguous/unparseable, mark DATE_UNCERTAIN and reduce confidence.

2) NULL VS ZERO SEMANTICS
- "INSUFFICIENT_DATA", "N/A", missing, or unknown values must be represented as null, NEVER 0.
- Use 0 only when the true numeric value is explicitly zero in source data.
- Do not infer bankruptcy/zero-value from missing data.

3) CONSISTENCY CHECKS
- If verdict is AVOID or WAIT_AND_SEE due to missing/invalid core data, do not present active trade recommendation as final actionable call.
- You may provide a hypothetical setup only under a dedicated section `hypothetical_setup`.
- If two metrics conflict across sections (e.g., dividend yield), explicitly explain likely source difference (trailing/interim/forward) or mark NEEDS_RECONCILIATION.

4) OUTPUT DISCIPLINE
- Never fabricate dates, prices, or percentages.
- If critical fields are null, say so explicitly and lower confidence.
- Prioritize candor over completeness.
"""
        msgs = list(messages)
        for i, msg in enumerate(msgs):
            if getattr(msg, "type", "") == "system":
                msgs[i] = SystemMessage(content=f"{global_rules}\n\n{msg.content}")
                break
        return await llm.ainvoke(msgs)

    @retry(wait=wait_exponential(min=2, max=10), stop=stop_after_attempt(3))
    async def _fetch_url(self, url: str) -> dict | None:
        try:
            return await asyncio.to_thread(self.stockbit_client.get, url)
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            raise

    # ── Phase 1 — Parallel Data Nodes (all on Flash) ────────────────────────

    async def _fundamental_node(self, state: DebateChamberState) -> dict:
        ticker = state["ticker"]
        current_price = state.get("current_price", 0.0)
        logger.info(f"[Fundamental] Fetching for {ticker}")
        try:
            raw = await self._fetch_url(
                f"{BASE_URL}/keystats/ratio/v1/{ticker}?year_limit=10"
            )
            if not raw:
                return {"fundamental_data": "Data Unavailable"}
                
            report_str, fv_price = build_fair_value_report(raw, ticker, current_price)
            
            messages = [
                SystemMessage(content=FUNDAMENTAL_SCOUT_PROMPT),
                HumanMessage(content=f"{report_str}\n\n=== RAW API JSON ===\n{json.dumps(raw)[:10_000]}"),
            ]
            resp = await self._invoke_llm(self.flash_llm, messages)
            return {"fundamental_data": resp.content}
        except Exception as e:
            logger.error(f"[Fundamental] Error: {e}")
            return {"fundamental_data": "Data Unavailable (Error)"}

    async def _chartist_node(self, state: DebateChamberState) -> dict:
        ticker = state["ticker"]
        logger.info(f"[Chartist] Fetching for {ticker}")
        await asyncio.sleep(0.5)   # stagger to avoid burst rate-limit
        try:
            raw = await self._fetch_url(
                f"{BASE_URL}/company-price-feed/v2/orderbook/companies/{ticker}"
            )
            if not raw:
                return {"technical_data": "Data Unavailable"}
            messages = [
                SystemMessage(content=CHARTIST_PROMPT),
                HumanMessage(content=json.dumps(raw)[:10_000]),
            ]
            resp = await self._invoke_llm(self.flash_llm, messages)
            return {"technical_data": resp.content}
        except Exception as e:
            logger.error(f"[Chartist] Error: {e}")
            return {"technical_data": "Data Unavailable (Error)"}

    async def _sentiment_node(self, state: DebateChamberState) -> dict:
        ticker = state["ticker"]
        logger.info(f"[Sentiment] Fetching for {ticker}")
        await asyncio.sleep(1.0)   # stagger to avoid burst rate-limit
        try:
            raw = await self._fetch_url(
                f"{BASE_URL}/stream/v3/symbol/{ticker}/pinned"
            )
            if not raw:
                return {"sentiment_data": "Data Unavailable"}
            messages = [
                SystemMessage(content=SENTIMENT_PROMPT),
                HumanMessage(content=json.dumps(raw)[:10_000]),
            ]
            resp = await self._invoke_llm(self.flash_llm, messages)
            return {"sentiment_data": resp.content}
        except Exception as e:
            logger.error(f"[Sentiment] Error: {e}")
            return {"sentiment_data": "Data Unavailable (Error)"}

    async def _synthesizer_node(self, state: DebateChamberState) -> dict:
        """
        Fan-in: merge the three parallel data briefs into one context string.
        Also runs the Margin-of-Safety pre-check and injects any warnings
        so that debate agents are immediately aware of overvaluation risk.
        """
        logger.info("[Synthesizer] Merging parallel data + margin-of-safety check")
        f = state.get("fundamental_data", "Missing")
        t = state.get("technical_data", "Missing")
        s = state.get("sentiment_data", "Missing")
        current_price = state.get("current_price", 0.0)

        raw = (
            f"=== FUNDAMENTALS ===\n{f}\n\n"
            f"=== TECHNICALS ===\n{t}\n\n"
            f"=== SENTIMENT ===\n{s}"
        )

        # ── Margin-of-Safety pre-check (pure Python, zero token cost) ──────
        # We do a lightweight parse of the fundamental brief to extract
        # fair_value if the Scout formatted it correctly ("FAIR VALUE: Rp X,XXX").
        fair_value_estimate = 0.0
        for line in f.splitlines():
            if "FAIR VALUE" in line.upper():
                try:
                    price_str = line.split(":")[-1].strip().replace("Rp", "").replace(",", "").strip()
                    fair_value_estimate = float(price_str.split()[0])
                    break
                except Exception:
                    pass

        if fair_value_estimate > 0 and current_price > 0:
            validation = validate_swing_targets(
                current_price=current_price,
                fair_value=fair_value_estimate,
                target_price=0.0,     # not known yet — only overvaluation checked here
                entry_price_range="0 - 0",
                stop_loss=0.0,
            )
            if not validation["is_valid"]:
                raw = (
                    f"[🚨 MARGIN-OF-SAFETY ALERT — Read Before Debating]\n"
                    f"{validation['warning_text']}\n"
                    f"Current Price: Rp {current_price:,.0f} | "
                    f"Estimated Fair Value: Rp {fair_value_estimate:,.0f}\n"
                    f"{'─' * 60}\n\n" + raw
                )
                logger.warning(f"[Synthesizer] Overvaluation detected: {current_price} > {fair_value_estimate}")

        if "Unavailable" in raw or "Missing" in raw:
            raw = (
                "[⚠️ WARNING: One or more data sources failed. "
                "Analysts must caveat conclusions accordingly.]\n\n" + raw
            )

        return {"raw_data": raw}

    # ── Phase 2 — Debate Nodes (on Pro) ─────────────────────────────────────

    async def _bullish_node(self, state: DebateChamberState) -> dict:
        ticker = state["ticker"]
        rc = state["round_count"]
        logger.info(f"[Bull] Round {rc + 1} for {ticker}")

        prompt = BULL_SYSTEM_PROMPT_R1 if rc == 0 else BULL_SYSTEM_PROMPT_R2

        content_parts = [f"Ticker: {ticker}\n\nSynthesized Market Data:\n{state['raw_data']}"]

        if rc > 0:
            # Send pruned history — prevents state bloat
            hist = "\n".join(
                f"[{m.role.upper()} R{m.round_num}]: {m.content}"
                for m in state["debate_history"]
            )
            content_parts.append(f"\n\nDebate History (may be pruned summary):\n{hist}")

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="\n".join(content_parts)),
        ]
        resp = await self._invoke_llm(self.pro_llm, messages)
        msg = DebateMessage(role="bull", content=resp.content, round_num=rc + 1)
        return {"debate_history": [msg]}

    async def _bearish_node(self, state: DebateChamberState) -> dict:
        ticker = state["ticker"]
        rc = state["round_count"]
        logger.info(f"[Bear] Round {rc + 1} for {ticker}")

        prompt = BEAR_SYSTEM_PROMPT_R1 if rc == 0 else BEAR_SYSTEM_PROMPT_R2

        # Always surface the latest Bull argument for the Bear to attack
        bull_args = [m.content for m in state["debate_history"] if m.role == "bull"]
        last_bull = bull_args[-1] if bull_args else "(no bull argument yet)"

        content_parts = [
            f"Ticker: {ticker}\n\nSynthesized Market Data:\n{state['raw_data']}",
            f"\n\nBull's argument to challenge:\n{last_bull}",
        ]

        if rc > 0:
            bear_args = [m.content for m in state["debate_history"] if m.role == "bear"]
            if bear_args:
                content_parts.append(
                    f"\n\nYour own Round 1 argument (DO NOT repeat this):\n{bear_args[-1]}"
                )

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="\n".join(content_parts)),
        ]
        resp = await self._invoke_llm(self.pro_llm, messages)
        new_rc = rc + 1
        msg = DebateMessage(role="bear", content=resp.content, round_num=new_rc)
        return {"debate_history": [msg], "round_count": new_rc}

    # ── Phase 3 — Adaptive Logic ─────────────────────────────────────────────

    async def _consensus_evaluator_node(self, state: DebateChamberState) -> dict:
        """
        Short-circuit check: if Bull & Bear essentially agree after Round 1,
        skip Round 2 and proceed directly to Devil's Advocate → CIO.
        Uses Flash (cheap) — no Pro tokens wasted here.
        """
        logger.info("[Consensus] Evaluating agreement")
        # Only inspect the two most recent messages (latest round)
        recent = [
            m for m in state["debate_history"]
            if m.round_num == state["round_count"]
        ]
        hist = "\n".join(f"[{m.role.upper()}]: {m.content}" for m in recent)

        messages = [
            SystemMessage(content=CONSENSUS_PROMPT),
            HumanMessage(content=hist),
        ]
        structured_llm = self.flash_llm.with_structured_output(ConsensusSchema)
        try:
            res: ConsensusSchema = await self._invoke_llm(structured_llm, messages)
            agreed = res.consensus_reached
        except Exception as e:
            logger.warning(f"[Consensus] Structured output failed ({e}); defaulting to False")
            agreed = False

        logger.info(f"[Consensus] Result: {agreed}")
        return {"consensus_reached": agreed}

    async def _state_cleaner_node(self, state: DebateChamberState) -> dict:
        """
        Context pruner: summarise the full debate_history into a dense
        3-section brief before Round 2 begins.  Prevents context-window bloat.
        The sentinel round_num=-1 triggers the history_updater to *replace*
        rather than append.
        """
        logger.info("[State Cleaner] Pruning context window")
        hist = "\n".join(
            f"[{m.role.upper()} R{m.round_num}]: {m.content}"
            for m in state["debate_history"]
        )
        messages = [
            SystemMessage(content=STATE_CLEANER_PROMPT),
            HumanMessage(content=hist),
        ]
        resp = await self._invoke_llm(self.flash_llm, messages)
        sentinel = DebateMessage(role="system", content="__REPLACE__", round_num=-1)
        summary_msg = DebateMessage(role="system", content=resp.content, round_num=0)
        return {"debate_history": [sentinel, summary_msg]}

    async def _devils_advocate_node(self, state: DebateChamberState) -> dict:
        """
        Injects a worst-case macro challenge before the CIO decides.
        Keeps the CIO from rubber-stamping the winning side.
        """
        logger.info("[Devil's Advocate] Injecting adversarial scenario")
        hist = "\n".join(
            f"[{m.role.upper()} R{m.round_num}]: {m.content}"
            for m in state["debate_history"]
        )
        messages = [
            SystemMessage(content=DEVILS_ADVOCATE_PROMPT),
            HumanMessage(content=f"Data:\n{state['raw_data']}\n\nDebate:\n{hist}"),
        ]
        resp = await self._invoke_llm(self.flash_llm, messages)
        msg = DebateMessage(
            role="devils_advocate",
            content=resp.content,
            round_num=state["round_count"] + 1,
        )
        return {
            "debate_history": [msg],
            "devils_advocate_question": resp.content,
        }

    # ── Phase 4 — CIO Judge ──────────────────────────────────────────────────

    async def _cio_judge_node(self, state: DebateChamberState) -> dict:
        """
        Weighted synthesis verdict — Swing Trade edition.
        Outputs a Pydantic-validated CIOVerdict with concrete price levels.
        The model_validator on CIOVerdict auto-computes expected_return,
        risk_reward_ratio, is_overvalued, and wait_and_see — no LLM arithmetic needed.
        """
        ticker = state["ticker"]
        current_price = state.get("current_price", 0.0)
        logger.info(f"[CIO] Deliberating on {ticker} (current price: {current_price:,.0f})")

        hist = "\n".join(
            f"[{m.role.upper()} R{m.round_num}]: {m.content}"
            for m in state["debate_history"]
        )
        user_content = (
            f"Ticker: {ticker}\n"
            f"Current Market Price: Rp {current_price:,.0f}\n\n"
            f"Synthesized Market Data:\n{state['raw_data']}\n\n"
            f"Full Debate Transcript:\n{hist}\n\n"
            f"Devil's Advocate Challenge:\n{state.get('devils_advocate_question', 'N/A')}"
        )

        messages = [
            SystemMessage(content=CIO_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        structured_llm = self.pro_llm.with_structured_output(CIOVerdict)

        try:
            verdict: CIOVerdict = await self._invoke_llm(structured_llm, messages)
            # Inject current_price so model_validator can run is_overvalued check
            verdict.current_price = current_price
            # Re-run validator with current_price now populated
            verdict = CIOVerdict(**verdict.model_dump())
            verdict_json = verdict.model_dump_json()
        except Exception as e:
            logger.warning(f"[CIO] Structured output failed ({e}); attempting manual parse")
            resp = await self._invoke_llm(self.pro_llm, messages)
            try:
                parsed = json.loads(resp.content)
                parsed["current_price"] = current_price
                verdict_json = CIOVerdict(**parsed).model_dump_json()
            except Exception:
                verdict_json = CIOVerdict(
                    ticker=ticker,
                    summary=resp.content,
                    confidence=0.0,
                    current_price=current_price,
                ).model_dump_json()

        logger.info(f"[CIO] Verdict delivered for {ticker}")
        return {"final_verdict": verdict_json}

    # ── Graph Assembly ───────────────────────────────────────────────────────

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(DebateChamberState)

        # Register nodes
        graph.add_node("fundamental",         self._fundamental_node)
        graph.add_node("chartist",            self._chartist_node)
        graph.add_node("sentiment",           self._sentiment_node)
        graph.add_node("synthesizer",         self._synthesizer_node)
        graph.add_node("bullish_analyst",     self._bullish_node)
        graph.add_node("bearish_auditor",     self._bearish_node)
        graph.add_node("consensus_evaluator", self._consensus_evaluator_node)
        graph.add_node("state_cleaner",       self._state_cleaner_node)
        graph.add_node("devils_advocate",     self._devils_advocate_node)
        graph.add_node("cio_judge",           self._cio_judge_node)

        # Phase 1: Parallel fan-out from START
        graph.add_edge(START, "fundamental")
        graph.add_edge(START, "chartist")
        graph.add_edge(START, "sentiment")

        # Phase 1: Fan-in to synthesizer
        graph.add_edge("fundamental", "synthesizer")
        graph.add_edge("chartist",    "synthesizer")
        graph.add_edge("sentiment",   "synthesizer")

        # Phase 2: Debate cycle
        graph.add_edge("synthesizer",     "bullish_analyst")
        graph.add_edge("bullish_analyst", "bearish_auditor")
        graph.add_edge("bearish_auditor", "consensus_evaluator")

        # Phase 3: Adaptive routing
        graph.add_conditional_edges("consensus_evaluator", post_evaluator_router)
        graph.add_edge("state_cleaner", "bullish_analyst")   # loops back for R2

        # Phase 4: Conclusion path
        graph.add_edge("devils_advocate", "cio_judge")
        graph.add_edge("cio_judge",       END)

        return graph.compile()

    # ── Public API ───────────────────────────────────────────────────────────

    async def run(self, ticker: str, current_price: float = 0.0) -> dict:
        """
        Execute the full swing-trade debate pipeline for a given IHSG ticker.

        Args:
            ticker        : IHSG stock code, e.g. "BBRI"
            current_price : Last traded price in IDR (e.g. 4875.0).
                            Used by the Synthesizer for margin-of-safety checks
                            and by the CIO for is_overvalued auto-flagging.
                            Pass 0.0 to skip price-level validation.

        Returns:
            The final LangGraph state dict.
            Access the verdict via: json.loads(result["final_verdict"])
            For the Svelte trade card: CIOVerdict(**json.loads(...)).to_trade_card()
        """
        initial_state: DebateChamberState = {
            "ticker": ticker,
            "current_price": current_price,
            "fundamental_data": "",
            "technical_data": "",
            "sentiment_data": "",
            "raw_data": "",
            "debate_history": [],
            "round_count": 0,
            "consensus_reached": False,
            "devils_advocate_question": "",
            "final_verdict": "",
            "error": None,
        }
        logger.info(f"[DebateChamber] ▶ Starting swing-trade pipeline for {ticker} @ Rp {current_price:,.0f}")
        result = await self.app.ainvoke(initial_state)
        logger.info(f"[DebateChamber] ✅ Pipeline complete for {ticker}")
        return result
