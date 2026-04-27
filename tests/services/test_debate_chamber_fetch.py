import pytest
from unittest.mock import patch
from services.debate_chamber import DebateChamber

# We disable the retry sleep for tests so they run instantly
import tenacity

@pytest.fixture
def no_sleep_tenacity(monkeypatch):
    """Monkey-patch asyncio.sleep to do nothing."""
    import asyncio
    from unittest.mock import AsyncMock
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))

@pytest.mark.asyncio
async def test_permanent_error_no_retry(dummy_chamber, no_sleep_tenacity):
    """Verify 'permission_denied' or 'authentication' are not retried."""
    call_count = {'n': 0}

    def counting_get(url):
        call_count['n'] += 1
        raise Exception('permission_denied: 401')
        
    dummy_chamber.stockbit_client.get = counting_get

    with pytest.raises(Exception, match='permission_denied'):
        await dummy_chamber._fetch_url('https://example.com/api')

    assert call_count['n'] == 1, f"Expected 1 call, got {call_count['n']}"

@pytest.mark.asyncio
async def test_authentication_error_no_retry(dummy_chamber, no_sleep_tenacity):
    """Verify 'authentication' is not retried."""
    call_count = {'n': 0}

    def counting_get(url):
        call_count['n'] += 1
        raise Exception('Authentication failed')
        
    dummy_chamber.stockbit_client.get = counting_get

    with pytest.raises(Exception, match='Authentication'):
        await dummy_chamber._fetch_url('https://example.com/api')

    assert call_count['n'] == 1, f"Expected 1 call, got {call_count['n']}"

@pytest.mark.asyncio
async def test_transient_error_retried(dummy_chamber, no_sleep_tenacity):
    """Verify HTTP 429/503 is retried (transient error)."""
    call_count = {'n': 0}
    
    def flaky_get(url):
        call_count['n'] += 1
        if call_count['n'] < 3:
            raise Exception('503 resource exhausted')
        return {'data': 'ok'}
        
    dummy_chamber.stockbit_client.get = flaky_get
    result = await dummy_chamber._fetch_url('https://example.com/api')
    
    assert result == {'data': 'ok'}
    assert call_count['n'] == 3

@pytest.mark.asyncio
async def test_exhaustion_on_transient_error(dummy_chamber, no_sleep_tenacity):
    """Verify that after max retries (3), the exception is raised."""
    call_count = {'n': 0}
    
    def continually_failing_get(url):
        call_count['n'] += 1
        raise Exception('429 Too Many Requests')
        
    dummy_chamber.stockbit_client.get = continually_failing_get
    
    import tenacity
    with pytest.raises(tenacity.RetryError):
         await dummy_chamber._fetch_url('https://example.com/api')
         
    # Our retry rules usually dictate stop_after_attempt(3)
    assert call_count['n'] == 3

@pytest.mark.asyncio
async def test_empty_string_exception(dummy_chamber, no_sleep_tenacity):
    """Verify exception without message doesn't crash the classifier."""
    def empty_ex(url):
        raise Exception()
        
    dummy_chamber.stockbit_client.get = empty_ex
    
    with pytest.raises(Exception):
        await dummy_chamber._fetch_url('url')

@pytest.mark.asyncio
async def test_budget_exhausted_from_get_no_retry(dummy_chamber, no_sleep_tenacity):
    """Verify BudgetExhaustedError is not retried (if raised internally)."""
    from core.budget import BudgetExhaustedError
    call_count = {'n': 0}
    
    def budget_ex(url):
        call_count['n'] += 1
        raise BudgetExhaustedError('OOM')
        
    dummy_chamber.stockbit_client.get = budget_ex
    
    with pytest.raises(BudgetExhaustedError):
        await dummy_chamber._fetch_url('url')
        
    assert call_count['n'] == 1

# Coverage target: services.debate_chamber (_fetch_url)
