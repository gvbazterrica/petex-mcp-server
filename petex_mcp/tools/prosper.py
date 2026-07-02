"""PROSPER tool functions for well modeling.

Generates complete, executable OpenServer scripts with all 7 sections:
1. System Summary (well type, fluid, lift method, trajectory)
2. PVT (fluid properties and correlations)
3. Equipment (tubing, casing, deviation survey)
4. IPR (inflow performance relationship)
5. VLP (vertical lift performance correlations)
6. Artificial Lift (ESP, gas lift, etc.)
7. System Analysis (nodal analysis conditions)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any

from petex_mcp.models.commands import OpenServerCommand
from petex_mcp.models.inputs import (
    CreateWellParams,
    AddIPRParams,
    AddVLPParams,
    AddLiftParams,
    AddCompletionParams,
    NodalAnalysisParams,
    SensitivityParams,
)
from petex_mcp.models.enums import (
    CompletionType,
    ExportFormat,
    FluidType,
    IPRModel,
    LiftMethod,
    SensitivityVariable,
    VLPCorrelation,
    WellTrajectory,
    WellType,
)
from petex_mcp.models.outputs import ExecutionMetadata
from petex_mcp.script.generator import ScriptGenerator
from petex_mcp.errors.exceptions import IncompatibleComponentError, PetexValidationError


# ============================================================================
# OpenServer enum mappings (PROSPER internal codes)
# ============================================================================

WELL_TYPE_MAP = {
    WellType.PRODUCER: "0",
    WellType.INJECTOR: "1",
}

FLUID_TYPE_MAP = {
    FluidType.OIL: "0",
    FluidType.GAS: "1",
    FluidType.CONDENSATE: "2",
    FluidType.WATER: "3",
}

# PROSPER.SIN.SUM.FLOWTYPE = Tubing(0)/Annular(1)/Both(2) — NOT trajectory.
# PROSPER.SIN.SUM.INFLOWTYPE = Single Branch(0) / Multi-Lateral(1)
# Well trajectory is determined by IPR model + deviation survey, not a single tag.
INFLOW_TYPE_MAP = {
    WellTrajectory.VERTICAL: "0",       # Single Branch
    WellTrajectory.DEVIATED: "0",       # Single Branch
    WellTrajectory.HORIZONTAL: "0",     # Single Branch
    WellTrajectory.MULTILATERAL: "1",   # Multi-Lateral
}

LIFT_METHOD_MAP = {
    LiftMethod.NONE: "0",
    LiftMethod.GAS_LIFT_CONTINUOUS: "1",
    LiftMethod.ESP: "2",
    LiftMethod.PCP: "4",
    LiftMethod.JET_PUMP: "7",
    LiftMethod.ROD_PUMP: "9",
    LiftMethod.GAS_LIFT_INTERMITTENT: "10",
    LiftMethod.PLUNGER_LIFT: "0",  # No direct code; use None and configure separately
}

# Completion in PROSPER uses two variables:
# PROSPER.SIN.SUM.COMPLETION: 0 = Cased Hole, 1 = Open Hole
# PROSPER.SIN.SUM.GRAVELPACK: 0 = None, 1 = Gravel pack, 2 = Pre-packed screen,
#                              3 = Wire wrapped screen, 4 = Slotted liner
COMPLETION_TYPE_TO_SETTINGS = {
    CompletionType.OPEN_HOLE: {"completion": "1", "gravelpack": "0"},
    CompletionType.CASED_PERFORATED: {"completion": "0", "gravelpack": "0"},
    CompletionType.GRAVEL_PACK: {"completion": "0", "gravelpack": "1"},
    CompletionType.FRAC_PACK: {"completion": "0", "gravelpack": "1"},
    CompletionType.OPEN_HOLE_GRAVEL_PACK: {"completion": "1", "gravelpack": "1"},
    CompletionType.SLOTTED_LINER: {"completion": "1", "gravelpack": "4"},
    CompletionType.PRE_PACKED_SCREEN: {"completion": "1", "gravelpack": "2"},
}

# IPR model: PROSPER.SIN.IPR.SINGLE.IPRMETHOD is zero-based index in list box.
# The order depends on available models for the well configuration.
# For standard single-branch wells the common ordering is:
# 0=PI Entry, 1=Vogel, 2=Composite, 3=Fetkovich, 4=Jones, 5=Darcy
# For horizontal wells the models appear differently.
# Safer approach: use PROSPER.SIN.IPR.SINGLE.IPRMODEL (sets by name)
IPR_MODEL_NAME_MAP = {
    IPRModel.PI_ENTRY: "PI Entry",
    IPRModel.VOGEL: "Vogel",
    IPRModel.DARCY: "Darcy",
    IPRModel.JONES: "Jones",
    IPRModel.FETKOVITCH: "Fetkovich",
    IPRModel.COMPOSITE: "Composite",
    IPRModel.HORIZONTAL_PI_JOSHI: "Joshi Horizontal PI",
    IPRModel.HORIZONTAL_PI_BABU_ODEH: "Babu-Odeh Horizontal PI",
    IPRModel.HORIZONTAL_PI_KUCHUK: "Kuchuk Horizontal PI",
    IPRModel.MULTI_LAYER: "Multi Layer",
    IPRModel.HYDRAULICALLY_FRACTURED: "Hydraulically Fractured",
}

# VLP correlations: use labels (recommended by PETEX - indices may change between versions)
# Index mapping kept for reference:
# 0=DunsandRosModified, 1=HagedornBrown, 2=FancherBrown, 4=MukerjeeBrill,
# 5=BeggsandBrill, 8=PetroleumExperts, 9=Orkiszewski, 10=PetroleumExperts2,
# 12=PetroleumExperts3, 20=PetroleumExperts5, 28=OLGAS2P, 3=Gray
VLP_CORRELATION_LABEL_MAP = {
    VLPCorrelation.HAGEDORN_BROWN: "HagedornBrown",
    VLPCorrelation.BEGGS_BRILL: "BeggsandBrill",
    VLPCorrelation.DUNS_ROS: "DunsandRosModified",
    VLPCorrelation.ORKISZEWSKI: "Orkiszewski",
    VLPCorrelation.PETROLEUM_EXPERTS_2: "PetroleumExperts2",
    VLPCorrelation.PETROLEUM_EXPERTS_3: "PetroleumExperts3",
    VLPCorrelation.PETROLEUM_EXPERTS_5: "PetroleumExperts5",
    VLPCorrelation.ANSARI: "PetroleumExperts",
    VLPCorrelation.OLGAS_2P: "OLGAS2P",
    VLPCorrelation.GRAY: "Gray",
    VLPCorrelation.GOVIER_AZIZ: "MukerjeeBrill",
    VLPCorrelation.MUKERJEE_BRILL: "MukerjeeBrill",
}

SENSITIVITY_VARIABLE_MAP = {
    "esp_frequency": "PROSPER.SIN.ESP.Frequency",
    "gor": "PROSPER.PVT.Input.SolGOR",
    "reservoir_pressure": "PROSPER.SIN.IPR.Single.Pres",
    "water_cut": "PROSPER.SIN.IPR.Single.WC",
    "skin": "PROSPER.SIN.IPR.Single.Skin",
    "tubing_diameter": "PROSPER.SIN.EQP.DOWN.DATA[0].TID",
    "lateral_length": "PROSPER.SIN.IPR.Single.HzLength",
}


# ============================================================================
# Engineering defaults
# ============================================================================

FLUID_DEFAULTS = {
    "oil": {
        "gor": 300.0,
        "api_gravity": 30.0,
        "gas_gravity": 0.65,
        "water_salinity": 10000.0,
        "pb_correlation": "Vasquez_Beggs",
        "viscosity_correlation": "Beggs_Robinson",
    },
    "gas": {
        "gor": 50000.0,
        "gas_gravity": 0.70,
        "condensate_gravity": 50.0,
        "water_salinity": 10000.0,
    },
    "condensate": {
        "gor": 10000.0,
        "api_gravity": 45.0,
        "gas_gravity": 0.68,
        "water_salinity": 10000.0,
    },
    "water": {
        "gor": 0.0,
        "water_salinity": 30000.0,
    },
}

# Hydrostatic pressure gradient (psi/ft) for reservoir pressure estimation
HYDROSTATIC_GRADIENT_PSI_PER_FT = 0.433

# Default tubing/casing dimensions (inches)
DEFAULT_TUBING_OD = 3.5
DEFAULT_TUBING_ID = 2.992
DEFAULT_TUBING_ROUGHNESS = 0.0006
DEFAULT_CASING_OD = 7.0
DEFAULT_CASING_ID = 6.184

# Default wellhead conditions
DEFAULT_WHP_PSIA = 200.0
DEFAULT_WHT_F = 100.0

# Geothermal gradient (F/ft)
GEOTHERMAL_GRADIENT_F_PER_FT = 0.015
SURFACE_TEMPERATURE_F = 60.0


# ============================================================================
# Compatibility validation
# ============================================================================

# IPR models only valid for horizontal wells
HORIZONTAL_IPR_MODELS = {
    IPRModel.HORIZONTAL_PI_JOSHI,
    IPRModel.HORIZONTAL_PI_BABU_ODEH,
    IPRModel.HORIZONTAL_PI_KUCHUK,
}

# IPR models only valid for gas wells
GAS_ONLY_IPR_MODELS = {
    IPRModel.FETKOVITCH,
}

# VLP correlations only valid for gas wells
GAS_ONLY_VLP = {
    VLPCorrelation.GRAY,
}

# Lift methods not valid for injectors
PRODUCER_ONLY_LIFT = {
    LiftMethod.ESP,
    LiftMethod.GAS_LIFT_CONTINUOUS,
    LiftMethod.GAS_LIFT_INTERMITTENT,
    LiftMethod.ROD_PUMP,
    LiftMethod.JET_PUMP,
    LiftMethod.PCP,
    LiftMethod.PLUNGER_LIFT,
}


def _validate_ipr_compatibility(
    ipr_model: IPRModel,
    well_trajectory: str,
    fluid: str,
) -> None:
    """Validate IPR model is compatible with well trajectory and fluid."""
    if ipr_model in HORIZONTAL_IPR_MODELS and well_trajectory != "horizontal":
        raise IncompatibleComponentError(
            error_message=(
                f"IPR model '{ipr_model.value}' requires a horizontal well, "
                f"but well trajectory is '{well_trajectory}'."
            ),
            suggested_action="Use a horizontal well trajectory or choose a different IPR model (Vogel, PI_Entry, Darcy).",
            original_params={"ipr_model": ipr_model.value, "well_trajectory": well_trajectory},
        )
    if ipr_model in GAS_ONLY_IPR_MODELS and fluid == "oil":
        raise IncompatibleComponentError(
            error_message=(
                f"IPR model '{ipr_model.value}' is designed for gas wells, "
                f"but fluid type is '{fluid}'."
            ),
            suggested_action="Use Vogel or PI_Entry for oil wells.",
            original_params={"ipr_model": ipr_model.value, "fluid": fluid},
        )


def _validate_vlp_compatibility(
    vlp_correlation: VLPCorrelation,
    fluid: str,
) -> None:
    """Validate VLP correlation is compatible with fluid type."""
    if vlp_correlation in GAS_ONLY_VLP and fluid == "oil":
        raise IncompatibleComponentError(
            error_message=(
                f"VLP correlation '{vlp_correlation.value}' is designed for gas wells, "
                f"but fluid type is '{fluid}'."
            ),
            suggested_action="Use Hagedorn_Brown or Beggs_Brill for oil wells.",
            original_params={"vlp_correlation": vlp_correlation.value, "fluid": fluid},
        )


def _validate_lift_compatibility(
    lift_method: LiftMethod,
    well_type: str,
) -> None:
    """Validate lift method is compatible with well type."""
    if lift_method in PRODUCER_ONLY_LIFT and well_type == "injector":
        raise IncompatibleComponentError(
            error_message=(
                f"Lift method '{lift_method.value}' is not applicable to injector wells."
            ),
            suggested_action="Injector wells typically use natural flow. Remove lift method.",
            original_params={"lift_method": lift_method.value, "well_type": well_type},
        )


# ============================================================================
# Helper functions for default resolution
# ============================================================================


def _get_default_ipr(fluid: FluidType, trajectory: WellTrajectory) -> IPRModel:
    """Select default IPR model based on fluid and trajectory."""
    if trajectory == WellTrajectory.HORIZONTAL:
        return IPRModel.HORIZONTAL_PI_JOSHI
    if fluid == FluidType.GAS:
        return IPRModel.FETKOVITCH
    return IPRModel.VOGEL


def _get_default_vlp(trajectory: WellTrajectory, fluid: FluidType) -> VLPCorrelation:
    """Select default VLP correlation based on trajectory and fluid."""
    if fluid == FluidType.GAS:
        return VLPCorrelation.GRAY
    if trajectory in (WellTrajectory.HORIZONTAL, WellTrajectory.DEVIATED):
        return VLPCorrelation.BEGGS_BRILL
    return VLPCorrelation.HAGEDORN_BROWN


def _get_default_completion(trajectory: WellTrajectory) -> CompletionType:
    """Select default completion type based on trajectory."""
    if trajectory == WellTrajectory.HORIZONTAL:
        return CompletionType.SLOTTED_LINER
    return CompletionType.CASED_PERFORATED


def _estimate_reservoir_pressure(depth_m: float) -> float:
    """Estimate reservoir pressure from hydrostatic gradient.

    Args:
        depth_m: Well depth in meters.

    Returns:
        Estimated reservoir pressure in psia.
    """
    depth_ft = depth_m * 3.28084
    return round(HYDROSTATIC_GRADIENT_PSI_PER_FT * depth_ft + 14.7, 1)


def _estimate_reservoir_temperature(depth_m: float) -> float:
    """Estimate reservoir temperature from geothermal gradient.

    Args:
        depth_m: Well depth in meters.

    Returns:
        Estimated reservoir temperature in degF.
    """
    depth_ft = depth_m * 3.28084
    return round(SURFACE_TEMPERATURE_F + GEOTHERMAL_GRADIENT_F_PER_FT * depth_ft, 1)


def _estimate_tvd_from_depth(depth_m: float, trajectory: WellTrajectory) -> float:
    """Estimate TVD from measured depth based on trajectory type."""
    if trajectory == WellTrajectory.VERTICAL:
        return depth_m
    elif trajectory == WellTrajectory.HORIZONTAL:
        return round(depth_m * 0.9, 1)
    elif trajectory == WellTrajectory.DEVIATED:
        return round(depth_m * 0.95, 1)
    else:
        return round(depth_m * 0.85, 1)


# ============================================================================
# Result dataclasses
# ============================================================================


@dataclass
class CreateWellResult:
    """Result from creating a PROSPER well."""

    model_path: str
    configured_parameters: dict
    defaults_applied: dict
    script: str
    metadata: ExecutionMetadata


@dataclass
class ComponentResult:
    """Result from adding/modifying a component."""

    model_path: str
    component_added: str
    component_value: str
    script_fragment: str
    model_summary: dict
    metadata: ExecutionMetadata


@dataclass
class NodalAnalysisResult:
    """Result from running nodal analysis."""

    model_path: str
    script: str
    rate_unit: str
    pressure_unit: str
    operating_point_rate: Optional[float]
    operating_point_pressure: Optional[float]
    metadata: ExecutionMetadata


@dataclass
class SensitivityResult:
    """Result from running sensitivity analysis."""

    model_path: str
    variable: str
    results: list[dict]
    script: str
    metadata: ExecutionMetadata


# ============================================================================
# Tool functions
# ============================================================================


async def create_prosper_well(
    params: CreateWellParams,
    session: Any = None,
    adapter: Any = None,
) -> CreateWellResult:
    """Create a new PROSPER well model with all 7 sections configured.

    Generates ~40+ OpenServer commands covering:
    1. System Summary (well type, fluid, trajectory, lift method)
    2. PVT (correlations, API, GOR, gas gravity, temperature)
    3. Equipment (tubing, casing, deviation survey)
    4. IPR (model, reservoir pressure, skin, horizontal params)
    5. VLP (correlation selection)
    6. Artificial Lift (ESP frequency, gas lift params)
    7. System Analysis (nodal analysis conditions)

    Args:
        params: Well creation parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        CreateWellResult with complete script and applied defaults.
    """
    start_time = time.perf_counter()

    model_path = f"PROSPER_{params.well_type.value}_{params.fluid.value}.Out"
    defaults_applied: dict = {}
    configured_parameters: dict = {
        "well_type": params.well_type.value,
        "fluid": params.fluid.value,
        "depth": params.depth,
    }

    # Resolve defaults
    fluid_defaults = FLUID_DEFAULTS.get(params.fluid.value, {})

    # GOR
    gor = params.gor
    if gor is None:
        gor = fluid_defaults.get("gor", 300.0)
        defaults_applied["gor"] = gor

    # Skin
    skin = params.skin
    if skin is None:
        skin = 0.0
        defaults_applied["skin"] = skin

    # Reservoir pressure
    reservoir_pressure = params.reservoir_pressure
    if reservoir_pressure is None:
        reservoir_pressure = _estimate_reservoir_pressure(params.depth)
        defaults_applied["reservoir_pressure"] = reservoir_pressure

    # Reservoir temperature
    reservoir_temp = _estimate_reservoir_temperature(params.depth)
    defaults_applied["reservoir_temperature"] = reservoir_temp

    # TVD
    tvd = params.tvd
    if tvd is None:
        tvd = _estimate_tvd_from_depth(params.depth, params.well_trajectory)
        if params.well_trajectory != WellTrajectory.VERTICAL:
            defaults_applied["tvd"] = tvd

    # IPR model
    ipr_model = params.ipr_model
    if ipr_model is None:
        ipr_model = _get_default_ipr(params.fluid, params.well_trajectory)
        defaults_applied["ipr_model"] = ipr_model.value
    else:
        _validate_ipr_compatibility(ipr_model, params.well_trajectory.value, params.fluid.value)

    # VLP correlation
    vlp_correlation = params.vlp_correlation
    if vlp_correlation is None:
        vlp_correlation = _get_default_vlp(params.well_trajectory, params.fluid)
        defaults_applied["vlp_correlation"] = vlp_correlation.value
    else:
        _validate_vlp_compatibility(vlp_correlation, params.fluid.value)

    # Completion type
    completion_type = params.completion_type
    if completion_type is None:
        completion_type = _get_default_completion(params.well_trajectory)
        defaults_applied["completion_type"] = completion_type.value

    # Lift method
    lift_method = params.lift_method
    if lift_method is not None:
        _validate_lift_compatibility(lift_method, params.well_type.value)
        configured_parameters["lift_method"] = lift_method.value
    else:
        lift_method = LiftMethod.NONE

    # Frequency (ESP)
    frequency = params.frequency
    if frequency is not None:
        configured_parameters["frequency"] = frequency

    # Lateral length (horizontal)
    lateral_length = params.lateral_length
    if lateral_length is not None:
        configured_parameters["lateral_length"] = lateral_length

    # API gravity
    api_gravity = fluid_defaults.get("api_gravity", 30.0)
    gas_gravity = fluid_defaults.get("gas_gravity", 0.65)
    water_salinity = fluid_defaults.get("water_salinity", 10000.0)

    # Horizontal perm ratio
    horizontal_perm_ratio = params.horizontal_perm_ratio
    if horizontal_perm_ratio is None and params.well_trajectory == WellTrajectory.HORIZONTAL:
        horizontal_perm_ratio = 0.1
        defaults_applied["horizontal_perm_ratio"] = horizontal_perm_ratio

    # =========================================================================
    # Generate OpenServer commands (~40+ commands)
    # =========================================================================
    commands: list[OpenServerCommand] = []

    # --- Section 1: System Summary ---
    # Start PROSPER application via OpenServer
    commands.append(
        OpenServerCommand(method="DoCmd", target='PROSPER.START("")')
    )
    # Create a new file and save with the desired path
    commands.append(
        OpenServerCommand(method="DoCmd", target="PROSPER.NEWFILE()")
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.WellType",
            value=WELL_TYPE_MAP[params.well_type],
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.Fluid",
            value=FLUID_TYPE_MAP[params.fluid],
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.FlowType",
            value="0",  # 0=Tubing flow (default)
        )
    )
    # Inflow Type: 0 = Single Branch, 1 = Multi-Lateral
    inflow_type_code = INFLOW_TYPE_MAP[params.well_trajectory]
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.InflowType",
            value=inflow_type_code,
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.LiftMethod",
            value=LIFT_METHOD_MAP[lift_method],
        )
    )
    # Completion uses two separate variables
    completion_settings = COMPLETION_TYPE_TO_SETTINGS[completion_type]
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.Completion",
            value=completion_settings["completion"],
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.GravelPack",
            value=completion_settings["gravelpack"],
        )
    )

    # --- Section 2: PVT ---
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.Api",
            value=str(api_gravity),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.GrvGas",
            value=str(gas_gravity),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.SolGOR",
            value=str(gor),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.Wgr",
            value="1.02",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.Tres",
            value=str(reservoir_temp),
        )
    )
    # PVT correlation selection
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.PVTmodel",
            value="0",  # 0 = Black Oil correlations
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.PbCorr",
            value="1",  # Standing
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.H2S",
            value="0",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.CO2",
            value="0",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.PVT.Input.N2",
            value="0",
        )
    )

    # --- Section 3: Equipment (Downhole) ---
    depth_ft = params.depth * 3.28084
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA.COUNT",
            value="1",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].LABEL",
            value="Tubing",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].TYPE",
            value="0",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].DEPTH",
            value=str(round(depth_ft, 1)),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].TID",
            value=str(DEFAULT_TUBING_ID),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].TIR",
            value=str(DEFAULT_TUBING_ROUGHNESS),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].TOD",
            value=str(DEFAULT_TUBING_OD),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].TOR",
            value=str(DEFAULT_TUBING_ROUGHNESS),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].CID",
            value=str(DEFAULT_CASING_ID),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].CIR",
            value=str(DEFAULT_TUBING_ROUGHNESS),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].COD",
            value=str(DEFAULT_CASING_OD),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.EQP.DOWN.DATA[0].COR",
            value=str(DEFAULT_TUBING_ROUGHNESS),
        )
    )

    # 3b: Deviation survey (Devn section)
    if params.well_trajectory == WellTrajectory.VERTICAL:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.DEVN.DATA.COUNT",
                value="2",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[0].Md",
                value="0",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[0].Tvd",
                value="0",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[1].Md",
                value=str(round(depth_ft, 1)),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[1].Tvd",
                value=str(round(depth_ft, 1)),
            )
        )
    else:
        # Non-vertical: 3-point survey
        tvd_ft = tvd * 3.28084
        kop_ft = tvd_ft * 0.7
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.DEVN.DATA.COUNT",
                value="3",
            )
        )
        commands.append(
            OpenServerCommand(method="DoSet", target="PROSPER.SIN.EQP.Devn.Data[0].Md", value="0")
        )
        commands.append(
            OpenServerCommand(method="DoSet", target="PROSPER.SIN.EQP.Devn.Data[0].Tvd", value="0")
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[1].Md",
                value=str(round(kop_ft, 1)),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[1].Tvd",
                value=str(round(kop_ft, 1)),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[2].Md",
                value=str(round(depth_ft, 1)),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.EQP.Devn.Data[2].Tvd",
                value=str(round(tvd_ft, 1)),
            )
        )

    # --- Section 4: IPR ---
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.IPR.Single.IprModel",
            value=IPR_MODEL_NAME_MAP[ipr_model],
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.IPR.Single.Pres",
            value=str(reservoir_pressure),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.IPR.Single.Temp",
            value=str(reservoir_temp),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.IPR.Single.Skin",
            value=str(skin),
        )
    )

    # Horizontal-specific IPR parameters
    if params.well_trajectory == WellTrajectory.HORIZONTAL:
        if lateral_length is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.SIN.IPR.Single.HzLength",
                    value=str(lateral_length),
                )
            )
        if horizontal_perm_ratio is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.SIN.IPR.Single.HzPermRatio",
                    value=str(horizontal_perm_ratio),
                )
            )

    # Reservoir thickness (used by Darcy, Jones, and other IPR models)
    reservoir_thickness = params.reservoir_thickness
    if reservoir_thickness is not None:
        thickness_ft = reservoir_thickness * 3.28084
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.IPR.Single.Thickness",
                value=str(round(thickness_ft, 1)),
            )
        )
        configured_parameters["reservoir_thickness"] = reservoir_thickness

    # --- Section 5: VLP ---
    # Use label-based selection (recommended by PETEX, indices may change)
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.ANL.VLP.TubingLabel",
            value=VLP_CORRELATION_LABEL_MAP[vlp_correlation],
        )
    )

    # --- Section 6: Artificial Lift ---
    if lift_method == LiftMethod.ESP:
        freq = frequency if frequency is not None else 60.0
        if frequency is None:
            defaults_applied["frequency"] = freq
        esp_depth = round(tvd * 3.28084 * 0.8, 1)  # 80% of TVD
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.ESP.Frequency",
                value=str(freq),
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.ESP.Depth",
                value=str(esp_depth),
            )
        )
    elif lift_method in (LiftMethod.GAS_LIFT_CONTINUOUS, LiftMethod.GAS_LIFT_INTERMITTENT):
        gl_depth = round(tvd * 3.28084 * 0.8, 1)
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="PROSPER.SIN.GL.InjDepth",
                value=str(gl_depth),
            )
        )

    # --- Section 7: System Analysis conditions ---
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.ANL.SYS.Pres",
            value=str(DEFAULT_WHP_PSIA),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.ANL.SYS.Temp",
            value=str(DEFAULT_WHT_F),
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.ANL.SYS.NodePosition",
            value="0",  # 0 = Bottom hole
        )
    )

    # Save file with the model path
    commands.append(
        OpenServerCommand(method="DoCmd", target=f"PROSPER.SAVEFILE({model_path})")
    )

    # Shutdown PROSPER to free license (only 1 instance allowed at a time)
    commands.append(
        OpenServerCommand(method="DoCmd", target="PROSPER.SHUTDOWN()")
    )

    # =========================================================================
    # Generate script
    # =========================================================================
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Create PROSPER Well Model",
        commands=commands,
        description=(
            f"{params.well_type.value} {params.fluid.value} well, "
            f"{params.well_trajectory.value}, depth={params.depth}m"
        ),
    )

    duration = time.perf_counter() - start_time
    metadata = ExecutionMetadata(
        duration_seconds=round(duration, 6),
        model_file_path=model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Execute via adapter if provided
    if adapter is not None:
        await adapter.execute(commands)

    # Update session context
    if session is not None:
        session.fluid_type = params.fluid.value
        session.well_type = params.well_type.value
        session.well_trajectory = params.well_trajectory.value
        session.active_models[model_path] = {
            "created_by": "create_prosper_well",
            "well_type": params.well_type.value,
            "fluid": params.fluid.value,
            "well_trajectory": params.well_trajectory.value,
        }

    return CreateWellResult(
        model_path=model_path,
        configured_parameters=configured_parameters,
        defaults_applied=defaults_applied,
        script=script,
        metadata=metadata,
    )


async def add_ipr_model(
    params: AddIPRParams,
    session: Any = None,
    adapter: Any = None,
) -> ComponentResult:
    """Add or modify the IPR model on an existing PROSPER well.

    Validates compatibility with well trajectory and fluid type before
    generating the OpenServer commands.

    Args:
        params: IPR model parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        ComponentResult with script fragment and model summary.
    """
    start_time = time.perf_counter()

    # Get well context from session for validation
    well_trajectory = "vertical"
    fluid = "oil"
    if session is not None and params.model_path in session.active_models:
        model_info = session.active_models[params.model_path]
        well_trajectory = model_info.get("well_trajectory", "vertical")
        fluid = model_info.get("fluid", "oil")

    # Validate compatibility
    _validate_ipr_compatibility(params.ipr_model, well_trajectory, fluid)

    # Generate commands
    commands: list[OpenServerCommand] = []
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f"PROSPER.OPENFILE({params.model_path})",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.IPR.Single.IprModel",
            value=IPR_MODEL_NAME_MAP[params.ipr_model],
        )
    )
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    # Generate script fragment
    script_gen = ScriptGenerator()
    script_fragment = script_gen.generate_fragment(
        commands, description=f"Set IPR model to {params.ipr_model.value}"
    )

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=params.model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Update session
    model_summary = {"ipr_model": params.ipr_model.value}
    if session is not None and params.model_path in session.active_models:
        session.active_models[params.model_path]["ipr_model"] = params.ipr_model.value

    return ComponentResult(
        model_path=params.model_path,
        component_added="ipr_model",
        component_value=params.ipr_model.value,
        script_fragment=script_fragment,
        model_summary=model_summary,
        metadata=metadata,
    )


async def add_vlp_correlation(
    params: AddVLPParams,
    session: Any = None,
    adapter: Any = None,
) -> ComponentResult:
    """Add or modify the VLP correlation on an existing PROSPER well.

    Validates compatibility with fluid type before generating commands.

    Args:
        params: VLP correlation parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        ComponentResult with script fragment and model summary.
    """
    start_time = time.perf_counter()

    # Get well context from session for validation
    fluid = "oil"
    if session is not None and params.model_path in session.active_models:
        model_info = session.active_models[params.model_path]
        fluid = model_info.get("fluid", "oil")

    # Validate compatibility
    _validate_vlp_compatibility(params.vlp_correlation, fluid)

    # Generate commands
    commands: list[OpenServerCommand] = []
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f"PROSPER.OPENFILE({params.model_path})",
        )
    )
    # Use label-based selection (recommended by PETEX)
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.ANL.VLP.TubingLabel",
            value=VLP_CORRELATION_LABEL_MAP[params.vlp_correlation],
        )
    )
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    # Generate script fragment
    script_gen = ScriptGenerator()
    script_fragment = script_gen.generate_fragment(
        commands, description=f"Set VLP correlation to {params.vlp_correlation.value}"
    )

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=params.model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Update session
    model_summary = {"vlp_correlation": params.vlp_correlation.value}
    if session is not None and params.model_path in session.active_models:
        session.active_models[params.model_path]["vlp_correlation"] = params.vlp_correlation.value

    return ComponentResult(
        model_path=params.model_path,
        component_added="vlp_correlation",
        component_value=params.vlp_correlation.value,
        script_fragment=script_fragment,
        model_summary=model_summary,
        metadata=metadata,
    )


async def add_lift_method(
    params: AddLiftParams,
    session: Any = None,
    adapter: Any = None,
) -> ComponentResult:
    """Add or modify the artificial lift configuration.

    Validates compatibility with well type before generating commands.

    Args:
        params: Lift method parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        ComponentResult with script fragment and model summary.
    """
    start_time = time.perf_counter()

    # Get well context from session for validation
    well_type = "producer"
    if session is not None and params.model_path in session.active_models:
        model_info = session.active_models[params.model_path]
        well_type = model_info.get("well_type", "producer")

    # Validate compatibility
    _validate_lift_compatibility(params.lift_method, well_type)

    # Generate commands
    commands: list[OpenServerCommand] = []
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f"PROSPER.OPENFILE({params.model_path})",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.LiftMethod",
            value=LIFT_METHOD_MAP[params.lift_method],
        )
    )

    model_summary: dict = {"lift_method": params.lift_method.value}

    # ESP-specific parameters
    if params.lift_method == LiftMethod.ESP:
        if params.frequency is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.SIN.ESP.Frequency",
                    value=str(params.frequency),
                )
            )
            model_summary["frequency"] = params.frequency

    # Gas lift-specific parameters
    if params.lift_method in (LiftMethod.GAS_LIFT_CONTINUOUS, LiftMethod.GAS_LIFT_INTERMITTENT):
        if params.injection_depth is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.SIN.GL.InjDepth",
                    value=str(params.injection_depth),
                )
            )
            model_summary["injection_depth"] = params.injection_depth
        if params.gas_rate is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.SIN.GL.Rate",
                    value=str(params.gas_rate),
                )
            )
            model_summary["gas_rate"] = params.gas_rate

    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    # Generate script fragment
    script_gen = ScriptGenerator()
    script_fragment = script_gen.generate_fragment(
        commands, description=f"Set lift method to {params.lift_method.value}"
    )

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=params.model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Update session
    if session is not None and params.model_path in session.active_models:
        session.active_models[params.model_path]["lift_method"] = params.lift_method.value

    return ComponentResult(
        model_path=params.model_path,
        component_added="lift_method",
        component_value=params.lift_method.value,
        script_fragment=script_fragment,
        model_summary=model_summary,
        metadata=metadata,
    )


async def add_completion(
    params: AddCompletionParams,
    session: Any = None,
    adapter: Any = None,
) -> ComponentResult:
    """Add or modify the completion configuration.

    Args:
        params: Completion parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        ComponentResult with script fragment and model summary.
    """
    start_time = time.perf_counter()

    # Generate commands
    commands: list[OpenServerCommand] = []
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f"PROSPER.OPENFILE({params.model_path})",
        )
    )
    # Completion uses two variables in PROSPER
    completion_settings = COMPLETION_TYPE_TO_SETTINGS[params.completion_type]
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.Completion",
            value=completion_settings["completion"],
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="PROSPER.SIN.SUM.GravelPack",
            value=completion_settings["gravelpack"],
        )
    )
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    # Generate script fragment
    script_gen = ScriptGenerator()
    script_fragment = script_gen.generate_fragment(
        commands, description=f"Set completion to {params.completion_type.value}"
    )

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=params.model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    model_summary = {"completion_type": params.completion_type.value}

    return ComponentResult(
        model_path=params.model_path,
        component_added="completion_type",
        component_value=params.completion_type.value,
        script_fragment=script_fragment,
        model_summary=model_summary,
        metadata=metadata,
    )


async def run_nodal_analysis(
    params: NodalAnalysisParams,
    session: Any = None,
    adapter: Any = None,
) -> NodalAnalysisResult:
    """Run nodal analysis on a PROSPER well model.

    Generates a script that:
    1. Opens the model
    2. Sets WHP values if a range is provided
    3. Sets ESP frequency values if a range is provided
    4. Runs the system calculation
    5. Retrieves operating point (rate and pressure)

    For ranges, generates a loop with one CALC per value.

    Args:
        params: Nodal analysis parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        NodalAnalysisResult with script and placeholder operating point.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({params.model_path})")
    )

    operating_point_rate: Optional[float] = None
    operating_point_pressure: Optional[float] = None

    if params.whp_range:
        # Run for each WHP value
        for whp in params.whp_range:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.ANL.SYS.Pres",
                    value=str(whp),
                )
            )
            commands.append(
                OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.SYS.CALC")
            )
            commands.append(
                OpenServerCommand(
                    method="DoGet",
                    target="PROSPER.OUT.SYS.Results[0].Sol.OilRate",
                )
            )
            commands.append(
                OpenServerCommand(
                    method="DoGet",
                    target="PROSPER.OUT.SYS.Results[0].Sol.Pres",
                )
            )
    elif params.frequency_range:
        # Run for each frequency value
        for freq in params.frequency_range:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="PROSPER.SIN.ESP.Frequency",
                    value=str(freq),
                )
            )
            commands.append(
                OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.SYS.CALC")
            )
            commands.append(
                OpenServerCommand(
                    method="DoGet",
                    target="PROSPER.OUT.SYS.Results[0].Sol.OilRate",
                )
            )
            commands.append(
                OpenServerCommand(
                    method="DoGet",
                    target="PROSPER.OUT.SYS.Results[0].Sol.Pres",
                )
            )
    else:
        # Single calculation at current settings
        commands.append(
            OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.SYS.CALC")
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].Sol.OilRate",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].Sol.Pres",
            )
        )
        # Get IPR and VLP curve data
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].IPR.Data",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].VLP.Data",
            )
        )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Run Nodal Analysis",
        commands=commands,
        description=f"Nodal analysis: {params.model_path}",
    )

    # Execute via adapter if provided
    if adapter is not None:
        results = await adapter.execute(commands)
        # Parse results: after OPENFILE, CALC, OilRate, Pres
        if len(results) >= 4:
            oil_rate_result = results[2]
            pres_result = results[3]
            if oil_rate_result.value:
                operating_point_rate = float(oil_rate_result.value)
            if pres_result.value:
                operating_point_pressure = float(pres_result.value)

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=params.model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return NodalAnalysisResult(
        model_path=params.model_path,
        script=script,
        rate_unit="STB/day",
        pressure_unit="psia",
        operating_point_rate=operating_point_rate,
        operating_point_pressure=operating_point_pressure,
        metadata=metadata,
    )


