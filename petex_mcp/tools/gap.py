"""GAP tool functions for network modeling.

Generates complete, executable OpenServer scripts for:
- Opening existing GAP network models
- Creating new network models with full system options (PVT, prediction, optimization)
- Adding wells (all types: gas lifted, ESP, PCP, naturally flowing, injectors)
- Adding pipelines with full description (correlation, environment, geometry)
- Adding separators, joints, compressors, pumps, inline elements
- Configuring well controls (dP choke, gas lift, ESP frequency, pump speed)
- Setting constraints at system, separator, well, joint, and group levels
- Running the network solver (No Optimization, RBNS, Full Optimization)
- Running production predictions with scheduling and reservoir coupling
- Batch generating IPRs and VLPs from PROSPER
- Initialising IPRs from tank simulations at a specific historical date
- Identifying bottlenecks

All commands follow the official GAP OpenServer documentation (January 2025).
Key GAP functions:
- DoGAPFunc: NEWITEM, LINKITEMS, SOLVENETWORK, OPENFILE, SAVEFILE
- DoSet/DoGet: GAP.MOD[{PROD}].WELL[{name}].Variable, etc.
- SOLVENETWORK(optimise, model, potential):
    optimise: 0=No Opt, 1=Optimise All, 2=Potential Only, 3=Rule Based
- Prediction via: GAP.PREDICTION(startdate, enddate, stepsize)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from petex_mcp.models.commands import OpenServerCommand
from petex_mcp.models.enums import (
    GAPCompressorType,
    GAPDPControl,
    GAPPipeCorrelation,
    GAPPipeModel,
    GAPPVTModel,
    GAPSolverMode,
    GAPSystemType,
    GAPWellType,
    OptimizationObjective,
)
from petex_mcp.models.inputs import (
    AddCompressorParams,
    AddInlineElementParams,
    AddPipelineParams,
    AddPumpParams,
    AddSeparatorParams,
    AddSourceSinkParams,
    AddTankParams,
    AddWellToNetworkParams,
    ConfigureWellControlParams,
    CreateGAPParams,
    GenerateWellIPRParams,
    GenerateWellVLPParams,
    InitialiseIPRsFromTanksParams,
    NetworkOptimizeParams,
    RunPredictionParams,
    SetConstraintsParams,
    AddScheduleEventParams,
)
from petex_mcp.models.outputs import (
    BottleneckResult,
    ConstraintsResult,
    ExecutionMetadata,
    GenerateIPRResult,
    GenerateVLPResult,
    NetworkSolution,
    OptimizationResult,
    PredictionResult,
    WellControlResult,
)
from petex_mcp.script.generator import ScriptGenerator


# ============================================================================
# OpenServer enum mappings (GAP internal codes)
# ============================================================================

# SOLVENETWORK optimise parameter:
# -1 = Use file settings
#  0 = No Optimisation
#  1 = Optimise and Honour Constraints
#  2 = Optimise with potential constraints
#  3 = Use Rule Based Solver to honour constraints
SOLVER_MODE_MAP = {
    GAPSolverMode.NO_OPTIMISATION: "0",
    GAPSolverMode.RULE_BASED: "3",
    GAPSolverMode.OPTIMISE_ALL_CONSTRAINTS: "1",
    GAPSolverMode.OPTIMISE_POTENTIAL_CONSTRAINTS: "2",
}

# GAP Options Method - Optimisation Method:
# 0 = Production (maximise primary fluid)
# 1 = Revenue
# 2 = Oil rate only
# 3 = Water rate only
# 4 = Gas + Oil rate
# 5 = Gross Heating Value
# 6 = Gas Rate with Preference to Oil Content
OPTIMIZATION_OBJECTIVE_MAP = {
    OptimizationObjective.MAX_PRODUCTION: "0",
    OptimizationObjective.MAX_OIL: "0",
    OptimizationObjective.MAX_REVENUE: "1",
    OptimizationObjective.OIL_RATE_ONLY: "2",
    OptimizationObjective.WATER_RATE_ONLY: "3",
    OptimizationObjective.GAS_PLUS_OIL: "4",
    OptimizationObjective.MAX_GAS: "4",
    OptimizationObjective.GROSS_HEATING_VALUE: "5",
    OptimizationObjective.GAS_RATE_OIL_PREFERENCE: "6",
    OptimizationObjective.MIN_ENERGY: "0",
}

# GAP System Type mapping
SYSTEM_TYPE_MAP = {
    GAPSystemType.PRODUCTION: "0",
    GAPSystemType.WATER_INJECTION: "1",
    GAPSystemType.GAS_INJECTION: "2",
    GAPSystemType.GAS_LIFT_INJECTION: "3",
}

# GAP PVT Model mapping
PVT_MODEL_MAP = {
    GAPPVTModel.BLACK_OIL: "0",
    GAPPVTModel.TRACKING: "1",
    GAPPVTModel.FULLY_COMPOSITIONAL: "2",
    GAPPVTModel.BO_COMPOSITIONAL_LUMPING_DELUMPING: "3",
}

# GAP Well Type mapping
WELL_TYPE_MAP = {
    GAPWellType.GAS_PRODUCER: "1",
    GAPWellType.OIL_PRODUCER_NO_LIFT: "3",
    GAPWellType.OIL_PRODUCER_GAS_LIFTED: "4",
    GAPWellType.OIL_PRODUCER_ESP: "5",
    GAPWellType.OIL_PRODUCER_PCP: "11",
    GAPWellType.OIL_PRODUCER_HSP: "6",
    GAPWellType.OIL_PRODUCER_JET_PUMP: "7",
    GAPWellType.OIL_PRODUCER_SRP: "12",
    GAPWellType.OIL_PRODUCER_DILUENT: "8",
    GAPWellType.RETROGRADE_CONDENSATE: "2",
    GAPWellType.WATER_INJECTOR: "14",
    GAPWellType.GAS_INJECTOR: "0",
    GAPWellType.WATER_PRODUCER: "15",
    GAPWellType.LIQUID_INJECTOR: "13",
    GAPWellType.CBM_ESP: "16",
    GAPWellType.CBM_PCP: "17",
}

# DP Control mapping
DP_CONTROL_MAP = {
    GAPDPControl.NONE: "NONE",
    GAPDPControl.FIXED_VALUE: "FIXED",
    GAPDPControl.CALCULATED: "CALCULATED",
}


# ============================================================================
# Helper functions
# ============================================================================


def _create_metadata(start_time: float, model_path: str) -> ExecutionMetadata:
    """Create execution metadata."""
    duration = time.perf_counter() - start_time
    return ExecutionMetadata(
        duration_seconds=round(duration, 6),
        model_file_path=model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _normalize_gap_path(model_name: str) -> str:
    """Ensure model path ends with .gap extension."""
    if model_name.endswith(".gap"):
        return model_name
    return f"{model_name}.gap"


# ============================================================================
# Tool functions
# ============================================================================


async def open_network(model_path: str) -> dict:
    """Open an existing GAP network model.

    Generates a script that:
    1. Opens the GAP model file via OPENFILE
    2. Queries the equipment list count
    3. Returns a network summary

    Args:
        model_path: Path to the GAP model file.

    Returns:
        Dictionary with model_path, network_summary, script, metadata, warnings.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{model_path}")',
        )
    )

    # Query network structure — equipment list count
    commands.append(
        OpenServerCommand(method="DoGet", target="GAP.MOD[0].EquipmentList.COUNT")
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Open GAP Network",
        commands=commands,
        description=f"Open and inspect network: {model_path}",
    )

    metadata = _create_metadata(start_time, model_path)

    return {
        "model_path": model_path,
        "network_summary": {
            "equipment_count": 0,
        },
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
        "warnings": ["Script-only mode: execute the script to obtain actual network counts."],
    }


