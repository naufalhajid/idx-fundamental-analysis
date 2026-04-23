import operator
from typing import Annotated, Literal, TypedDict

from pydantic import Field

from schemas import BaseDataClass


class DebateMessage(BaseDataClass):
    """Single argument in the stock debate chamber."""

    role: Literal["scout", "bull", "bear"] = "scout"
    content: str = ""
    round_num: int = 0


class CIOVerdict(BaseDataClass):
    """Structured output from the CIO Judge — used with LangChain's with_structured_output()."""

    ticker: str = ""
    rating: Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"] = "HOLD"
    confidence: float = 0.0
    key_catalysts: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    summary: str = ""


class DebateChamberState(TypedDict):
    """LangGraph state for the Stock Debate Chamber.

    Reducers:
        - debate_history: operator.add (append-only list)
        - All other fields: replace (default LangGraph behavior)
    """

    ticker: str
    raw_data: str
    debate_history: Annotated[list[DebateMessage], operator.add]
    round_count: int
    final_verdict: str
    error: str | None
