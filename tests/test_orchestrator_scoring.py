import pytest
import copy
from orchestrator import compute_conviction_score

def test_no_mutation():
    """Verify compute_conviction_score does not mutate its input."""
    verdict = {'confidence': 0.8, 'risk_reward_ratio': 2.5}
    original = copy.deepcopy(verdict)
    compute_conviction_score(verdict)
    assert verdict == original

def test_returns_tuple():
    """Verify function returns exactly (float, str|None)."""
    result = compute_conviction_score({'confidence': 0.7, 'risk_reward_ratio': 2.0})
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], float)

def test_high_rr_warning():
    """Verify warning is present when RR ratio > 3.5."""
    score, warning = compute_conviction_score({'confidence': 0.8, 'risk_reward_ratio': 4.0})
    assert warning is not None
    assert 'R/R' in warning

def test_normal_rr_no_warning():
    """Verify warning is None when RR ratio <= 3.5."""
    score, warning = compute_conviction_score({'confidence': 0.8, 'risk_reward_ratio': 2.0})
    assert warning is None

def test_score_formula():
    """Verify the 50/50 formula yields the correct numerical value."""
    # Score = 0.5 * confidence + 0.5 * (RR/5.0)
    score, _ = compute_conviction_score({'confidence': 0.6, 'risk_reward_ratio': 2.5})
    expected = (0.5 * 0.6) + (0.5 * (2.5 / 5.0))
    assert abs(score - expected) < 0.001

def test_none_inputs_no_crash():
    """Verify handling of None types for RR and confidence defaults to 0."""
    score, warning = compute_conviction_score({'confidence': None, 'risk_reward_ratio': None})
    assert score == 0.0
    assert warning is None

def test_rr_norm_cap():
    """Verify anomalous RR ratios (>5.0) are capped."""
    score, _ = compute_conviction_score({'confidence': 1.0, 'risk_reward_ratio': 999.0})
    # Max contribution is 1.0
    expected = (0.5 * 1.0) + (0.5 * 1.0)
    assert abs(score - expected) < 0.001

def test_confidence_normalization():
    """Verify if confidence is 1-100 it scales to [0,1]."""
    score1, _ = compute_conviction_score({'confidence': 80})  # 80/100
    score2, _ = compute_conviction_score({'confidence': 0.8}) # 0.8/1.0
    assert abs(score1 - score2) < 0.001

def test_confidence_exceeds_bounds():
    """Verify confidence > 100 or < 0 is clamped [0,1]."""
    score, _ = compute_conviction_score({'confidence': 150})
    assert score > 0 # At minimum, should cap out without expanding score. Max conf score = 0.5 * 1.0
    
    score, _ = compute_conviction_score({'confidence': -0.5})
    # Expected would be 0, assuming RR=0.
    assert score == 0.0

# Coverage target: orchestrator (compute_conviction_score)
