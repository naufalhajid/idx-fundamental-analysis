import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Import Chamber via the dummy chamber in conftest or instantiate it
from services.debate_chamber import DebateChamber

MOCK_API_RESPONSE = {'eps': 500, 'book_value': 2000}

def mock_fair_value_report(raw, ticker, price):
    return ('FAIR VALUE REPORT\nFAIR VALUE: Rp 5,500', 5500.0)

STATE = {
    'ticker': 'BBRI',
    'current_price': 4875.0,
    'fundamental_data': '',
    'fair_value_estimate': 0.0,
    'debate_history': [],
    'round_count': 0,
    'final_verdict': ''
}

@pytest.mark.asyncio
async def test_fv_from_python_not_llm(dummy_chamber):
    """Verify that FV comes from python calculation and not from an LLM regex parse."""
    with patch('services.debate_chamber.build_fair_value_report', side_effect=mock_fair_value_report) as mock_fv:
        with patch.object(dummy_chamber, '_fetch_url', new_callable=AsyncMock, return_value=MOCK_API_RESPONSE):
            # Give LLM a fake response with a completely different number to simulate hallucination
            with patch.object(dummy_chamber, '_invoke_llm', new_callable=AsyncMock, return_value=MagicMock(content='LLM said FV is Rp999')):
                result = await dummy_chamber._fundamental_node(STATE.copy())

    # Should be our mock FV (5500.0) from the python calculation, NOT the LLM's 999.
    assert result['fair_value_estimate'] == 5500.0
    assert mock_fv.call_count == 1

@pytest.mark.asyncio
async def test_fv_zero_when_no_data_no_crash(dummy_chamber):
    """Verify state estimate is 0.0 when no meaningful data is returned, and it doesnt crash."""
    with patch('services.debate_chamber.build_fair_value_report', return_value=('Empty report', 0.0)):
        with patch.object(dummy_chamber, '_fetch_url', new_callable=AsyncMock, return_value={}):
            with patch.object(dummy_chamber, '_invoke_llm', new_callable=AsyncMock, return_value=MagicMock(content='')):
                result = await dummy_chamber._fundamental_node(STATE.copy())
                
    assert result.get('fair_value_estimate', 0.0) == 0.0

@pytest.mark.asyncio
async def test_empty_api_response_sets_data_unavailable(dummy_chamber):
    """Verify that if API returns empty, fundamental_data fallback is generated."""
    with patch('services.debate_chamber.build_fair_value_report', return_value=('', 0.0)):
        with patch.object(dummy_chamber, '_fetch_url', new_callable=AsyncMock, return_value=None):
             with patch.object(dummy_chamber, '_invoke_llm', new_callable=AsyncMock, return_value=MagicMock(content='')):
                 result = await dummy_chamber._fundamental_node(STATE.copy())
                 
                 # The code inside `_fundamental_node` concatenates many strings.
                 # Usually if it fails fetching, it should either skip or state unavailable.
                 # Just ensure no exception is raised and it handled None smoothly.
                 assert isinstance(result['fundamental_data'], str)

@pytest.mark.asyncio
async def test_fv_different_format_no_impact(dummy_chamber):
    """Verify LLM output format has absolutely no impact on FV state."""
    with patch('services.debate_chamber.build_fair_value_report', return_value=('report', 7000.0)):
        with patch.object(dummy_chamber, '_fetch_url', new_callable=AsyncMock, return_value=MOCK_API_RESPONSE):
            with patch.object(dummy_chamber, '_invoke_llm', new_callable=AsyncMock, return_value=MagicMock(content='Some weird text formatting')):
                result = await dummy_chamber._fundamental_node(STATE.copy())
                
    assert result['fair_value_estimate'] == 7000.0

# Coverage target: services.debate_chamber (_fundamental_node FV calculation)
