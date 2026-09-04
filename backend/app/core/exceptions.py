"""Typed errors and the uniform response envelope.

Internal detail never crosses the API boundary: a 500 returns a code and a request id,
and nothing else.
"""

from typing import Any


class TraceFallError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500
    message = "An unexpected error occurred"

    def __init__(self, message: str | None = None, field: str | None = None) -> None:
        self.message = message or self.message
        self.field = field
        super().__init__(self.message)

    def envelope(self, request_id: str) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "request_id": request_id,
        }
        if self.field:
            error["field"] = self.field
        return {"error": error}


class Unauthenticated(TraceFallError):
    code = "UNAUTHENTICATED"
    status_code = 401
    message = "Authentication required"


class Forbidden(TraceFallError):
    code = "FORBIDDEN"
    status_code = 403
    message = "You do not have permission to perform this action"


class NotFound(TraceFallError):
    """Also returned for resources the caller may not access.

    A 403 on a case would confirm that the case exists, leaking that an investigation
    into a given address is underway (ADR-013).
    """

    code = "NOT_FOUND"
    status_code = 404
    message = "Resource not found"


class ValidationFailed(TraceFallError):
    code = "VALIDATION_ERROR"
    status_code = 422
    message = "Request validation failed"


class InvalidAddress(TraceFallError):
    code = "INVALID_ADDRESS"
    status_code = 422
    message = "Address failed validation"


class UnsupportedChain(TraceFallError):
    code = "UNSUPPORTED_CHAIN"
    status_code = 422
    message = "Chain is not supported"


class Conflict(TraceFallError):
    code = "ANALYSIS_IN_PROGRESS"
    status_code = 409
    message = "An analysis for this address is already running"


class ProviderUnavailable(TraceFallError):
    code = "PROVIDER_UNAVAILABLE"
    status_code = 503
    message = "A required upstream service is unavailable"
