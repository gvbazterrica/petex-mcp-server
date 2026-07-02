"""Error handling for the PETEX MCP Server."""

from petex_mcp.errors.exceptions import (
    ErrorHandler,
    IncompatibleComponentError,
    PetexConnectionError,
    PetexError,
    PetexExecutionError,
    PetexInternalError,
    PetexTimeoutError,
    PetexValidationError,
)

__all__ = [
    "ErrorHandler",
    "IncompatibleComponentError",
    "PetexConnectionError",
    "PetexError",
    "PetexExecutionError",
    "PetexInternalError",
    "PetexTimeoutError",
    "PetexValidationError",
]