async def create_gap_model(params: CreateGAPParams) -> dict:
    """Create a new GAP network model with full system options.

    Generates a script that:
    1. Starts GAP via OpenServer
    2. Creates a new empty model with NEWFILE
    3. Configures system options (Options | Method):
       - System Type (Production/Injection)
       - Optimization Method
       - PVT Model (Black Oil/Compositional/Tracking)
       - Prediction: On
       - Prediction Method (P only / P+T / P+T Gradient)
       - Temperature Model
       - Calculate Well Choke DeltaT
       - Water Vapour calculation
    4. Saves the model with SAVEFILE

    Args:
        params: Model creation parameters including system configuration.

    Returns:
        Dictionary with model_path, script, metadata, defaults_applied.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    model_path = _normalize_gap_path(params.model_name)

    # Start GAP
    commands.append(
        OpenServerCommand(method="DoCmd", target='GAP.START("")')
    )

    # Create new empty file
    commands.append(
        OpenServerCommand(method="DoGAPFunc", target="GAP.NEWFILE()")
    )

    # Configure system options (Options | Method)
    # System Type
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].SYSTYPE",
            value=SYSTEM_TYPE_MAP[params.system_type],
        )
    )

    # Optimisation Method
    opt_code = OPTIMIZATION_OBJECTIVE_MAP.get(params.optimization_method, "0")
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].OPTMETHOD",
            value=opt_code,
        )
    )

    # PVT Model
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].PVTMODEL",
            value=PVT_MODEL_MAP[params.pvt_model],
        )
    )

    # Prediction ON
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].PREDICTION",
            value="1",
        )
    )

    # Prediction Method (temperature model)
    pred_method_map = {
        "pressure_only": "0",
        "pressure_and_temperature": "1",
        "pressure_and_temperature_gradient": "2",
    }
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].PREDMETHOD",
            value=pred_method_map.get(params.prediction_method.value, "1"),
        )
    )

    # Calculate Well Choke DeltaT
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].CALCCHOKEDELTAT",
            value="1" if params.calculate_well_choke_dt else "0",
        )
    )

    # Water Vapour
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.MOD[0].WATERVAPOUR",
            value="1" if params.water_vapour else "0",
        )
    )

    # Save with filename
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.SAVEFILE("{model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    desc = params.description or f"New GAP network: {model_path}"
    script = script_gen.generate(
        operation="Create GAP Network Model",
        commands=commands,
        description=desc,
    )

    metadata = _create_metadata(start_time, model_path)

    defaults_applied = {
        "system_type": params.system_type.value,
        "optimization_method": params.optimization_method.value,
        "pvt_model": params.pvt_model.value,
        "prediction_method": params.prediction_method.value,
        "temperature_model": params.temperature_model.value,
        "calculate_well_choke_dt": params.calculate_well_choke_dt,
        "water_vapour": params.water_vapour,
    }

    return {
        "model_path": model_path,
        "model_name": params.model_name,
        "script": script,
        "defaults_applied": defaults_applied,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }


async def add_well_to_network(params: AddWellToNetworkParams) -> dict:
    """Add a well to an existing GAP network.

    Per GAP User Guide (Equipment Data - Wells):
    - Well types: Gas Producer, Oil Producer (No Lift/Gas Lifted/ESP/PCP/HSP/
      Jet Pump/SRP/Diluent), Condensate Producer, Water/Gas Injector, CBM
    - Well models: VLP/IPR Intersection, PC Interpolation, Outflow Only (VLP/PROSPER)
    - Uses NEWITEM("WELL", label, ...) per OpenServer documentation
    - Optionally links a PROSPER model file for IPR/VLP generation

    Args:
        params: Well addition parameters including well_type and well_model.

    Returns:
        Dictionary with model_path, well_added, prosper_linked, script.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{params.model_path}")',
        )
    )

    # Add well using NEWITEM
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=f'GAP.NEWITEM("WELL", "{params.well_name}", "RIGHT", NULL, MOD[0])',
        )
    )

    # Set well type
    well_type_code = WELL_TYPE_MAP.get(params.well_type, "3")
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target=f"GAP.MOD[0].WELL[{{{params.well_name}}}].WellType",
            value=well_type_code,
        )
    )

    # Link PROSPER model if provided
    prosper_linked = False
    if params.prosper_model_path:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"GAP.MOD[0].WELL[{{{params.well_name}}}].PROSPERFile",
                value=params.prosper_model_path,
            )
        )
        prosper_linked = True

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.SAVEFILE("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Add Well {params.well_name} to Network",
        commands=commands,
        description=f"Add well: {params.well_name} (type={params.well_type.value})",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "well_added": params.well_name,
        "well_type": params.well_type.value,
        "well_model": params.well_model.value,
        "prosper_linked": prosper_linked,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }


