"""Session context manager for the PETEX MCP Server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SessionSummary:
    """Summary of current session state."""

    active_models: dict
    fluid_type: Optional[str]
    well_type: Optional[str]
    well_trajectory: Optional[str]
    selected_correlations: dict
    unit_preferences: str
    operation_count: int


class SessionContext:
    """Maintains state across multiple tool invocations within a session."""

    def __init__(self):
        self.active_models: dict[str, dict] = {}
        self.fluid_type: Optional[str] = None
        self.well_type: Optional[str] = None
        self.well_trajectory: Optional[str] = None
        self.selected_correlations: dict[str, str] = {}
        self.unit_preferences: str = "field"
        self.accumulated_params: dict[str, dict] = {}
        self.operation_history: list[dict] = []

    def query_context(self) -> SessionSummary:
        """Return current session state for user inspection."""
        return SessionSummary(
            active_models=self.active_models,
            fluid_type=self.fluid_type,
            well_type=self.well_type,
            well_trajectory=self.well_trajectory,
            selected_correlations=self.selected_correlations,
            unit_preferences=self.unit_preferences,
            operation_count=len(self.operation_history),
        )

    def update_context(self, tool_name: str, params: dict, result: Any) -> None:
        """Update session context after a successful operation."""
        if "fluid" in params:
            self.fluid_type = params["fluid"]
        if "well_type" in params:
            self.well_type = params["well_type"]
        if "well_trajectory" in params:
            self.well_trajectory = params["well_trajectory"]

        model_path = None
        if isinstance(result, dict):
            model_path = result.get("model_path")
        elif hasattr(result, "model_path"):
            model_path = result.model_path

        if model_path:
            self.active_models[model_path] = {"created_by": tool_name}

        self.operation_history.append({
            "tool_name": tool_name,
            "params": params,
        })

    def reset(self) -> None:
        """Clear all session context."""
        self.active_models = {}
        self.fluid_type = None
        self.well_type = None
        self.well_trajectory = None
        self.selected_correlations = {}
        self.unit_preferences = "field"
        self.accumulated_params = {}
        self.operation_history = []

    def carry_forward(self, new_workflow: str) -> dict:
        """Offer relevant context from current session for a new workflow."""
        context: dict[str, Any] = {"unit_system": self.unit_preferences}

        if self.fluid_type:
            context["fluid"] = self.fluid_type
        if self.well_type:
            context["well_type"] = self.well_type

        if new_workflow == "gap":
            well_models = [
                path for path, info in self.active_models.items()
                if info.get("created_by") == "create_prosper_well"
            ]
            if well_models:
                context["available_well_models"] = well_models

        elif new_workflow == "mbal":
            prosper_models = [
                path for path, info in self.active_models.items()
                if info.get("created_by") == "create_prosper_well"
            ]
            if prosper_models:
                context["related_prosper_models"] = prosper_models

        return context

    def get_context_defaults(self, tool_name: str) -> dict:
        """Return previously specified parameters as defaults for a new operation."""
        defaults: dict[str, Any] = {}
        if self.fluid_type:
            defaults["fluid"] = self.fluid_type
        if self.well_type:
            defaults["well_type"] = self.well_type
        if self.well_trajectory:
            defaults["well_trajectory"] = self.well_trajectory
        return defaults
