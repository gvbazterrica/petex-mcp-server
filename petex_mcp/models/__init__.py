"""Data models for the PETEX MCP Server."""

from petex_mcp.models.commands import OpenServerCommand, CommandResult
from petex_mcp.models.outputs import (
    BottleneckResult,
    ExecutionMetadata,
    ForecastResult,
    HistoryMatchResult,
    MonteCarloResult,
    NetworkSolution,
    OptimizationResult,
    StructuredError,
)

__all__ = [
    "BottleneckResult",
    "CommandResult",
    "ExecutionMetadata",
    "ForecastResult",
    "HistoryMatchResult",
    "MonteCarloResult",
    "NetworkSolution",
    "OpenServerCommand",
    "OptimizationResult",
    "StructuredError",
]