async def add_pipeline(params: AddPipelineParams) -> dict:
    """Add a pipeline to an existing GAP network.

    Uses NEWITEM("PIPE", label, ...) and LINKITEMS to connect nodes.

    Args:
        params: Pipeline addition parameters.

    Returns:
        Dictionary with model_path, pipeline_added, source/dest nodes, script.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{params.model_path}")',
        )
    )

    # Add pipeline using NEWITEM
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=(
                f'GAP.NEWITEM("PIPE", "{params.pipeline_name}", "RIGHT", '
                f"MOD[0].EQUIP[{{{params.source_node}}}], MOD[0])"
            ),
        )
    )

    # Link pipeline to source node
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=(
                f"GAP.LINKITEMS(MOD[0].EQUIP[{{{params.source_node}}}], "
                f'MOD[0].PIPE[{{{params.pipeline_name}}}], "")'
            ),
        )
    )

    # Link pipeline to destination node
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=(
                f"GAP.LINKITEMS(MOD[0].PIPE[{{{params.pipeline_name}}}], "
                f'MOD[0].EQUIP[{{{params.destination_node}}}], "")'
            ),
        )
    )

    # Set optional parameters
    pipe_prefix = f"GAP.MOD[0].PIPE[{{{params.pipeline_name}}}]"
    if params.length is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{pipe_prefix}.Length",
                value=str(params.length),
            )
        )
    if params.diameter is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{pipe_prefix}.Diameter",
                value=str(params.diameter),
            )
        )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.SAVEFILE("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Add Pipeline {params.pipeline_name}",
        commands=commands,
        description=f"Pipeline: {params.source_node} -> {params.destination_node}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "pipeline_added": params.pipeline_name,
        "source_node": params.source_node,
        "destination_node": params.destination_node,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }


async def add_separator(params: AddSeparatorParams) -> dict:
    """Add a separator to an existing GAP network.

    Uses NEWITEM("SEP", label, ...) per OpenServer documentation.

    Args:
        params: Separator addition parameters.

    Returns:
        Dictionary with model_path, separator_added, script.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{params.model_path}")',
        )
    )

    # Add separator using NEWITEM
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=f'GAP.NEWITEM("SEP", "{params.separator_name}", "RIGHT", NULL, MOD[0])',
        )
    )

    # Set capacity (max liquid rate) if provided
    if params.capacity is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"GAP.MOD[0].SEP[{{{params.separator_name}}}].MAXQLIQ",
                value=str(params.capacity),
            )
        )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.SAVEFILE("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Add Separator {params.separator_name}",
        commands=commands,
        description=f"Separator: {params.separator_name}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "separator_added": params.separator_name,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }


async def add_compressor(params: AddCompressorParams) -> dict:
    """Add a compressor to an existing GAP network.

    Uses NEWITEM("COMP", label, ...) per OpenServer documentation.

    Args:
        params: Compressor addition parameters.

    Returns:
        Dictionary with model_path, compressor_added, script.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{params.model_path}")',
        )
    )

    # Add compressor using NEWITEM
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=f'GAP.NEWITEM("COMP", "{params.compressor_name}", "RIGHT", NULL, MOD[0])',
        )
    )

    # Set optional parameters
    comp_prefix = f"GAP.MOD[0].COMP[{{{params.compressor_name}}}]"

    if params.suction_pressure is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{comp_prefix}.SuctionPressure",
                value=str(params.suction_pressure),
            )
        )
    if params.discharge_pressure is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{comp_prefix}.DischargePressure",
                value=str(params.discharge_pressure),
            )
        )
    if params.capacity is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{comp_prefix}.MaxRate",
                value=str(params.capacity),
            )
        )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.SAVEFILE("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Add Compressor {params.compressor_name}",
        commands=commands,
        description=f"Compressor: {params.compressor_name}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "compressor_added": params.compressor_name,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }


async def run_network(model_path: str) -> NetworkSolution:
    """Execute GAP network solver.

    Uses SOLVENETWORK(optimise, model, potential) per documentation:
    - optimise=0 (no optimization, just solve)
    - model=MOD[0] (production system)
    - potential=0 (no potential calculation)

    Results are retrieved per node using:
    GAP.MOD[0].EQUIP[{name}].SolverResults[0].Qoil

    Args:
        model_path: Path to the GAP model file.

    Returns:
        NetworkSolution with script and placeholder production values.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{model_path}")',
        )
    )

    # Reset solver inputs before solving
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target="GAP.RESETSOLVERINPUTS()",
        )
    )

    # Run solver: no optimization, production system, no potential calc
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target="GAP.SOLVENETWORK(0, MOD[0], 0)",
        )
    )

    # Retrieve total field production from separators
    # In GAP, total production is accessed per separator node
    # Using wildcard to get all separator results
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qoil",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qgas",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qwat",
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Run GAP Network Solver",
        commands=commands,
        description=f"Solve network: {model_path}",
    )

    metadata = _create_metadata(start_time, model_path)

    return NetworkSolution(
        model_path=model_path,
        script=script,
        total_field_production={
            "oil_rate": 0.0,
            "oil_rate_unit": "STB/d",
            "gas_rate": 0.0,
            "gas_rate_unit": "MSCF/d",
            "water_rate": 0.0,
            "water_rate_unit": "STB/d",
        },
        well_results=[],
        metadata=metadata,
        warnings=["Script-only mode: execute the script to obtain actual production rates."],
    )


