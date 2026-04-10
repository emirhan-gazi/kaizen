"""Tests for kaizen_sdk.cache — TTL cache with time-based expiry."""

from unittest.mock import patch

from kaizen_sdk.cache import TTLCache


def test_cache_set_get():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_cache_miss():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("nonexistent") is None


def test_cache_ttl_expiry():
    cache = TTLCache(ttl_seconds=10)
    with patch("kaizen_sdk.cache.time.monotonic") as mock_mono:
        # Set at time=1000
        mock_mono.return_value = 1000.0
        cache.set("key1", "value1")

        # Get within TTL at time=1005
        mock_mono.return_value = 1005.0
        assert cache.get("key1") == "value1"

        # Get after TTL at time=1011
        mock_mono.return_value = 1011.0
        assert cache.get("key1") is None


def test_cache_invalidate():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key1", "value1")
    cache.invalidate("key1")
    assert cache.get("key1") is None


def test_cache_invalidate_missing_key():
    cache = TTLCache(ttl_seconds=60)
    cache.invalidate("nonexistent")  # Should not raise


def test_cache_clear():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key1", "v1")
    cache.set("key2", "v2")
    cache.set("key3", "v3")
    cache.clear()
    assert cache.get("key1") is None
    assert cache.get("key2") is None
    assert cache.get("key3") is None


def test_cache_overwrite():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key1", "old")
    cache.set("key1", "new")
    assert cache.get("key1") == "new"


def test_cache_stores_any_type():
    cache = TTLCache(ttl_seconds=60)
    cache.set("dict", {"a": 1})
    cache.set("list", [1, 2, 3])
    cache.set("none", None)
    assert cache.get("dict") == {"a": 1}
    assert cache.get("list") == [1, 2, 3]
    assert cache.get("none") is None  # None is indistinguishable from miss
