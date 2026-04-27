import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from orchestrator import run_batch_debates, DebateChamber
from core.budget import BudgetExhaustedError

DUMMY_RESULT = {
    'ticker': 'BBRI',
    'final_verdict': '{}',
    'round_count': 1,
    'debate_history': [],
    'raw_data': '',
    'error': None
}

@pytest.mark.asyncio
async def test_chamber_instantiated_once():
    """Verify DebateChamber is instantiated exactly once, even for multiple tickers."""
    tickers = ['BBRI', 'BBCA', 'TLKM', 'BMRI', 'ASII']
    init_count = {'n': 0}

    original_init = DebateChamber.__init__
    def counting_init(self, *a, **kw):
        init_count['n'] += 1
        self.flash_llm = MagicMock()
        self.pro_llm = MagicMock()
        self.stockbit_client = MagicMock()
        self.app = MagicMock()

    with patch.object(DebateChamber, '__init__', counting_init):
        # We mock run so it doesn't actually execute
        with patch.object(DebateChamber, 'run', return_value=DUMMY_RESULT) as mock_run:
            mock_run.side_effect = lambda ticker, *a, **kw: {**DUMMY_RESULT, 'ticker': ticker}
            
            with patch('orchestrator.fetch_current_price', return_value=1000):
                await run_batch_debates(tickers)

    assert init_count['n'] == 1, f"Expected 1 instantiation, got {init_count['n']}"

@pytest.mark.asyncio
async def test_chamber_run_called_per_ticker():
    """Verify chamber.run() is called exactly once per ticker."""
    tickers = ['BBRI', 'BBCA', 'TLKM']
    
    with patch.object(DebateChamber, '__init__', lambda self: None):
        with patch.object(DebateChamber, 'run', autospec=True) as mock_run:
            mock_run.side_effect = lambda self, ticker, *a, **kw: {**DUMMY_RESULT, 'ticker': ticker}
            with patch('orchestrator.fetch_current_price', return_value=1000):
                results = await run_batch_debates(tickers)
            
    assert mock_run.call_count == 3
    assert len(results) == 3

@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """Verify that no more than 3 debates are run simultaneously (Semaphore bounds)."""
    import asyncio
    tickers = ['T1', 'T2', 'T3', 'T4', 'T5']
    
    active_debates = 0
    max_active = 0
    
    async def tracking_run(self, ticker, *args, **kwargs):
        nonlocal active_debates, max_active
        active_debates += 1
        if active_debates > max_active:
            max_active = active_debates
            
        await asyncio.sleep(0.01) # Hold concurrency
        active_debates -= 1
        return {**DUMMY_RESULT, 'ticker': ticker}

    with patch.object(DebateChamber, '__init__', lambda self: None):
        with patch.object(DebateChamber, 'run', tracking_run):
            with patch('orchestrator.fetch_current_price', return_value=1000):
                await run_batch_debates(tickers)
            
    # Max concurrency should be exactly what semaphore specifies (3)
    assert max_active == 3

@pytest.mark.asyncio
async def test_budget_exhausted_aborts_target_but_wont_crash():
    """Verify BudgetExhaustedError on one ticker gracefully returns error data."""
    tickers = ['T1', 'T2']
    
    async def error_run(self, ticker, *args, **kwargs):
        raise BudgetExhaustedError("Run out of budget")

    with patch.object(DebateChamber, '__init__', lambda self: None):
        with patch.object(DebateChamber, 'run', error_run):
            with patch('orchestrator.fetch_current_price', return_value=1000):
                results = await run_batch_debates(tickers)
            
    # Should not raise exception to caller, should return dict with error inside
    assert len(results) == 2
    assert "Budget exhausted" in results[0]["error"]
    assert "Budget exhausted" in results[1]["error"]

@pytest.mark.asyncio
async def test_all_tickers_fail_returns_list():
    """Verify that if all tickers fail fundamentally, the batch runner returns a valid list of error dicts."""
    tickers = ['T1', 'T2']
    
    async def fail_run(self, ticker, *args, **kwargs):
        raise Exception("Random backend crash")

    with patch.object(DebateChamber, '__init__', lambda self: None):
        with patch.object(DebateChamber, 'run', fail_run):
            with patch('orchestrator.fetch_current_price', return_value=1000):
                results = await run_batch_debates(tickers)
                
    assert isinstance(results, list)
    assert len(results) == 2
    assert "Random backend crash" in results[0]["error"]

# Coverage target: orchestrator (run_batch_debates)