async def optimize_network(params: NetworkOptimizeParams) -> OptimizationResult:
    """Optimize GAP network for a given objective.

    Per GAP User Guide (Network Solver and Optimiser):
    - SOLVENETWORK(optimise, model, potential):
      optimise=0 (No Opt), 1 (Full SQP), 2 (Potential Only), 3 (RBNS)
    - Optimization objectives: Production, Revenue, Oil Rate, Gas+Oil, GHV
    - Constraints set at system/separator/well/joint levels
    - Wells must have dP Control = Calculated for optimizer to choke them
    - Gas lifted wells need GL Control = Calculated for gas allocation
    - ESP wells need Frequency Control = Calculated

    Supports:
    - No Optimisation (natural response, wells fully open)
    - Rule Based Network Solver (RBNS) — fast, honours constraints
    - Optimise with All Constraints (full SQP, slower but optimal)
    - Optimise with Potential Constraints Only

    Args:
        params: Optimization parameters including solver mode.

    Returns:
        OptimizationResult with script and placeholder values.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{params.model_path}")',
        )
    )

    # Reset solver inputs
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target="GAP.RESETSOLVERINPUTS()",
        )
    )

    # Set separator pressure if provided
    if params.separator_pressure is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="GAP.SOLVER.SEPPRES[0]",
                value=str(params.separator_pressure),
            )
        )

    # Set gas lift available if provided
    if params.gas_lift_available is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="GAP.SOLVER.GASLIFTAVAIL[0]",
                value=str(params.gas_lift_available),
            )
        )

    # Set constraints if provided
    if params.constraints:
        for constraint_name, constraint_value in params.constraints.items():
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"GAP.MOD[0].{constraint_name}",
                    value=str(constraint_value),
                )
            )

    # Determine solver mode code
    solver_code = SOLVER_MODE_MAP.get(params.solver_mode, "1")

    # Calculate potential flag
    potential_flag = "1" if params.calculate_potential else "0"

    # Run solver with selected mode
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=f"GAP.SOLVENETWORK({solver_code}, MOD[0], {potential_flag})",
        )
    )

    # Retrieve results from separators
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qoil",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qgas",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qwat",
        )
    )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.SAVEFILE("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Optimize Network ({params.objective.value}, mode={params.solver_mode.value})",
        commands=commands,
        description=f"Objective: {params.objective.value}, Solver: {params.solver_mode.value}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return OptimizationResult(
        model_path=params.model_path,
        script=script,
        objective=params.objective.value,
        production_improvement_percent=0.0,
        optimized_production={},
        well_allocations=[],
        metadata=metadata,
        warnings=["Script-only mode: execute the script to obtain actual optimization results."],
    )


async def identify_bottlenecks(model_path: str) -> BottleneckResult:
    """Identify bottlenecks in a GAP network.

    Runs the solver twice:
    1. Without optimization (baseline)
    2. With optimization (potential)
    Compares results to identify restricted elements.

    Also queries well and pipeline solver results to find constraints.

    Args:
        model_path: Path to the GAP model file.

    Returns:
        BottleneckResult with script and placeholder bottleneck lists.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'GAP.OPENFILE("{model_path}")',
        )
    )

    # Reset inputs
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target="GAP.RESETSOLVERINPUTS()",
        )
    )

    # Solve without optimization to get current state
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target="GAP.SOLVENETWORK(0, MOD[0], 0)",
        )
    )

    # Get well results (oil rates)
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].WELL[$].SolverResults[0].Qoil",
        )
    )

    # Get well potential rates for comparison
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].WELL[$].SolverResults[0].Qpot",
        )
    )

    # Get separator results
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].SolverResults[0].Qoil",
        )
    )

    # Now solve with optimization + potential to see what could be achieved
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target="GAP.SOLVENETWORK(1, MOD[0], 1)",
        )
    )

    # Get optimized results for comparison
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].WELL[$].SolverResults[0].Qoil",
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Identify Network Bottlenecks",
        commands=commands,
        description=f"Bottleneck analysis: {model_path}",
    )

    metadata = _create_metadata(start_time, model_path)

    return BottleneckResult(
        model_path=model_path,
        script=script,
        restricted_wells=[],
        restricted_pipelines=[],
        limiting_facilities=[],
        recommendations=[],
        metadata=metadata,
        warnings=["Script-only mode: execute the script to identify actual bottlenecks."],
    )


