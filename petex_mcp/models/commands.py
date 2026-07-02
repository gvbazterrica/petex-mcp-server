"""OpenServer command models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OpenServerCommand:
    """Represents a single OpenServer command to execute."""

    method: str  # DoCmd, DoSet, DoGet, DoSlowCmd
    target: str  # OpenServer variable path or command
    value: Optional[str] = None  # Value for DoSet commands


@dataclass
class CommandResult:
    """Result from executing OpenServer commands."""

    success: bool
    results: list[str] | None = None
    error_message: str | None = None
    value: Optional[str] = None
    duration_ms: Optional[float] = None
