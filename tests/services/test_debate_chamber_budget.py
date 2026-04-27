import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.debate_chamber import DebateChamber
from core.budget import BudgetExhaustedError

# Mock LLM that fails `fail_count` times before succeeding
def make_flaky_llm(fail_count=2):
    call_count = {'n': 0}
    async def ainvoke(msgs):
        call_count['n'] += 1
        if call_count['n'] <= fail_count:
            raise Exception('503 resource exhausted')
        return MagicMock(content='ok')
    
    llm = MagicMock()
    llm.ainvoke = ainvoke
    llm.model_name = 'gemini-pro' # Ensure it does not crash on model checking
    return llm

@pytest.mark.asyncio
async def test_budget_charged_once_on_retry():
    """Verify budget is incremented exactly once even if LLM fails and is retried."""
    chamber = DebateChamber()
    flaky = make_flaky_llm(fail_count=2)

    with patch('services.debate_chamber.check_and_increment_pro_budget', new_callable=AsyncMock) as mock_budget:
        with patch.object(chamber, '_classify_llm_tier', return_value='pro'):
            # The retry loops internally due to tenacious/backoff
            resp = await chamber._invoke_llm(flaky, [])
            
    assert mock_budget.call_count == 1
    assert resp.content == 'ok'

@pytest.mark.asyncio
async def test_budget_charged_once_on_success():
    """Verify budget is incremented exactly once when LLM successfully replies immediately."""
    chamber = DebateChamber()
    good_llm = make_flaky_llm(fail_count=0)

    with patch('services.debate_chamber.check_and_increment_pro_budget', new_callable=AsyncMock) as mock_budget:
        with patch.object(chamber, '_classify_llm_tier', return_value='pro'):
            resp = await chamber._invoke_llm(good_llm, [])
            
    assert mock_budget.call_count == 1
    assert resp.content == 'ok'

@pytest.mark.asyncio
async def test_budget_exhausted_not_retried():
    """Verify that a BudgetExhaustedError avoids retries and propagates immediately."""
    chamber = DebateChamber()
    
    with patch('services.debate_chamber.check_and_increment_pro_budget', side_effect=BudgetExhaustedError('exhausted')):
        with pytest.raises(BudgetExhaustedError):
            mock_llm = MagicMock(model='gemini-pro')
            mock_llm.ainvoke = AsyncMock()
            await chamber._invoke_llm(mock_llm, [])

@pytest.mark.asyncio
async def test_flash_budget_charged():
    """Verify that non-Pro (Flash) calls charge the Flash budget instead of Pro budget."""
    chamber = DebateChamber()
    good_llm = make_flaky_llm(fail_count=0)

    with patch('services.debate_chamber.check_and_increment_flash_budget', new_callable=AsyncMock) as mock_flash_budget:
        with patch.object(chamber, '_classify_llm_tier', return_value='flash'):
            await chamber._invoke_llm(good_llm, [])
            
    assert mock_flash_budget.call_count == 1

@pytest.mark.asyncio
async def test_all_attempts_fail_budget_charged_once():
    """Verify budget is incremented exactly once even if all attempts fail."""
    chamber = DebateChamber()
    # It will hit the max retries limit of tenacity
    always_fails_llm = make_flaky_llm(fail_count=10)

    with patch('services.debate_chamber.check_and_increment_pro_budget', new_callable=AsyncMock) as mock_budget:
        with patch.object(chamber, '_classify_llm_tier', return_value='pro'):
            with pytest.raises(Exception):
                await chamber._invoke_llm(always_fails_llm, [])
                
    assert mock_budget.call_count == 1

@pytest.mark.asyncio
async def test_permanent_error_no_retry_budget_charged_once():
    """Verify permission_denied or invalid_argument charge budget once and do not retry."""
    chamber = DebateChamber()
    
    async def perma_fail(msgs):
        raise ValueError('permission_denied')
        
    llm = MagicMock()
    llm.ainvoke = perma_fail
    
    with patch('services.debate_chamber.check_and_increment_pro_budget', new_callable=AsyncMock) as mock_budget:
        with patch.object(chamber, '_classify_llm_tier', return_value='pro'):
            with pytest.raises(ValueError, match='permission_denied'):
                await chamber._invoke_llm(llm, [])
                
    assert mock_budget.call_count == 1

# Coverage target: services.debate_chamber (_invoke_llm budget behavior), core.budget
