import pytest
import ast
import inspect

def test_no_math_and_timedelta_in_exdate_scanner():
    """Verify math and timedelta are successfully removed from exdate_scanner imports."""
    import utils.exdate_scanner as m
    src = inspect.getsource(m)
    tree = ast.parse(src)
    
    # Collect all top-level imports
    top_imports = [n for n in ast.walk(tree) 
                   if isinstance(n, (ast.Import, ast.ImportFrom))]
    
    imported_names = []
    for node in top_imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.append(node.module)
            for alias in node.names:
                imported_names.append(alias.name)
                
    assert 'math' not in imported_names, "math import found in exdate_scanner.py"
    assert 'timedelta' not in imported_names, "timedelta import found in exdate_scanner.py"


def test_exdate_scanner_imports_cleanly():
    """Verify exdate_scanner still resolves successfully."""
    try:
        import utils.exdate_scanner  # noqa
    except ImportError as e:
        pytest.fail(f"exdate_scanner failed to import due to missing cleanup: {e}")

def test_snap_to_tick_values():
    """Verify technicals snap_to_tick logic correctly uses math top level (no crash)."""
    from utils.technicals import snap_to_tick
    
    # tick = 1 (Rp < 200)
    assert snap_to_tick(150.0) == 150.0
    
    # tick = 2 (Rp200 - Rp500)
    assert snap_to_tick(301.0) == 300.0
    assert snap_to_tick(300.0) == 300.0
    
    # tick = 5 (Rp500 - Rp2000)
    assert snap_to_tick(1002.5) == 1005.0
    
    # tick = 25 (Rp > 2000)
    assert snap_to_tick(4875.0) == 4875.0   # On tick
    assert snap_to_tick(4865.0) == 4875.0   # rounded up

def test_snap_to_tick_edge_cases():
    """Verify Edge Cases for snap_to_tick."""
    from utils.technicals import snap_to_tick
    
    assert snap_to_tick(0.0) == 0.0
    
    # NaN
    assert snap_to_tick(float('nan')) == 0.0
    
    # None
    assert snap_to_tick(None) == 0.0

# Coverage target: utils.exdate_scanner (import cleanliness), utils.technicals (snap_to_tick)
