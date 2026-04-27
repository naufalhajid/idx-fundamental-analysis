import pytest
import asyncio
from unittest.mock import MagicMock

# Shared fixtures for the test suite

@pytest.fixture
def dummy_chamber():
    """Returns a DebateChamber instance with all external dependencies mocked."""
    # We patch __init__ so it doesn't try to instantiate real LLMs/Clients
    from services.debate_chamber import DebateChamber
    
    class MockChamber(DebateChamber):
        def __init__(self):
            self.flash_llm = MagicMock()
            self.pro_llm = MagicMock()
            self.stockbit_client = MagicMock()
            self.app = MagicMock()
            self.model_tier_map = {}
            
    return MockChamber()