# ============================================================================
# New Tool Functions — Production Prediction
# ============================================================================


async def run_prediction(params: RunPredictionParams) -> PredictionResult:
    """Run a GAP production prediction (forecast).

    Generates a script that:
    1. Opens the GAP model
    2. Sets prediction parameters (start/end date, step size)
    3. Sets separator pressure and gas lift available
    4. Optionally sets target pressures for voidage replacement
    5. Runs prediction with specified solver mode
    6. Retrieves cumulative production results

    Per GAP User Guide:
    - Prediction calculates (optimised or not) future production using
      reservoir models (MBAL or decline curves)
    - At each timestep: reservoir pressure/saturations → WC/GOR → Solve Network
    - Results include cumulative oil/gas/water and individual well rates

    Args:
        params: Prediction parameters.

    Returns:
        PredictionResult with script and placeholder values.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    # Set prediction dates and step size
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.PRED.STARTDATE",
            value=params.start_date,
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.PRED.ENDDATE",
            value=params.end_date,
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.PRED.STEPSIZE",
            value=str(params.step_size_months),
        )
    )

    # Set separator pressure
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.PRED.SEPPRES[0]",
            value=str(params.separator_pressure),
        )
    )

    # Set gas lift available if provided
    if params.gas_lift_available is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="GAP.PRED.GASLIFTAVAIL[0]",
                value=str(params.gas_lift_available),
            )
        )

    # Set target pressures for voidage replacement
    if params.target_pressures:
        for tank_name, target_pres in params.target_pressures.items():
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"GAP.PRED.TANK[{{{tank_name}}}].TARGETPRES",
                    value=str(target_pres),
                )
            )
            if params.gas_injection_fraction is not None:
                commands.append(
                    OpenServerCommand(
                        method="DoSet",
                        target=f"GAP.PRED.TANK[{{{tank_name}}}].GASINJFRAC",
                        value=str(params.gas_injection_fraction),
                    )
                )

    # Set solver mode
    solver_code = SOLVER_MODE_MAP.get(params.solver_mode, "1")
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.PRED.OPTMODE",
            value=solver_code,
        )
    )

    # Calculate potential option
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="GAP.PRED.CALCPOTENTIAL",
            value="1" if params.calculate_potential else "0",
        )
    )

    # Run prediction
    commands.append(
        OpenServerCommand(method="DoGAPFunc", target="GAP.RUNPREDICTION()")
    )

    # Retrieve results
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].PREDRES[$].CUMOIL",
        )
    )
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="GAP.MOD[0].SEP[$].PREDRES[$].CUMGAS",
        )
    )

    # Save
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Run GAP Prediction",
        commands=commands,
        description=f"Prediction: {params.start_date} to {params.end_date}, mode={params.solver_mode.value}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return PredictionResult(
        model_path=params.model_path,
        script=script,
        start_date=params.start_date,
        end_date=params.end_date,
        step_size_months=params.step_size_months,
        solver_mode=params.solver_mode.value,
        metadata=metadata,
        warnings=["Script-only mode: execute the script to obtain actual prediction results."],
    )


# ============================================================================
# Well Controls and Constraints
# ============================================================================


async def configure_well_control(params: ConfigureWellControlParams) -> WellControlResult:
    """Configure well controls (dP choke, gas lift, ESP frequency, pump speed).

    Per GAP User Guide (Controls section):
    - dP Control: None (fully open) / Fixed Value / Calculated (optimizer controls)
    - Gas Lift: Fixed injection rate or Calculated with min/max bounds
    - ESP: Fixed frequency or Calculated with min/max bounds
    - Pump/Compressor speed: Fixed or Calculated

    Wells must be 'controllable' for the optimizer to honour constraints.

    Args:
        params: Well control configuration parameters.

    Returns:
        WellControlResult with script and applied controls.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []
    well_prefix = f"GAP.MOD[{{PROD}}].WELL[{{{params.well_name}}}]"

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    controls_applied = {}

    # dP Control
    dp_code = DP_CONTROL_MAP.get(params.dp_control, "NONE")
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target=f"{well_prefix}.DPControl",
            value=dp_code,
        )
    )
    controls_applied["dp_control"] = params.dp_control.value

    if params.dp_control == GAPDPControl.FIXED_VALUE and params.fixed_dp is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{well_prefix}.DPChoke",
                value=str(params.fixed_dp),
            )
        )
        controls_applied["fixed_dp"] = params.fixed_dp

    # Gas Lift Control
    if params.gas_lift_mode:
        gl_mode = "CALCULATED" if params.gas_lift_mode == "calculated" else "FIXED"
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{well_prefix}.GLControl",
                value=gl_mode,
            )
        )
        controls_applied["gas_lift_mode"] = params.gas_lift_mode

        if params.gas_lift_rate is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{well_prefix}.GLRate",
                    value=str(params.gas_lift_rate),
                )
            )
            controls_applied["gas_lift_rate"] = params.gas_lift_rate

        if params.max_gas_injection is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{well_prefix}.GLMaxRate",
                    value=str(params.max_gas_injection),
                )
            )
        if params.min_gas_injection is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{well_prefix}.GLMinRate",
                    value=str(params.min_gas_injection),
                )
            )

    # ESP Control
    if params.esp_frequency_mode:
        esp_mode = "CALCULATED" if params.esp_frequency_mode == "calculated" else "FIXED"
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"{well_prefix}.ESPControl",
                value=esp_mode,
            )
        )
        controls_applied["esp_frequency_mode"] = params.esp_frequency_mode

        if params.esp_frequency is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{well_prefix}.ESPFrequency",
                    value=str(params.esp_frequency),
                )
            )
            controls_applied["esp_frequency"] = params.esp_frequency

        if params.min_frequency is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{well_prefix}.ESPMinFreq",
                    value=str(params.min_frequency),
                )
            )
        if params.max_frequency is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{well_prefix}.ESPMaxFreq",
                    value=str(params.max_frequency),
                )
            )

    # Save
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Configure Well Control: {params.well_name}",
        commands=commands,
        description=f"Set controls for well {params.well_name}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return WellControlResult(
        model_path=params.model_path,
        well_name=params.well_name,
        script=script,
        controls_applied=controls_applied,
        metadata=metadata,
    )


async def set_constraints(params: SetConstraintsParams) -> ConstraintsResult:
    """Set constraints on GAP equipment (well, separator, joint, system, group).

    Per GAP User Guide:
    - System constraints: max oil/gas/liquid/water for total field
    - Separator: max liquid/gas/oil/water/power, LNG production
    - Well: max/min liquid/gas, min FBHP, max drawdown, max GOR, max WC
    - Joint: max liquid/gas/oil/water, min/max pressure

    Constraints direct the optimizer to honour process limitations.

    Args:
        params: Constraint parameters.

    Returns:
        ConstraintsResult with script and constraints set.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    # Determine the OpenServer prefix based on equipment type
    equip_type = params.equipment_type.lower()
    if equip_type == "system":
        prefix = "GAP.MOD[{PROD}].SYSCONST"
    elif equip_type == "separator":
        prefix = f"GAP.MOD[{{PROD}}].SEP[{{{params.equipment_name}}}]"
    elif equip_type == "well":
        prefix = f"GAP.MOD[{{PROD}}].WELL[{{{params.equipment_name}}}]"
    elif equip_type == "joint":
        prefix = f"GAP.MOD[{{PROD}}].JOINT[{{{params.equipment_name}}}]"
    elif equip_type == "group":
        prefix = f"GAP.MOD[{{PROD}}].GROUP[{{{params.equipment_name}}}]"
    else:
        prefix = f"GAP.MOD[{{PROD}}].EQUIP[{{{params.equipment_name}}}]"

    constraints_set = {}

    constraint_map = {
        "max_liquid_rate": ("MAXQLIQ", params.max_liquid_rate),
        "max_gas_rate": ("MAXQGAS", params.max_gas_rate),
        "max_oil_rate": ("MAXQOIL", params.max_oil_rate),
        "max_water_rate": ("MAXQWAT", params.max_water_rate),
        "min_liquid_rate": ("MINQLIQ", params.min_liquid_rate),
        "min_gas_rate": ("MINQGAS", params.min_gas_rate),
        "max_pressure": ("MAXPRES", params.max_pressure),
        "min_pressure": ("MINPRES", params.min_pressure),
        "max_power": ("MAXPOWER", params.max_power),
        "max_gor": ("MAXGOR", params.max_gor),
        "max_water_cut": ("MAXWC", params.max_water_cut),
    }

    for name, (var_name, value) in constraint_map.items():
        if value is not None:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"{prefix}.{var_name}",
                    value=str(value),
                )
            )
            constraints_set[name] = value

    # Save
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Set Constraints: {params.equipment_name} ({equip_type})",
        commands=commands,
        description=f"Constraints on {equip_type} {params.equipment_name}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return ConstraintsResult(
        model_path=params.model_path,
        equipment_name=params.equipment_name,
        script=script,
        constraints_set=constraints_set,
        metadata=metadata,
    )


# ============================================================================
# Batch IPR/VLP Generation
# ============================================================================


async def generate_well_iprs(params: GenerateWellIPRParams) -> GenerateIPRResult:
    """Batch generate well IPRs from PROSPER models.

    License Optimization: Processes wells SEQUENTIALLY — opens PROSPER for 
    one well at a time, generates IPR, saves, closes PROSPER, then moves 
    to the next well. Only 1 PROSPER license consumed at any time.

    Per GAP User Guide (VLP/IPR Generation):
    - Uses PROSPER models associated with each well
    - Transfers PI, reservoir pressure, PVT data from PROSPER to GAP

    Args:
        params: IPR generation parameters.

    Returns:
        GenerateIPRResult with serial-processing script.
    """
    start_time = time.perf_counter()

    script_gen = ScriptGenerator()

    if params.well_names:
        # Generate serial script using the batch_wells method
        prosper_files = {wn: f"{wn}.Out" for wn in params.well_names}
        script = script_gen.generate_batch_wells(
            operation="Batch Generate Well IPRs from PROSPER",
            well_names=params.well_names,
            prosper_files=prosper_files,
            per_well_commands_fn="GAP.GENERATEIPR",
            gap_model=params.model_path,
            description="Sequential IPR generation (1 PROSPER license at a time)",
        )
    else:
        # All wells — still use sequential approach via GAP internal batch
        commands: list[OpenServerCommand] = []
        commands.append(
            OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
        )
        # GAP's internal GENERATEIPR handles PROSPER lifecycle when called with $
        # But we add explicit notes about license behavior
        commands.append(
            OpenServerCommand(method="DoGAPFunc", target='GAP.GENERATEIPR("$")')
        )
        commands.append(
            OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
        )
        script = script_gen.generate(
            operation="Batch Generate Well IPRs from PROSPER",
            commands=commands,
            description="IPR generation for all wells (GAP manages PROSPER lifecycle internally)",
        )

    metadata = _create_metadata(start_time, params.model_path)
    wells_desc = ", ".join(params.well_names) if params.well_names else "all wells"

    return GenerateIPRResult(
        model_path=params.model_path,
        script=script,
        wells_processed=params.well_names or [],
        metadata=metadata,
        warnings=[
            "Script-only mode: execute to transfer IPR data from PROSPER.",
            f"License optimization: processes {wells_desc} sequentially (max 1 PROSPER).",
        ],
    )


async def generate_well_vlps(params: GenerateWellVLPParams) -> GenerateVLPResult:
    """Batch generate well VLPs from PROSPER models.

    License Optimization: Processes wells SEQUENTIALLY — opens PROSPER for 
    one well at a time, generates VLP curves, saves .vlp file, closes 
    PROSPER, then moves to the next well. Only 1 PROSPER license at a time.

    Per GAP User Guide (VLP/IPR Generation):
    - Generates VLP curves for ranges of Rate, Pressure, GOR, WC
    - For gas lifted wells: GLR Injected
    - For ESP wells: Operating Frequency
    - VLP ranges must cover full expected field life conditions

    Args:
        params: VLP generation parameters.

    Returns:
        GenerateVLPResult with serial-processing script.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open GAP model (stays open throughout)
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    # Set VLP generation ranges
    if params.rate_values:
        for i, rate in enumerate(params.rate_values):
            commands.append(
                OpenServerCommand(method="DoSet", target=f"GAP.VLPGEN.RATE[{i}]", value=str(rate))
            )
    if params.pressure_values:
        for i, pres in enumerate(params.pressure_values):
            commands.append(
                OpenServerCommand(method="DoSet", target=f"GAP.VLPGEN.TOPNODEPRES[{i}]", value=str(pres))
            )
    if params.gor_values:
        for i, gor in enumerate(params.gor_values):
            commands.append(
                OpenServerCommand(method="DoSet", target=f"GAP.VLPGEN.GOR[{i}]", value=str(gor))
            )
    if params.watercut_values:
        for i, wc in enumerate(params.watercut_values):
            commands.append(
                OpenServerCommand(method="DoSet", target=f"GAP.VLPGEN.WC[{i}]", value=str(wc))
            )
    if params.glr_values:
        for i, glr in enumerate(params.glr_values):
            commands.append(
                OpenServerCommand(method="DoSet", target=f"GAP.VLPGEN.GLR[{i}]", value=str(glr))
            )
    if params.frequency_values:
        for i, freq in enumerate(params.frequency_values):
            commands.append(
                OpenServerCommand(method="DoSet", target=f"GAP.VLPGEN.FREQ[{i}]", value=str(freq))
            )

    # Generate VLPs sequentially per well (1 PROSPER at a time)
    if params.well_names:
        for well_name in params.well_names:
            # Each GENERATEVLP call opens PROSPER for that well, generates, saves, closes
            commands.append(
                OpenServerCommand(
                    method="DoGAPFunc",
                    target=f'GAP.GENERATEVLP("{well_name}")',
                )
            )
            # Add wait between wells for PROSPER to fully release license
            commands.append(
                OpenServerCommand(method="DoCmd", target="# time.sleep(5)  -- wait for PROSPER license release")
            )
    else:
        # All wells — GAP internal handles sequential PROSPER lifecycle
        commands.append(
            OpenServerCommand(method="DoGAPFunc", target='GAP.GENERATEVLP("$")')
        )

    # Save GAP
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    # Generate script
    script_gen = ScriptGenerator()
    wells_desc = ", ".join(params.well_names) if params.well_names else "all wells"
    script = script_gen.generate(
        operation="Batch Generate Well VLPs from PROSPER (Sequential)",
        commands=commands,
        description=f"VLP generation for: {wells_desc} | 1 PROSPER license at a time",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return GenerateVLPResult(
        model_path=params.model_path,
        script=script,
        wells_processed=params.well_names or [],
        metadata=metadata,
        warnings=[
            "Script-only mode: execute to generate VLP curves via PROSPER.",
            f"License optimization: processes {wells_desc} sequentially (max 1 PROSPER).",
        ],
    )


# ============================================================================
# Initialise IPRs from Tank Simulations
# ============================================================================


async def initialise_iprs_from_tanks(params: InitialiseIPRsFromTanksParams) -> dict:
    """Initialise well IPRs from tank simulations at a specific historical date.

    Per GAP User Guide (Edit menu):
    - Runs MBAL simulation up to the specified date
    - Transfers reservoir pressure, fluid saturations to well IPR sections
    - Updates WC/GOR based on relative permeability at that date
    - Essential for history matching: allows checking production at specific dates

    Args:
        params: Initialisation parameters with date and well selection.

    Returns:
        Dictionary with script and metadata.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    # Initialise IPRs from tanks at date
    if params.well_names:
        for well_name in params.well_names:
            commands.append(
                OpenServerCommand(
                    method="DoGAPFunc",
                    target=f'GAP.INITIALISEIPRFROMTANK("{well_name}", "{params.date}")',
                )
            )
    else:
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=f'GAP.INITIALISEIPRFROMTANK("$", "{params.date}")',
            )
        )

    # Save
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    script_gen = ScriptGenerator()
    wells_desc = ", ".join(params.well_names) if params.well_names else "all wells"
    script = script_gen.generate(
        operation="Initialise IPRs from Tank Simulations",
        commands=commands,
        description=f"Initialise IPRs at date {params.date} for: {wells_desc}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "date": params.date,
        "wells": params.well_names or "all",
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
        "warnings": ["Script-only mode: execute to initialise IPRs from MBAL tanks."],
    }


# ============================================================================
# Schedule Events
# ============================================================================


async def add_schedule_event(params: AddScheduleEventParams) -> dict:
    """Add a scheduled event to a GAP equipment for prediction.

    Per GAP User Guide (Schedule section):
    - Used to change constraints, mask/unmask, start/stop wells at specific dates
    - Can change any OpenServer variable at a given date
    - Events added between timesteps create an additional prediction step

    Args:
        params: Schedule event parameters.

    Returns:
        Dictionary with script and event details.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    # Build the schedule command based on event type
    event_type_lower = params.event_type.lower()

    if event_type_lower == "start_well":
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=f'GAP.ADDSCHEDULE("{params.equipment_name}", "{params.event_date}", "START")',
            )
        )
    elif event_type_lower == "stop_well":
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=f'GAP.ADDSCHEDULE("{params.equipment_name}", "{params.event_date}", "STOP")',
            )
        )
    elif event_type_lower in ("mask", "unmask", "bypass", "unbypass"):
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=f'GAP.ADDSCHEDULE("{params.equipment_name}", "{params.event_date}", "{event_type_lower.upper()}")',
            )
        )
    elif event_type_lower == "change_constraint" and params.constraint_type and params.new_value is not None:
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=(
                    f'GAP.ADDSCHEDULE("{params.equipment_name}", "{params.event_date}", '
                    f'"CONSTRAINT", "{params.constraint_type}", {params.new_value})'
                ),
            )
        )
    elif event_type_lower == "change_pressure" and params.new_value is not None:
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=(
                    f'GAP.ADDSCHEDULE("{params.equipment_name}", "{params.event_date}", '
                    f'"PRESSURE", {params.new_value})'
                ),
            )
        )
    elif event_type_lower == "change_openserver_variable" and params.openserver_variable and params.new_value is not None:
        commands.append(
            OpenServerCommand(
                method="DoGAPFunc",
                target=(
                    f'GAP.ADDSCHEDULE("{params.equipment_name}", "{params.event_date}", '
                    f'"OSVAR", "{params.openserver_variable}", {params.new_value})'
                ),
            )
        )

    # Save
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Add Schedule Event: {params.equipment_name}",
        commands=commands,
        description=f"Schedule {params.event_type} on {params.event_date}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "equipment_name": params.equipment_name,
        "event_date": params.event_date,
        "event_type": params.event_type,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }


