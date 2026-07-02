"""Output models for the PETEX MCP Server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionMetadata:
    """Metadata about a tool execution."""

    duration_seconds: float
    petex_version: Optional[str] = None
    model_file_path: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class StructuredError:
    """Structured error response for MCP clients."""

    error_code: str
    error_message: str
    suggested_action: str
    category: str
    original_params: dict = field(default_factory=dict)


# =============================================================================
# MBAL Output Models
# =============================================================================


@dataclass
class HistoryMatchResult:
    """Result from running history matching."""

    model_path: str
    script: str
    ooip_stb: Optional[float] = None
    giip_scf: Optional[float] = None
    ooip_unit: str = "STB"
    giip_unit: str = "SCF"
    aquifer_volume: Optional[float] = None
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class ForecastResult:
    """Result from running production forecast."""

    model_path: str
    script: str
    forecast_period: float = 0.0
    time_series: list[dict] = field(default_factory=list)
    abandonment_reason: Optional[str] = None
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class MonteCarloResult:
    """Result from running Monte Carlo reserves estimation."""

    model_path: str
    script: str
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None
    mean: Optional[float] = None
    unit: str = "STB"
    iterations: int = 0
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


# =============================================================================
# GAP Output Models
# =============================================================================


@dataclass
class NetworkSolution:
    """Result from running the GAP network solver."""

    model_path: str
    script: str
    total_field_production: dict = field(default_factory=lambda: {
        "oil_rate": 0.0,
        "oil_rate_unit": "STB/d",
        "gas_rate": 0.0,
        "gas_rate_unit": "MSCF/d",
        "water_rate": 0.0,
        "water_rate_unit": "STB/d",
    })
    well_results: list[dict] = field(default_factory=list)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """Result from running network optimization."""

    model_path: str
    script: str
    objective: str = ""
    production_improvement_percent: float = 0.0
    optimized_production: dict = field(default_factory=dict)
    well_allocations: list[dict] = field(default_factory=list)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class BottleneckResult:
    """Result from bottleneck identification."""

    model_path: str
    script: str
    restricted_wells: list[str] = field(default_factory=list)
    restricted_pipelines: list[str] = field(default_factory=list)
    limiting_facilities: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class PredictionResult:
    """Result from running a GAP production prediction."""

    model_path: str
    script: str
    start_date: str = ""
    end_date: str = ""
    step_size_months: float = 0.0
    solver_mode: str = ""
    cumulative_oil: float = 0.0
    cumulative_gas: float = 0.0
    cumulative_water: float = 0.0
    time_steps: int = 0
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class WellControlResult:
    """Result from configuring well controls."""

    model_path: str
    well_name: str
    script: str
    controls_applied: dict = field(default_factory=dict)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConstraintsResult:
    """Result from setting constraints."""

    model_path: str
    equipment_name: str
    script: str
    constraints_set: dict = field(default_factory=dict)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class GenerateVLPResult:
    """Result from batch VLP generation."""

    model_path: str
    script: str
    wells_processed: list[str] = field(default_factory=list)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)


@dataclass
class GenerateIPRResult:
    """Result from batch IPR generation."""

    model_path: str
    script: str
    wells_processed: list[str] = field(default_factory=list)
    metadata: ExecutionMetadata = field(default_factory=lambda: ExecutionMetadata(duration_seconds=0.0))
    warnings: list[str] = field(default_factory=list)
