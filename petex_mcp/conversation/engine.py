"""Conversation engine for interactive parameter collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from petex_mcp.conversation.session import SessionContext


@dataclass
class MissingParamsResponse:
    """Response describing missing parameters."""

    missing_params: list[dict]


@dataclass
class CompletionResult:
    """Result of a completeness check."""

    is_complete: bool
    missing_params: Optional[MissingParamsResponse] = None


# Required parameters per tool
TOOL_REQUIRED_PARAMS: dict[str, list[str]] = {
    "create_prosper_well": ["well_type", "fluid", "depth"],
    "add_ipr_model": ["model_path", "ipr_model"],
    "add_vlp_correlation": ["model_path", "vlp_correlation"],
    "add_lift_method": ["model_path", "lift_method"],
    "add_completion": ["model_path", "completion_type"],
    "run_nodal_analysis": ["model_path"],
    "run_sensitivity": ["model_path", "variable", "values"],
}


class ConversationEngine:
    """Manages interactive parameter collection and guided suggestions."""

    def __init__(self, session: Optional[SessionContext] = None):
        self.session = session or SessionContext()

    def check_completeness(self, tool_name: str, params: dict) -> CompletionResult:
        """Check if all required parameters are present, considering session context."""
        required = TOOL_REQUIRED_PARAMS.get(tool_name)
        if required is None:
            return CompletionResult(is_complete=True)

        # Merge with session context defaults
        context_defaults = self.session.get_context_defaults(tool_name)
        effective_params = {**context_defaults, **params}

        missing = [p for p in required if p not in effective_params]

        if not missing:
            return CompletionResult(is_complete=True)

        missing_details = [{"name": p} for p in missing]
        return CompletionResult(
            is_complete=False,
            missing_params=MissingParamsResponse(missing_params=missing_details),
        )

    def accumulate_params(self, tool_name: str, new_params: dict) -> dict:
        """Merge new parameters with previously accumulated ones."""
        existing = self.session.accumulated_params.get(tool_name, {})
        merged = {**existing, **new_params}
        self.session.accumulated_params[tool_name] = merged
        return merged
