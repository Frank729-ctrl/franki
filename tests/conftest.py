"""Shared pytest fixtures."""
import pytest


@pytest.fixture(autouse=True)
def clear_response_cache():
    """Clear the response cache before each test to prevent cross-test pollution."""
    from franki.cache import response_cache
    response_cache.clear()
    yield
    response_cache.clear()
