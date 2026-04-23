import asyncio
import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from providers.gemini import get_flash_llm, get_pro_llm
from schemas.debate import CIOVerdict, DebateChamberState, DebateMessage
from services.stockbit_api_client import StockbitApiClient
from utils.logger_config import logger


def _is_transient_error(exc: BaseException) -> bool:
    """Only retry on transient API errors (429 rate-limit, 503 server error).

    Non-transient errors (404 model not found, 400 bad request, etc.)
    should fail immediately — retrying won't help.
    """

    error_str = str(exc).lower()
    return "429" in error_str or "503" in error_str or "resource exhausted" in error_str


# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

DATA_SCOUT_SYSTEM_PROMPT = """\
You are a Financial Data Scout. Analyze raw financial data from the Stockbit API \
and produce a concise, structured summary.

Cover these sections:
1. Key Valuation (PE, PBV, EV/EBITDA)
2. Profitability (ROE, ROA, margins)
3. Growth (revenue, profit YoY)
4. Solvency (DER, current ratio, Altman Z-Score)
5. Dividend (yield, payout ratio)
6. Price Performance (52w high/low, YTD)
7. Market Sentiment (brief summary of stream data)

Rules:
- Stay under 500 tokens
- Numbers and facts ONLY — no opinions
- Use plain text with clear section headers"""

BULL_SYSTEM_PROMPT = """\
You are a Senior Equity Analyst at a top-tier investment bank. \
Build the strongest possible BUY case for this stock.

Rules:
- Use ONLY the provided fundamental data — do NOT fabricate numbers
- Be specific: cite PE ratios, growth rates, margins, dividend yields
- Highlight competitive advantages and catalysts
- If this is NOT the first round, you MUST directly counter the Bear's latest argument
- Keep your argument under 300 tokens
- Be persuasive but intellectually honest"""

BEAR_SYSTEM_PROMPT = """\
You are a Forensic Financial Auditor. Your job is to find every risk, \
red flag, and weakness in this stock.

Rules:
- Read the Bull's latest argument and systematically dismantle it
- Use the fundamental data to support your SELL/AVOID case
- Focus on: overvaluation, debt risks, declining margins, governance issues, macro headwinds
- Be specific with numbers — cite from the data provided
- Keep your argument under 300 tokens
- Be ruthless but fair — do NOT fabricate data"""

CIO_SYSTEM_PROMPT = """\
You are the Chief Investment Officer. You have observed a structured debate \
between a Bullish Analyst and a Bearish Auditor about a specific stock.

Analyze both sides of the debate and the underlying fundamental data. \
Produce a balanced, final investment verdict.

Your output MUST be a valid JSON object with exactly these fields:
- ticker (string): the stock ticker
- rating (string): one of "STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"
- confidence (float): between 0.0 and 1.0
- key_catalysts (list of strings): top 3 reasons supporting the stock
- key_risks (list of strings): top 3 risks threatening the stock
- summary (string): 2-3 sentence final verdict paragraph

Be balanced. Consider both sides. Base your confidence on how convincing each side was."""


# ---------------------------------------------------------------------------
# Router Functions (pure — no side effects)
# ---------------------------------------------------------------------------


def debate_router(state: DebateChamberState) -> Literal["bullish_analyst", "cio_judge"]:
    """Route after Bear node: continue debating or go to final judgement.

    round_count is incremented by Bear AFTER its argument:
        - round_count=0 → first cycle not started yet
        - round_count=1 → first cycle complete, continue
        - round_count=2 → second cycle complete, go to CIO
    """

    if state["round_count"] < 2:
        return "bullish_analyst"
    return "cio_judge"


def data_scout_router(state: DebateChamberState) -> Literal["bullish_analyst", "__end__"]:
    """Route after Data Scout: proceed to debate or abort on error."""

    if state.get("error") is not None:
        return "__end__"
    return "bullish_analyst"


# ---------------------------------------------------------------------------
# Debate Chamber
# ---------------------------------------------------------------------------

BASE_URL = "https://exodus.stockbit.com"


