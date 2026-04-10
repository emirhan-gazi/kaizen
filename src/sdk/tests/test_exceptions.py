"""Tests for kaizen_sdk.exceptions — error hierarchy and raise_for_status."""

from unittest.mock import MagicMock

import pytest

from kaizen_sdk.exceptions import (
    CTAuthError,
    CTError,
    CTNotFoundError,
    CTServerError,
    CTValidationError,
    raise_for_status,
)


def _mock_response(status_code: int, body: dict | None = None):
    """Create a mock httpx.Response with status_code and json()."""
    resp = MagicMock()
    resp.status_code = status_code
    if body is not None:
        resp.json.return_value = body
    else:
        resp.json.side_effect = ValueError("No JSON")
    return resp


def test_ct_error_base():
    err = CTError("something broke", status_code=400, detail="bad input")
    assert str(err) == "something broke"
    assert err.status_code == 400
    assert err.detail == "bad input"


def test_ct_error_defaults():
    err = CTError("oops")
    assert err.status_code is None
    assert err.detail is None


def test_auth_error_inherits():
    err = CTAuthError("unauthorized", status_code=401)
    assert isinstance(err, CTError)
    assert isinstance(err, Exception)


def test_not_found_inherits():
    assert issubclass(CTNotFoundError, CTError)


def test_validation_error_inherits():
    assert issubclass(CTValidationError, CTError)


def test_server_error_inherits():
    assert issubclass(CTServerError, CTError)


def test_raise_for_status_200():
    resp = _mock_response(200)
    raise_for_status(resp)  # Should not raise


def test_raise_for_status_201():
    resp = _mock_response(201)
    raise_for_status(resp)  # Should not raise


def test_raise_for_status_401():
    body = {
        "type": "about:blank",
        "title": "Unauthorized",
        "status": 401,
        "detail": "Invalid API key",
    }
    resp = _mock_response(401, body)
    with pytest.raises(CTAuthError) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"
    assert "Unauthorized" in str(exc_info.value)


def test_raise_for_status_404():
    body = {"title": "Not Found", "status": 404, "detail": "Task not found"}
    resp = _mock_response(404, body)
    with pytest.raises(CTNotFoundError) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 404


def test_raise_for_status_422():
    body = {"title": "Validation Error", "status": 422, "detail": "name is required"}
    resp = _mock_response(422, body)
    with pytest.raises(CTValidationError) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "name is required"


def test_raise_for_status_500():
    body = {"title": "Internal Server Error", "status": 500, "detail": "DB connection failed"}
    resp = _mock_response(500, body)
    with pytest.raises(CTServerError) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 500


def test_raise_for_status_502():
    resp = _mock_response(502)
    with pytest.raises(CTServerError) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 502


def test_raise_for_status_other_4xx():
    resp = _mock_response(429)
    with pytest.raises(CTError) as exc_info:
        raise_for_status(resp)
    assert exc_info.value.status_code == 429
    # Must be base CTError, not a subclass
    assert isinstance(exc_info.value, CTError)
    subclasses = (CTAuthError, CTNotFoundError, CTValidationError, CTServerError)
    assert not isinstance(exc_info.value, subclasses)


def test_raise_for_status_no_json_body():
    resp = _mock_response(500)
    with pytest.raises(CTServerError) as exc_info:
        raise_for_status(resp)
    assert "HTTP 500" in str(exc_info.value)
