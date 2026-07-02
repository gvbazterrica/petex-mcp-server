"""Input parameter models for the PETEX MCP Server."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from petex_mcp.models.enums import (
    AquiferModel,
    CompletionType,
    FluidType,
    GAPCompressorType,
    GAPDPControl,
    GAPPipeCorrelation,
    GAPPipeModel,
    GAPPredictionMethod,
    GAPPVTModel,
    GAPSeparatorType,
    GAPSolverMode,
    GAPSystemType,
    GAPTankModel,
    GAPTemperatureModel,
    GAPWellModel,
    GAPWellType,
    IPRModel,
    LiftMethod,
    OptimizationObjective,
    ReservoirType,
    VLPCorrelation,
    WellTrajectory,
    WellType,
)


# =============================================================================
# PROSPER Input Models
# =============================================================================


class CreateWellParams(BaseModel):
    well_type: WellType
    fluid: FluidType
    well_trajectory: WellTrajectory = WellTrajectory.VERTICAL
    depth: float = Field(gt=0, le=15000, description="Well depth in meters")
    gor: Optional[float] = Field(default=None, ge=0, le=100000)
    ipr_model: Optional[IPRModel] = None
    vlp_correlation: Optional[VLPCorrelation] = None
    completion_type: Optional[CompletionType] = None
    lift_method: Optional[LiftMethod] = None
    frequency: Optional[float] = Field(default=None, ge=30, le=90)
    skin: Optional[float] = Field(default=None, ge=-7, le=200)
    reservoir_pressure: Optional[float] = Field(default=None, ge=14.7, le=30000)
    reservoir_thickness: Optional[float] = Field(
        default=None, gt=0, le=1000,
        description="Net reservoir thickness in meters (used by Darcy IPR model)"
    )
    lateral_length: Optional[float] = Field(default=None, gt=0, le=10000)
    tvd: Optional[float] = Field(default=None, gt=0, le=15000)
    horizontal_perm_ratio: Optional[float] = Field(default=None, gt=0)


class AddIPRParams(BaseModel):
    model_path: str
    ipr_model: IPRModel


class AddVLPParams(BaseModel):
    model_path: str
    vlp_correlation: VLPCorrelation


class AddLiftParams(BaseModel):
    model_path: str
    lift_method: LiftMethod
    frequency: Optional[float] = Field(default=None, ge=30, le=90)
    injection_depth: Optional[float] = None
    gas_rate: Optional[float] = None


class AddCompletionParams(BaseModel):
    model_path: str
    completion_type: CompletionType


class NodalAnalysisParams(BaseModel):
    model_path: str
    whp_range: Optional[list[float]] = None
    frequency_range: Optional[list[float]] = None


class SensitivityParams(BaseModel):
    model_path: str
    variable: str
    values: list[float]


# =============================================================================
# MBAL Input Models
# =============================================================================


class HistoricalDataPoint(BaseModel):
    """A single production history data point."""

    model_config = {"populate_by_name": True}

    date: str
    oil_rate: Optional[float] = None
    gas_rate: Optional[float] = None
    water_rate: Optional[float] = None
    pressure: Optional[float] = Field(default=None, alias="reservoir_pressure")


class CreateMbalModelParams(BaseModel):
    reservoir_type: ReservoirType
    model_name: Optional[str] = None
    production_history: Optional[list[HistoricalDataPoint]] = None
    production_file: Optional[str] = None
    pvt_data: Optional[dict] = None


class RunHistoryMatchParams(BaseModel):
    model_path: str
    aquifer_model: AquiferModel
    initial_ooip_guess: Optional[float] = None
    initial_giip_guess: Optional[float] = None


class ForecastParams(BaseModel):
    model_path: str
    forecast_period: float = Field(gt=0, description="Forecast period in years")
    min_rate: Optional[float] = None
    max_water_cut: Optional[float] = Field(default=None, ge=0, le=1.0)
    min_pressure: Optional[float] = None


class MonteCarloParams(BaseModel):
    model_path: str
    distributions: dict
    iterations: int = Field(default=1000, ge=100, le=100000)


# =============================================================================
# GAP Input Models
# =============================================================================


class CreateGAPParams(BaseModel):
    model_name: str
    description: Optional[str] = None
    system_type: GAPSystemType = GAPSystemType.PRODUCTION
    optimization_method: OptimizationObjective = OptimizationObjective.MAX_OIL
    pvt_model: GAPPVTModel = GAPPVTModel.BLACK_OIL
    prediction_method: GAPPredictionMethod = GAPPredictionMethod.PRESSURE_AND_TEMPERATURE
    temperature_model: GAPTemperatureModel = GAPTemperatureModel.ROUGH_APPROXIMATION
    calculate_well_choke_dt: bool = False
    water_vapour: bool = False


class AddWellToNetworkParams(BaseModel):
    model_path: str
    well_name: str
    well_type: GAPWellType = GAPWellType.OIL_PRODUCER_NO_LIFT
    well_model: GAPWellModel = GAPWellModel.VLP_IPR_INTERSECTION
    prosper_model_path: Optional[str] = None
    inline_ipr: Optional[dict] = None


class AddPipelineParams(BaseModel):
    model_path: str
    pipeline_name: str
    source_node: str
    destination_node: str
    pipe_model: GAPPipeModel = GAPPipeModel.GAP_INTERNAL_CORRELATIONS
    correlation: GAPPipeCorrelation = GAPPipeCorrelation.PETROLEUM_EXPERTS_5
    length: Optional[float] = Field(default=None, gt=0)
    diameter: Optional[float] = Field(default=None, gt=0)
    roughness: float = Field(default=0.0006, gt=0)
    upstream_tvd: Optional[float] = None
    downstream_tvd: Optional[float] = None
    u_value: Optional[float] = Field(
        default=None, gt=0,
        description="Overall Heat Transfer Coefficient (BTU/h/ft2/F)"
    )
    surrounding_temperature: Optional[float] = None
    enable_transient: bool = False


class AddSeparatorParams(BaseModel):
    model_path: str
    separator_name: str
    separator_type: GAPSeparatorType = GAPSeparatorType.PRODUCTION_SEPARATOR
    capacity: Optional[float] = Field(default=None, gt=0)
    max_gas_rate: Optional[float] = Field(default=None, gt=0)
    max_water_rate: Optional[float] = Field(default=None, gt=0)
    max_oil_rate: Optional[float] = Field(default=None, gt=0)


class AddCompressorParams(BaseModel):
    model_path: str
    compressor_name: str
    compressor_type: GAPCompressorType = GAPCompressorType.PERFORMANCE_CURVES
    num_stages: int = Field(default=1, ge=1, le=10)
    suction_pressure: Optional[float] = None
    discharge_pressure: Optional[float] = None
    capacity: Optional[float] = Field(default=None, gt=0)
    polytropic_efficiency: Optional[float] = Field(default=None, gt=0, le=1.0)
    speed: Optional[float] = Field(default=None, gt=0)
    min_speed: Optional[float] = Field(default=None, gt=0)
    max_speed: Optional[float] = Field(default=None, gt=0)
    controllable: bool = False


class NetworkOptimizeParams(BaseModel):
    model_path: str
    objective: OptimizationObjective
    solver_mode: GAPSolverMode = GAPSolverMode.OPTIMISE_ALL_CONSTRAINTS
    constraints: Optional[dict] = None
    separator_pressure: Optional[float] = None
    gas_lift_available: Optional[float] = None
    calculate_potential: bool = False


class RunPredictionParams(BaseModel):
    """Parameters for running a GAP production forecast."""
    model_path: str
    start_date: str = Field(description="Start date (DD/MM/YYYY)")
    end_date: str = Field(description="End date (DD/MM/YYYY)")
    step_size_months: float = Field(default=2, gt=0, le=120)
    solver_mode: GAPSolverMode = GAPSolverMode.OPTIMISE_ALL_CONSTRAINTS
    separator_pressure: float = Field(gt=0)
    gas_lift_available: Optional[float] = None
    calculate_potential: bool = False
    target_pressures: Optional[dict[str, float]] = Field(
        default=None,
        description="Tank name -> target pressure (psig) for voidage replacement"
    )
    gas_injection_fraction: Optional[float] = Field(
        default=None, ge=0, le=1.0,
        description="Fraction of voidage replaced by gas (0=100% water)"
    )


class ConfigureWellControlParams(BaseModel):
    """Parameters for configuring well controls in GAP."""
    model_path: str
    well_name: str
    dp_control: GAPDPControl = GAPDPControl.CALCULATED
    fixed_dp: Optional[float] = Field(default=None, ge=0)
    # Gas lift control
    gas_lift_mode: Optional[str] = Field(
        default=None, description="'fixed' or 'calculated'"
    )
    gas_lift_rate: Optional[float] = Field(default=None, ge=0)
    max_gas_injection: Optional[float] = Field(default=None, ge=0)
    min_gas_injection: Optional[float] = Field(default=None, ge=0)
    # ESP control
    esp_frequency_mode: Optional[str] = Field(
        default=None, description="'fixed' or 'calculated'"
    )
    esp_frequency: Optional[float] = Field(default=None, ge=0)
    min_frequency: Optional[float] = Field(default=None, ge=0)
    max_frequency: Optional[float] = Field(default=None, ge=0)
    # Compressor speed control
    speed_mode: Optional[str] = Field(
        default=None, description="'fixed' or 'calculated'"
    )
    speed: Optional[float] = Field(default=None, ge=0)
    min_speed: Optional[float] = Field(default=None, ge=0)
    max_speed: Optional[float] = Field(default=None, ge=0)


class SetConstraintsParams(BaseModel):
    """Parameters for setting constraints on GAP equipment."""
    model_path: str
    equipment_name: str
    equipment_type: str = Field(description="well, separator, joint, system, group")
    max_liquid_rate: Optional[float] = Field(default=None, gt=0)
    max_gas_rate: Optional[float] = Field(default=None, gt=0)
    max_oil_rate: Optional[float] = Field(default=None, gt=0)
    max_water_rate: Optional[float] = Field(default=None, gt=0)
    min_liquid_rate: Optional[float] = Field(default=None, gt=0)
    min_gas_rate: Optional[float] = Field(default=None, gt=0)
    max_pressure: Optional[float] = Field(default=None, gt=0)
    min_pressure: Optional[float] = Field(default=None, gt=0)
    max_power: Optional[float] = Field(default=None, gt=0)
    max_gor: Optional[float] = Field(default=None, gt=0)
    max_water_cut: Optional[float] = Field(default=None, ge=0, le=1.0)


class AddScheduleEventParams(BaseModel):
    """Parameters for adding a scheduled event in GAP prediction."""
    model_path: str
    equipment_name: str
    event_date: str = Field(description="Event date (DD/MM/YYYY)")
    event_type: str = Field(description="Event type: start_well, stop_well, mask, unmask, change_constraint, change_pressure, change_openserver_variable")
    constraint_type: Optional[str] = None
    new_value: Optional[float] = None
    openserver_variable: Optional[str] = None


class GenerateWellIPRParams(BaseModel):
    """Parameters for batch generating well IPRs from PROSPER."""
    model_path: str
    well_names: Optional[list[str]] = Field(
        default=None, description="Well names to generate IPRs for. None=all wells."
    )
    pvt_method: Optional[str] = Field(
        default=None, description="'black_oil' or 'compositional'. None=use PROSPER setting."
    )


class GenerateWellVLPParams(BaseModel):
    """Parameters for batch generating well VLPs from PROSPER."""
    model_path: str
    well_names: Optional[list[str]] = Field(
        default=None, description="Well names to generate VLPs for. None=all wells."
    )
    rate_values: Optional[list[float]] = Field(
        default=None, description="Rate sensitivity values"
    )
    pressure_values: Optional[list[float]] = Field(
        default=None, description="Top node pressure sensitivity values"
    )
    gor_values: Optional[list[float]] = Field(
        default=None, description="GOR (or CGR/WGR) sensitivity values"
    )
    watercut_values: Optional[list[float]] = Field(
        default=None, description="Water cut sensitivity values"
    )
    glr_values: Optional[list[float]] = Field(
        default=None, description="Gas Lift Ratio injected values (gas lifted wells)"
    )
    frequency_values: Optional[list[float]] = Field(
        default=None, description="ESP frequency values (ESP wells)"
    )


class AddTankParams(BaseModel):
    """Parameters for adding a reservoir tank to GAP."""
    model_path: str
    tank_name: str
    tank_model: GAPTankModel = GAPTankModel.MATERIAL_BALANCE
    mbal_file: Optional[str] = None
    fluid_type: Optional[str] = Field(
        default=None, description="'oil', 'gas', or 'condensate' (for decline curve)"
    )
    connected_wells: Optional[list[str]] = None


class AddInlineElementParams(BaseModel):
    """Parameters for adding an inline element (choke, valve, etc.) to GAP."""
    model_path: str
    element_name: str
    element_type: str = Field(
        description="Type: gate_valve, check_valve, inline_separation, inline_choke, inline_injection, inline_general"
    )
    upstream_node: str
    downstream_node: str
    # For inline choke
    choke_diameter: Optional[float] = Field(default=None, gt=0)
    dp_control: Optional[GAPDPControl] = None
    # For inline injection
    injection_rate: Optional[float] = Field(default=None, ge=0)
    injection_fluid: Optional[str] = None
    # For inline general (script)
    script_content: Optional[str] = None


class AddSourceSinkParams(BaseModel):
    """Parameters for adding a source or sink element to GAP."""
    model_path: str
    element_name: str
    is_source: bool = True
    source_type: str = Field(
        default="fixed_rate",
        description="fixed_rate, fixed_mass, fixed_pressure, separated_gas, separated_oil, separated_water"
    )
    fluid_type: Optional[str] = Field(
        default=None, description="gas, water, oil, steam"
    )
    rate: Optional[float] = None
    pressure: Optional[float] = None
    temperature: Optional[float] = None


class AddPumpParams(BaseModel):
    """Parameters for adding a pump to GAP network."""
    model_path: str
    pump_name: str
    pump_type: str = Field(
        default="performance_curves",
        description="performance_curves, jet_pump, onesubsea"
    )
    num_stages: int = Field(default=1, ge=1)
    speed: Optional[float] = Field(default=None, gt=0)
    min_speed: Optional[float] = Field(default=None, gt=0)
    max_speed: Optional[float] = Field(default=None, gt=0)
    controllable: bool = False


class InitialiseIPRsFromTanksParams(BaseModel):
    """Parameters for initialising well IPRs from tank simulation at a specific date."""
    model_path: str
    date: str = Field(description="Date to initialise IPRs (DD/MM/YYYY)")
    well_names: Optional[list[str]] = Field(
        default=None, description="Well names to initialise. None=all wells."
    )