async def run_sensitivity(
    params: SensitivityParams,
    session: Any = None,
    adapter: Any = None,
) -> SensitivityResult:
    """Run sensitivity analysis on well parameters.

    Generates a script that iterates over each parameter value:
    1. Opens the model
    2. For each value: sets the parameter, runs CALC, retrieves results
    3. Returns results for each value

    Args:
        params: Sensitivity parameters.
        session: Optional session context for state tracking.
        adapter: Optional OpenServer adapter for live execution.

    Returns:
        SensitivityResult with script and results for each value.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Resolve the OpenServer path for the variable
    variable_path = SENSITIVITY_VARIABLE_MAP.get(params.variable)
    if variable_path is None:
        variable_path = f"PROSPER.SIN.{params.variable}"

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({params.model_path})")
    )

    # For each value: set, calculate, retrieve
    for value in params.values:
        commands.append(
            OpenServerCommand(method="DoSet", target=variable_path, value=str(value))
        )
        commands.append(
            OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.SYS.CALC")
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].Sol.LiqRate",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].Sol.OilRate",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].Sol.WatRate",
            )
        )
        commands.append(
            OpenServerCommand(
                method="DoGet",
                target="PROSPER.OUT.SYS.Results[0].Sol.Pres",
            )
        )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Sensitivity Analysis: {params.variable}",
        commands=commands,
        description=f"Sensitivity on {params.variable}: {len(params.values)} values",
    )

    # Build results (placeholder or from adapter)
    results: list[dict] = []

    if adapter is not None:
        exec_results = await adapter.execute(commands)
        # Parse: skip OPENFILE (index 0), then groups of 6 (DoSet, CALC, 4 DoGet)
        idx = 1
        for value in params.values:
            row: dict = {"variable_value": value}
            idx += 1  # DoSet
            idx += 1  # CALC
            if idx < len(exec_results) and exec_results[idx].value:
                row["liquid_rate"] = float(exec_results[idx].value)
            else:
                row["liquid_rate"] = 0.0
            idx += 1
            if idx < len(exec_results) and exec_results[idx].value:
                row["oil_rate"] = float(exec_results[idx].value)
            else:
                row["oil_rate"] = 0.0
            idx += 1
            if idx < len(exec_results) and exec_results[idx].value:
                row["water_rate"] = float(exec_results[idx].value)
            else:
                row["water_rate"] = 0.0
            idx += 1
            if idx < len(exec_results) and exec_results[idx].value:
                row["pressure"] = float(exec_results[idx].value)
            else:
                row["pressure"] = 0.0
            idx += 1
            results.append(row)
    else:
        # Script-only mode: generate placeholder results
        for value in params.values:
            results.append({
                "variable_value": value,
                "liquid_rate": 0.0,
                "oil_rate": 0.0,
                "water_rate": 0.0,
                "pressure": 0.0,
            })

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=params.model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return SensitivityResult(
        model_path=params.model_path,
        variable=params.variable,
        results=results,
        script=script,
        metadata=metadata,
    )


async def export_prosper_results(
    model_path: str,
    export_format: ExportFormat,
    session: Any = None,
) -> dict:
    """Export PROSPER results to Excel, CSV, or JSON.

    Generates a script that:
    1. Opens the model
    2. Retrieves key results (operating point, IPR/VLP data)
    3. Formats output for the requested format

    Args:
        model_path: Path to the PROSPER model file.
        export_format: Output format (csv, excel, json).
        session: Optional session context.

    Returns:
        Dictionary with file_path, format, script, and metadata.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})")
    )

    # Retrieve results
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="PROSPER.OUT.SYS.Results[0].Sol.OilRate",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="PROSPER.OUT.SYS.Results[0].Sol.GasRate",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="PROSPER.OUT.SYS.Results[0].Sol.WatRate",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="PROSPER.OUT.SYS.Results[0].Sol.Pres",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="PROSPER.OUT.SYS.Results[0].Sol.LiqRate",
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Export PROSPER Results",
        commands=commands,
        description=f"Export results to {export_format.value}",
    )

    # Determine output file path
    base_name = model_path.replace(".Out", "").replace(".out", "")
    ext_map = {
        ExportFormat.CSV: ".csv",
        ExportFormat.EXCEL: ".xlsx",
        ExportFormat.JSON: ".json",
    }
    output_ext = ext_map.get(export_format, ".csv")
    output_path = f"{base_name}_results{output_ext}"

    metadata = ExecutionMetadata(
        duration_seconds=round(time.perf_counter() - start_time, 6),
        model_file_path=model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return {
        "model_path": model_path,
        "format": export_format.value,
        "file_path": output_path,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }
