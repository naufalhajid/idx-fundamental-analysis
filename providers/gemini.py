import os

from langchain_google_genai import ChatGoogleGenerativeAI

from core.settings import settings


def _get_api_key() -> str:
    """Resolve Gemini API key.

    Settings is cached via @lru_cache at import time — before load_dotenv()
    runs in entry-point scripts. Fall back to os.environ which IS populated
    by the time factory functions are called at runtime.
    """

    return settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")


def get_flash_llm() -> ChatGoogleGenerativeAI:
    """Create a Gemini Flash instance — fast and cheap, for data extraction/summarization."""

    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_FLASH_MODEL,
        google_api_key=_get_api_key(),
        temperature=0.1,
        max_output_tokens=2048,
    )


def get_pro_llm() -> ChatGoogleGenerativeAI:
    """Create a Gemini Pro instance — high reasoning capability, for debate and judgement."""

    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_PRO_MODEL,
        google_api_key=_get_api_key(),
        temperature=0.7,
        max_output_tokens=4096,
    )
