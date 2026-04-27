import json
import pytest
from utils.serializers import MsgSpecJSONResponse

def test_render_returns_bytes():
    """Verify that render returns a valid bytes object."""
    r = MsgSpecJSONResponse({'key': 'val'})
    assert isinstance(r.body, bytes)

def test_render_is_valid_json():
    """Verify that the rendered payload can be decoded as valid JSON."""
    r = MsgSpecJSONResponse({'price': 4875, 'ticker': 'BBRI'})
    parsed = json.loads(r.body)
    assert parsed['ticker'] == 'BBRI'
    assert parsed['price'] == 4875

def test_render_list():
    """Verify that sequences (lists) are rendered correctly."""
    r = MsgSpecJSONResponse([1, 2, 3])
    assert json.loads(r.body) == [1, 2, 3]

def test_render_none():
    """Verify that passing None does not raise exception and renders as null."""
    r = MsgSpecJSONResponse(None)
    assert r.body == b'null'

def test_render_unicode():
    """Verify that unicode strings (like Rupiah) are preserved and not corrupted."""
    r = MsgSpecJSONResponse({'name': 'Rp 4.875 📈💸'})
    decoded = r.body.decode('utf-8')
    assert 'Rp' in decoded
    assert '📈💸' in decoded

def test_render_large_dict():
    """Verify that rendering a very large dict does not hit recursion or memory errors."""
    large_data = {f"key_{i}": i for i in range(1000)}
    r = MsgSpecJSONResponse(large_data)
    parsed = json.loads(r.body)
    assert parsed["key_999"] == 999

# Coverage target: utils.serializers
