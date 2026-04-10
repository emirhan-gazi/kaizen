"""Exception hierarchy for the Kaizen SDK.

Maps HTTP status codes from the API to typed Python exceptions.
Parses RFC 7807 ProblemDetail responses when available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


class CTError(Exception):
    """Base exception for CT SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: str | None = None,
    ):
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class CTAuthError(CTError):
    """Raised on 401 Unauthorized."""

    pass


class CTNotFoundError(CTError):
    """Raised on 404 Not Found."""

    pass


class CTValidationError(CTError):
    """Raised on 422 Unprocessable Entity."""

    pass


class CTServerError(CTError):
    """Raised on 5xx Server Error."""

    pass


# Status code to exception class mapping
_STATUS_MAP: dict[int, type[CTError]] = {
    401: CTAuthError,
    404: CTNotFoundError,
    422: CTValidationError,
}


def raise_for_status(response: httpx.Response) -> None:
    """Inspect an httpx response and raise the appropriate CTError if non-2xx.

    Attempts to parse RFC 7807 ProblemDetail JSON for the ``detail`` field.
    """
    status = response.status_code

    if 200 <= status < 300:
        return

    # Try to extract detail from RFC 7807 JSON body
    detail: str | None = None
    title: str | None = None
    try:
        body = response.json()
        detail = body.get("detail")
        title = body.get("title")
    except Exception:
        pass

    message = title or f"HTTP {status}"
    if detail:
        message = f"{message}: {detail}"

    # Map to specific exception class
    if status in _STATUS_MAP:
        raise _STATUS_MAP[status](message, status_code=status, detail=detail)

    if 500 <= status < 600:
        raise CTServerError(message, status_code=status, detail=detail)

    raise CTError(message, status_code=status, detail=detail)
