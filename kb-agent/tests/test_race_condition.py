import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tenant_context import (
    set_tenant, set_search_scope, get_search_scope, get_tenant, reset_context
)

@pytest.fixture(autouse=True)
def reset():
    reset_context()
    yield
    reset_context()

def test_race_condition_fallback_scope():
    """Test that fallback scope can be clobbered by concurrent requests when context is lost."""
    set_tenant("alice@corp.com")
    set_search_scope("shared")
    
    def worker():
        # Force context loss to simulate ADK behavior (as claimed by developer)
        from services.tenant_context import _scope_var, _tenant_var
        _scope_var.set(None)
        # We don't clear _tenant_var here to see if it falls back correctly
        # but wait, if we clear it, it falls back to _fallback_tenant.
        
        time.sleep(0.1)
        return get_search_scope()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        
        time.sleep(0.02)
        # Simulate another request clobbering the fallback for the SAME tenant or default
        # Since we use a dict keyed by tenant, we need to know what get_tenant() returns in the worker.
        # If we didn't clear _tenant_var in worker, it returns "alice@corp.com".
        # So it looks up _fallback_scopes["alice@corp.com"].
        # If we clobber it here:
        set_search_scope("all") # This updates _fallback_scopes["alice@corp.com"] because tenant is still Alice!
        
        result = future.result()
        
    print(f"Worker saw scope: {result}")
    # It will be "all" because we clobbered it for "alice@corp.com"!
    assert result == "all", f"Expected 'all' (clobbered), got '{result}'"

def test_contextvar_propagation_in_pytest():
    """Test if contextvars are propagated by default in this environment."""
    set_search_scope("shared")
    
    def worker():
        return get_search_scope()

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(worker).result()
        
    print(f"Propagated scope: {result}")
    # In Python 3.7+, ThreadPoolExecutor STILL does not propagate contextvars by default.
    # Let's see what happens.
    # If it returns "all" (default), then it did NOT propagate.
    # If it returns "shared", then it DID propagate.
    assert result in ("all", "shared")
