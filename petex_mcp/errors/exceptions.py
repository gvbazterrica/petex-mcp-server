"""Exception hierarchy for the PETEX MCP Server."""

from __future__ import annotations

from petex_mcp.models.outputs import StructuredError


class PetexError(Exception):
    """Base error with structured error response."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "PETEX_ERROR",
        suggested_action: str = "",
        original_params: dict | None = None,
    ):
        super().__init__(error_message)
        self.error_message = error_message
        self.error_code = error_code
        self.suggested_action = suggested_action
        self.original_params = original_params or {}


class PetexValidationError(PetexError):
    """Validation error for invalid input parameters."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "VALIDATION_ERROR",
        suggested_action: str = "Fix input parameters per error message",
        original_params: dict | None = None,
    ):
        super().__init__(error_message, error_code, suggested_action, original_params)


class PetexConnectionError(PetexError):
    """Connection error for COM/OpenServer failures."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "CONNECTION_ERROR",
        suggested_action: str = "Check PETEX installation, restart applications",
        original_params: dict | None = None,
    ):
        super().__init__(error_message, error_code, suggested_action, original_params)


class PetexExecutionError(PetexError):
    """Execution error for calculation failures."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "EXECUTION_ERROR",
        suggested_action: str = "Verify model data, try different parameters",
        original_params: dict | None = None,
    ):
        super().__init__(error_message, error_code, suggested_action, original_params)


class PetexTimeoutError(PetexError):
    """Timeout error for long-running operations."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "TIMEOUT_ERROR",
        suggested_action: str = "Simplify calculation, reduce range size",
        original_params: dict | None = None,
    ):
        super().__init__(error_message, error_code, suggested_action, original_params)


class PetexInternalError(PetexError):
    """Internal error for unexpected failures."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "INTERNAL_ERROR",
        suggested_action: str = "Report bug, retry operation",
        original_params: dict | None = None,
    ):
        super().__init__(error_message, error_code, suggested_action, original_params)


class IncompatibleComponentError(PetexValidationError):
    """Error for incompatible component combinations."""

    def __init__(
        self,
        error_message: str,
        error_code: str = "INCOMPATIBLE_COMPONENT",
        suggested_action: str = "Check component compatibility requirements",
        original_params: dict | None = None,
    ):
        super().__init__(error_message, error_code, suggested_action, original_params)


class ErrorHandler:
    """Handles errors and produces structured error responses."""

    # Map error types to categories
    _CATEGORY_MAP = {
        PetexValidationError: "validation_error",
        IncompatibleComponentError: "validation_error",
        PetexConnectionError: "connection_error",
        PetexExecutionError: "execution_error",
        PetexTimeoutError: "timeout_error",
        PetexInternalError: "internal_error",
    }

    @classmethod
    def handle(cls, error: Exception, original_params: dict | None = None) -> StructuredError:
        """Convert an exception to a StructuredError response."""
        if isinstance(error, PetexError):
            category = cls._CATEGORY_MAP.get(type(error), "internal_error")
            params = error.original_params if error.original_params else (original_params or {})
            return StructuredError(
                error_code=error.error_code,
                error_message=error.error_message,
                suggested_action=error.suggested_action,
                category=category,
                original_params=params,
            )
        else:
            return StructuredError(
                error_code="INTERNAL_ERROR",
                error_message=str(error),
                suggested_action="Report bug, retry operation",
                category="internal_error",
                original_params=original_params or {},
            )
