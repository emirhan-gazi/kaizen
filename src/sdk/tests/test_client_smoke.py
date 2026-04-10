"""Smoke tests for CTClient — TDD RED phase for Task 1."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from kaizen_sdk.client import CTClient
from kaizen_sdk.exceptions import CTError


def test_client_constructor_with_key():
    client = CTClient(api_key="test-key", base_url="http://localhost:8000")
    assert client._api_key == "test-key"
    assert client._base_url == "http://localhost:8000"
    client.close()


def test_client_missing_key_raises(monkeypatch):
    monkeypatch.delenv("KAIZEN_API_KEY", raising=False)
    with pytest.raises(CTError):
        CTClient()


def test_client_has_all_methods():
    client = CTClient(api_key="test-key")
    for method_name in [
        "log_feedback",
        "get_prompt",
        "trigger_optimization",
        "get_job",
        "list_tasks",
        "create_task",
        "activate_prompt",
        "close",
    ]:
        assert hasattr(client, method_name), f"Missing method: {method_name}"
    client.close()


def test_client_context_manager():
    with CTClient(api_key="test-key") as client:
        assert client._api_key == "test-key"