class DebateChamber:
    """LangGraph-based adversarial debate system for IDX stock analysis.

    Architecture:
        Data Scout (Flash) → Bull (Pro) ↔ Bear (Pro) × 2 rounds → CIO Judge (Pro)

    LLM instances are created once in __init__ and reused across all node
    invocations for optimal HTTP connection pooling.
    """

    def __init__(self, flash_llm=None, pro_llm=None, stockbit_client=None):
        self.flash_llm = flash_llm or get_flash_llm()
        self.pro_llm = pro_llm or get_pro_llm()
        self.stockbit_client = stockbit_client or StockbitApiClient()
        self.app = self._build_graph()

    # -- LLM invocation with retry for transient Gemini API errors (429/503)

    @retry(
        wait=wait_exponential(min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_transient_error),
    )
    async def _invoke_llm(self, llm, messages):
        """Invoke any LangChain-compatible LLM/Runnable with exponential backoff retry.

        Only retries on transient errors (429, 503). Permanent errors (404, 400)
        fail immediately.
        """

        return await llm.ainvoke(messages)

    # -- Node: Data Scout (Gemini Flash) -----------------------------------

    async def _data_scout_node(self, state: DebateChamberState) -> dict:
        """Fetch fundamental data from Stockbit and summarize via Gemini Flash.

        Raw scraping objects are local variables — they go out of scope
        naturally after this function returns. No gc.collect() needed because
        LangGraph state only stores the compressed summary string.
        """

        ticker = state["ticker"]
        logger.info(f"[Data Scout] Fetching data for {ticker}")

        key_stats_url = f"{BASE_URL}/keystats/ratio/v1/{ticker}?year_limit=10"
        price_url = f"{BASE_URL}/company-price-feed/v2/orderbook/companies/{ticker}"
        sentiment_url = f"{BASE_URL}/stream/v3/symbol/{ticker}/pinned"

        # Wrap sync Stockbit API calls to avoid blocking the event loop
        raw_key_stats = await asyncio.to_thread(self.stockbit_client.get, key_stats_url)
        raw_price = await asyncio.to_thread(self.stockbit_client.get, price_url)
        raw_sentiment = await asyncio.to_thread(self.stockbit_client.get, sentiment_url)

        if not raw_key_stats and not raw_price:
            logger.error(f"[Data Scout] No data returned for {ticker}")
            return {"error": f"Failed to fetch data for {ticker}. Both key stats and price returned empty."}

        # Compose raw payload for LLM summarization
        raw_payload = json.dumps(
            {"key_stats": raw_key_stats, "price": raw_price, "sentiment": raw_sentiment},
            default=str,
        )

        # Truncate to prevent token overflow (Flash context is large but we want speed)
        if len(raw_payload) > 15000:
            raw_payload = raw_payload[:15000] + "...[truncated]"

        messages = [
            SystemMessage(content=DATA_SCOUT_SYSTEM_PROMPT),
            HumanMessage(content=f"Ticker: {ticker}\n\nRaw Data:\n{raw_payload}"),
        ]

        response = await self._invoke_llm(self.flash_llm, messages)
        logger.info(f"[Data Scout] Summary ready for {ticker} ({len(response.content)} chars)")

        return {"raw_data": response.content}

    # -- Node: Bullish Analyst (Gemini Pro) --------------------------------

    async def _bullish_analyst_node(self, state: DebateChamberState) -> dict:
        """Build the strongest possible BUY case.

        On round > 0, reads and counters the last Bear argument.
        """

        ticker = state["ticker"]
        round_count = state["round_count"]
        logger.info(f"[Bull] Round {round_count + 1} for {ticker}")

        user_content = f"Ticker: {ticker}\n\nFundamental Data:\n{state['raw_data']}"

        # Counter the Bear's last argument if this is not the first round
        if round_count > 0:
            bear_args = [m for m in state["debate_history"] if m.role == "bear"]
            if bear_args:
                user_content += f"\n\n--- Bear's Last Argument (you MUST counter this) ---\n{bear_args[-1].content}"

        messages = [
            SystemMessage(content=BULL_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        response = await self._invoke_llm(self.pro_llm, messages)

        message = DebateMessage(role="bull", content=response.content, round_num=round_count + 1)
        logger.info(f"[Bull] Argument delivered ({len(response.content)} chars)")

        return {"debate_history": [message]}

    # -- Node: Bearish Auditor (Gemini Pro) --------------------------------

    async def _bearish_auditor_node(self, state: DebateChamberState) -> dict:
        """Find every risk and weakness. Increments round_count AFTER argument.

        round_count semantics:
            - Incremented here (after Bear's rebuttal) = 1 full Bull↔Bear cycle
            - Router checks AFTER this increment
        """

        ticker = state["ticker"]
        round_count = state["round_count"]
        logger.info(f"[Bear] Round {round_count + 1} for {ticker}")

        # Get the last Bull argument to dismantle
        bull_args = [m for m in state["debate_history"] if m.role == "bull"]
        last_bull = bull_args[-1].content if bull_args else ""

        user_content = (
            f"Ticker: {ticker}\n\n"
            f"Fundamental Data:\n{state['raw_data']}\n\n"
            f"--- Bull's Argument (dismantle this) ---\n{last_bull}"
        )

        messages = [
            SystemMessage(content=BEAR_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        response = await self._invoke_llm(self.pro_llm, messages)

        new_round_count = round_count + 1
        message = DebateMessage(role="bear", content=response.content, round_num=new_round_count)
        logger.info(f"[Bear] Argument delivered, round_count → {new_round_count}")

        return {"debate_history": [message], "round_count": new_round_count}

    # -- Node: CIO Judge (Gemini Pro + Structured Output) ------------------

    async def _cio_judge_node(self, state: DebateChamberState) -> dict:
        """Deliver final structured verdict using with_structured_output().

        Uses LangChain's with_structured_output(CIOVerdict) for type-safe
        JSON parsing. Falls back to raw response if structured parsing fails.
        """

        ticker = state["ticker"]
        logger.info(f"[CIO] Judging debate for {ticker}")

        # Format debate history for the judge
        debate_text = ""
        for msg in state["debate_history"]:
            label = {"bull": "🐂 Bullish Analyst", "bear": "🐻 Bearish Auditor"}
            debate_text += f"\n### {label.get(msg.role, msg.role)} (Round {msg.round_num})\n{msg.content}\n"

        user_content = (
            f"Ticker: {ticker}\n\n"
            f"Fundamental Data Summary:\n{state['raw_data']}\n\n"
            f"--- Full Debate Transcript ---\n{debate_text}"
        )

        messages = [
            SystemMessage(content=CIO_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        # Primary: structured output via with_structured_output()
        structured_llm = self.pro_llm.with_structured_output(CIOVerdict)

        try:
            verdict: CIOVerdict = await self._invoke_llm(structured_llm, messages)
            verdict_json = verdict.model_dump_json()
        except Exception as e:
            logger.warning(f"[CIO] Structured output failed ({e}), falling back to raw JSON parse")
            # Fallback: ask the LLM directly and attempt manual parse
            response = await self._invoke_llm(self.pro_llm, messages)
            try:
                parsed = json.loads(response.content)
                verdict = CIOVerdict(**parsed)
                verdict_json = verdict.model_dump_json()
            except (json.JSONDecodeError, Exception) as parse_err:
                logger.error(f"[CIO] JSON fallback also failed ({parse_err}), using raw content")
                # Last resort: wrap raw content in a default verdict
                verdict = CIOVerdict(ticker=ticker, summary=response.content)
                verdict_json = verdict.model_dump_json()

        logger.info(f"[CIO] Verdict delivered for {ticker}")
        return {"final_verdict": verdict_json}

    # -- Graph Assembly ----------------------------------------------------

    def _build_graph(self) -> StateGraph:
        """Assemble and compile the LangGraph state machine.

        Flow:
            START → data_scout →[error?]→ END
                                →[ok]→ bullish_analyst → bearish_auditor
                                            ↑               ↓
                                            └──[round<2]────┘
                                                [round==2]→ cio_judge → END
        """

        graph = StateGraph(DebateChamberState)

        graph.add_node("data_scout", self._data_scout_node)
        graph.add_node("bullish_analyst", self._bullish_analyst_node)
        graph.add_node("bearish_auditor", self._bearish_auditor_node)
        graph.add_node("cio_judge", self._cio_judge_node)

        graph.add_edge(START, "data_scout")
        graph.add_conditional_edges("data_scout", data_scout_router)
        graph.add_edge("bullish_analyst", "bearish_auditor")
        graph.add_conditional_edges("bearish_auditor", debate_router)
        graph.add_edge("cio_judge", END)

        return graph.compile()

    # -- Public API --------------------------------------------------------

    async def run(self, ticker: str) -> dict:
        """Run a complete debate for a single ticker.

        Creates a fresh state per ticker — no history leakage between runs.

        Returns:
            The final LangGraph state dict with keys:
            ticker, raw_data, debate_history, round_count, final_verdict, error
        """

        initial_state: DebateChamberState = {
            "ticker": ticker,
            "raw_data": "",
            "debate_history": [],
            "round_count": 0,
            "final_verdict": "",
            "error": None,
        }

        logger.info(f"[DebateChamber] Starting debate for {ticker}")
        result = await self.app.ainvoke(initial_state)
        logger.info(f"[DebateChamber] Debate complete for {ticker}")

        return result