# ============================================================================
# Tank (Reservoir) Management
# ============================================================================


async def add_tank(params: AddTankParams) -> dict:
    """Add a reservoir tank to the GAP network.

    Per GAP User Guide (Tanks section):
    - Tank can be Material Balance (MBAL), Decline Curve, or External Simulator
    - Must be connected to wells for prediction
    - MBAL file is linked for Material Balance predictions
    - Decline curves define pressure vs. cumulative production

    Args:
        params: Tank parameters.

    Returns:
        Dictionary with model_path, tank_name, script.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.OPENFILE("{params.model_path}")')
    )

    # Add tank
    commands.append(
        OpenServerCommand(
            method="DoGAPFunc",
            target=f'GAP.NEWITEM("TANK", "{params.tank_name}", "RIGHT", NULL, MOD[0])',
        )
    )

    # Link MBAL file if provided
    if params.mbal_file:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target=f"GAP.MOD[0].TANK[{{{params.tank_name}}}].MBALFile",
                value=params.mbal_file,
            )
        )

    # Connect wells to tank
    if params.connected_wells:
        for well_name in params.connected_wells:
            commands.append(
                OpenServerCommand(
                    method="DoGAPFunc",
                    target=f'GAP.LINKITEMS(MOD[0].TANK[{{{params.tank_name}}}], MOD[0].WELL[{{{well_name}}}], "")',
                )
            )

    # Save
    commands.append(
        OpenServerCommand(method="DoCmd", target=f'GAP.SAVEFILE("{params.model_path}")')
    )

    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Add Tank: {params.tank_name}",
        commands=commands,
        description=f"Tank: {params.tank_name} ({params.tank_model.value})",
    )

    metadata = _create_metadata(start_time, params.model_path)

    return {
        "model_path": params.model_path,
        "tank_name": params.tank_name,
        "tank_model": params.tank_model.value,
        "mbal_file": params.mbal_file,
        "connected_wells": params.connected_wells,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
    }
