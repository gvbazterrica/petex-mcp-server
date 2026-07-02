"""MBAL tool functions for material balance modeling.

Generates complete, executable OpenServer scripts for:
- Creating material balance models with PVT and production history
- Running analytical history matching with aquifer models
- Estimating OOIP/GIIP from matched models
- Production forecasting with abandonment conditions
- Monte Carlo probabilistic reserves estimation

All commands follow the official MBAL OpenServer documentation (January 2025).
Key patterns:
- Production history: MBAL.MB.TANK.PRODHIST[i].TIME/PRESS/CUMGAS/etc.
- History matching: MBAL.MB.REGRESSTANKHIST(MBAL.MB.TANK[0])
- Prediction: MBAL.MB.RunPrediction
- Monte Carlo: MBAL.MC.Calculate
- Aquifer type: MBAL.MB.TANK.AQUIFTYPE (string values)
- OOIP/GIIP: MBAL.MB.TANK.OOIP / MBAL.MB.TANK.GIIP
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from petex_mcp.conversation.session import SessionContext
from petex_mcp.models.commands import OpenServerCommand
from petex_mcp.models.enums import AquiferModel, ReservoirType
from petex_mcp.models.inputs import (
    CreateMbalModelParams,
    ForecastParams,
    HistoricalDataPoint,
    MonteCarloParams,
    RunHistoryMatchParams,
)
from petex_mcp.models.outputs import (
    ExecutionMetadata,
    ForecastResult,
    HistoryMatchResult,
    MonteCarloResult,
)
from petex_mcp.script.generator import ScriptGenerator


# ============================================================================
# OpenServer enum mappings (MBAL uses string values for many settings)
# ============================================================================

# MBAL.MB.TANK.TYPE — reservoir type (string values per documentation)
# Options: OIL, GAS, CON, WATER
RESERVOIR_TYPE_MAP = {
    ReservoirType.OIL: "OIL",
    ReservoirType.GAS: "GAS",
    ReservoirType.CONDENSATE: "CON",
    ReservoirType.GAS_CAP_OIL: "OIL",
}

# MBAL.MB.TANK.AQUIFTYPE — aquifer model (string values per documentation)
# Options: NONE, SMALLPOT, SCHILTHUIS, HURSTSIMPL, HURSTODEH, HURSTDAKE,
#          VOGT, FETKOSTEADY, FETKOUNSTEADY, HURSTMODIF, CARTERTRACY
AQUIFER_MODEL_MAP = {
    AquiferModel.NO_AQUIFER: "NONE",
    AquiferModel.FETKOVICH: "FETKOUNSTEADY",
    AquiferModel.CARTER_TRACY: "CARTERTRACY",
    AquiferModel.POT: "SMALLPOT",
    AquiferModel.HURST_VAN_EVERDINGEN: "HURSTODEH",
}

# PVT parameter to OpenServer path mapping
# Per documentation: MBAL.MB[0].PVT.INPUT section (pág. 187-190)
PVT_FIELD_MAP = {
    "api_gravity": "MBAL.MB[0].PVT.INPUT.OILGRAV",
    "gas_gravity": "MBAL.MB[0].PVT.INPUT.GASGRAV",
    "temperature": "MBAL.MB[0].PVT.INPUT.TRES",
    "bubble_point": "MBAL.MB[0].PVT.INPUT.PRES",
    "oil_gravity": "MBAL.MB[0].PVT.INPUT.OILGRAV",
    "water_salinity": "MBAL.MB[0].PVT.INPUT.WATSAL",
    "h2s_fraction": "MBAL.MB[0].PVT.INPUT.H2S",
    "co2_fraction": "MBAL.MB[0].PVT.INPUT.CO2",
    "n2_fraction": "MBAL.MB[0].PVT.INPUT.N2",
    "initial_pressure": "MBAL.MB.TANK.PRESS",
    "porosity": "MBAL.MB.TANK.POROSITY",
    "connate_water": "MBAL.MB.TANK.CONWATER",
    "rock_compressibility": "MBAL.MB.TANK.ROCKCOMPRESS",
    "water_compressibility": "MBAL.MB.TANK.WATCOMPRESS",
    "gor": "MBAL.MB[0].PVT.INPUT.SOLGOR",
}

# Production history fields per documentation:
# MBAL.MB.TANK.PRODHIST[i].TIME — date/time
# MBAL.MB.TANK.PRODHIST[i].PRESS — pressure
# MBAL.MB.TANK.PRODHIST[i].CUMOIL — cumulative oil
# MBAL.MB.TANK.PRODHIST[i].CUMGAS — cumulative gas
# MBAL.MB.TANK.PRODHIST[i].CUMWAT — cumulative water
# MBAL.MB.TANK.PRODHIST[i].CUMWIN — cumulative water injection
PROD_FIELD_MAP = {
    "date": "TIME",
    "pressure": "PRESS",
    "cumulative_oil": "CUMOIL",
    "cumulative_gas": "CUMGAS",
    "cumulative_water": "CUMWAT",
    "oil_rate": "CUMOIL",      # Note: MBAL uses cumulative, not rates
    "gas_rate": "CUMGAS",
    "water_rate": "CUMWAT",
    "reservoir_pressure": "PRESS",
}


# ============================================================================
# Helper functions
# ============================================================================


def _generate_mbal_model_path(params: dict) -> str:
    """Generate model file path from parameters."""
    model_name = params.get("model_name")
    reservoir_type = params.get("reservoir_type")

    if model_name:
        name = model_name
    else:
        rt = reservoir_type
        if hasattr(rt, "value"):
            rt = rt.value
        name = f"MBAL_{rt}"

    if not name.endswith(".mbi"):
        name = f"{name}.mbi"
    return name


def _field_to_mbal_path(field_name: str, index: int) -> Optional[str]:
    """Map a production data field name to its MBAL OpenServer path.

    Uses MBAL.MB.TANK.PRODHIST[index].FIELD format per documentation.
    """
    os_field = PROD_FIELD_MAP.get(field_name)
    if os_field is None:
        return None
    return f"MBAL.MB.TANK.PRODHIST[{index}].{os_field}"


def _check_data_gaps(
    history: list[HistoricalDataPoint],
    warnings: list[str],
) -> None:
    """Check production history for data gaps and add warnings."""
    if not history:
        return

    fields_present: dict[str, int] = {}
    fields_missing: dict[str, list[int]] = {}

    check_fields = ["oil_rate", "gas_rate", "water_rate", "pressure"]

    for i, point in enumerate(history):
        for f in check_fields:
            val = getattr(point, f, None)
            if val is not None:
                fields_present[f] = fields_present.get(f, 0) + 1
            else:
                if f not in fields_missing:
                    fields_missing[f] = []
                fields_missing[f].append(i)

    for f, missing_indices in fields_missing.items():
        if f in fields_present and fields_present[f] > 0:
            n_missing = len(missing_indices)
            n_total = len(history)
            warnings.append(
                f"Field '{f}' is missing in {n_missing}/{n_total} records. "
                f"Data gaps may affect history match quality."
            )


def _configure_pvt(
    pvt_data: dict,
    commands: list[OpenServerCommand],
    warnings: list[str],
) -> None:
    """Configure PVT parameters from user-provided data."""
    for param_name, value in pvt_data.items():
        os_path = PVT_FIELD_MAP.get(param_name)
        if os_path:
            commands.append(
                OpenServerCommand(method="DoSet", target=os_path, value=str(value))
            )
        else:
            warnings.append(
                f"Unknown PVT parameter '{param_name}' ignored. "
                f"Known parameters: {', '.join(PVT_FIELD_MAP.keys())}"
            )


def _create_metadata(start_time: float, model_path: str) -> ExecutionMetadata:
    """Create execution metadata."""
    duration = time.perf_counter() - start_time
    return ExecutionMetadata(
        duration_seconds=round(duration, 6),
        model_file_path=model_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================================
# Tool functions
# ============================================================================


async def create_mbal_model(
    params: CreateMbalModelParams,
    session: Optional[SessionContext] = None,
) -> dict:
    """Create a new MBAL material balance model.

    Generates a complete OpenServer script that:
    1. Opens MBAL and creates a new file
    2. Sets reservoir type on the tank
    3. Configures PVT if provided
    4. Loads production history using PRODHIST array
    5. Validates and saves the model

    Args:
        params: Model creation parameters.
        session: Optional session context for state tracking.

    Returns:
        Dictionary with model_path, summary, script, metadata, and warnings.
    """
    start_time = time.perf_counter()
    warnings: list[str] = []
    commands: list[OpenServerCommand] = []

    # Determine model path
    model_path = _generate_mbal_model_path({
        "model_name": params.model_name,
        "reservoir_type": params.reservoir_type,
    })

    # --- Section 1: Start MBAL and open/create file ---
    commands.append(
        OpenServerCommand(method="DoCmd", target='MBAL.START("")')
    )
    # Open file will create new if doesn't exist
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target=f'MBAL.OPENFILE="{model_path}"',
        )
    )

    # --- Section 2: Set reservoir type on the tank ---
    res_type_str = RESERVOIR_TYPE_MAP.get(params.reservoir_type, "OIL")
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="MBAL.MB.TANK.TYPE",
            value=res_type_str,
        )
    )

    # --- Section 3: Configure PVT ---
    if params.pvt_data:
        _configure_pvt(params.pvt_data, commands, warnings)

    # --- Section 4: Load production history ---
    data_points = 0
    date_range = None

    if params.production_history:
        history = params.production_history
        data_points = len(history)

        # Check for data gaps
        _check_data_gaps(history, warnings)

        # Reset existing production history
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.PRODHIST.RESET",
                value="",
            )
        )

        # Add rows and populate production data table
        for i, point in enumerate(history):
            # Add a new row
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target="MBAL.MB.TANK.PRODHIST.ADD",
                    value="",
                )
            )
            # Date/time is always required
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"MBAL.MB.TANK.PRODHIST[{i}].TIME",
                    value=point.date,
                )
            )
            if point.pressure is not None:
                commands.append(
                    OpenServerCommand(
                        method="DoSet",
                        target=f"MBAL.MB.TANK.PRODHIST[{i}].PRESS",
                        value=str(point.pressure),
                    )
                )
            if point.oil_rate is not None:
                commands.append(
                    OpenServerCommand(
                        method="DoSet",
                        target=f"MBAL.MB.TANK.PRODHIST[{i}].CUMOIL",
                        value=str(point.oil_rate),
                    )
                )
            if point.gas_rate is not None:
                commands.append(
                    OpenServerCommand(
                        method="DoSet",
                        target=f"MBAL.MB.TANK.PRODHIST[{i}].CUMGAS",
                        value=str(point.gas_rate),
                    )
                )
            if point.water_rate is not None:
                commands.append(
                    OpenServerCommand(
                        method="DoSet",
                        target=f"MBAL.MB.TANK.PRODHIST[{i}].CUMWAT",
                        value=str(point.water_rate),
                    )
                )

        # Sort production history by date
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.PRODHIST.SORT",
                value="",
            )
        )

        date_range = (history[0].date, history[-1].date)

    # --- Section 5: Validate and save ---
    # MBAL.MB.VALIDATE auto-validates all objects
    commands.append(
        OpenServerCommand(method="DoCmd", target="MBAL.MB.VALIDATE")
    )
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'MBAL.SaveFile("{model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation=f"Create MBAL Model ({params.reservoir_type.value})",
        commands=commands,
        description=f"Material balance model: {model_path}",
    )

    metadata = _create_metadata(start_time, model_path)

    # Update session context
    if session is not None:
        session.active_models[model_path] = {
            "created_by": "create_mbal_model",
            "reservoir_type": params.reservoir_type.value,
        }

    # Build summary
    summary: dict = {
        "reservoir_type": params.reservoir_type.value,
        "data_points": data_points,
    }
    if date_range:
        summary["date_range"] = date_range

    return {
        "model_path": model_path,
        "summary": summary,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
        "warnings": warnings,
    }


async def run_history_match(
    params: RunHistoryMatchParams,
    session: Optional[SessionContext] = None,
) -> HistoryMatchResult:
    """Run analytical history matching on an MBAL model.

    Uses MBAL.MB.REGRESSTANKHIST(MBAL.MB.TANK[0]) per documentation.

    Generates a script that:
    1. Opens the model
    2. Sets the aquifer type (string value)
    3. Sets initial OOIP/GIIP guesses if provided
    4. Resets regression inputs
    5. Runs the history match regression
    6. Retrieves OOIP, GIIP, and aquifer volume results

    Args:
        params: History match parameters.
        session: Optional session context for state tracking.

    Returns:
        HistoryMatchResult with script and placeholder results.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target=f'MBAL.OPENFILE="{params.model_path}"',
        )
    )

    # Set aquifer model (string value per documentation)
    aq_str = AQUIFER_MODEL_MAP.get(params.aquifer_model, "NONE")
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="MBAL.MB.TANK.AQUIFTYPE",
            value=aq_str,
        )
    )

    # Set initial guesses if provided
    if params.initial_ooip_guess is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.OOIP",
                value=str(params.initial_ooip_guess),
            )
        )
    if params.initial_giip_guess is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.GIIP",
                value=str(params.initial_giip_guess),
            )
        )

    # Reset regression inputs before running
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target="MBAL.MB.RESETREGRESSTANKHIST(MBAL.MB.TANK[0])",
        )
    )

    # Run history match regression
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target="MBAL.MB.REGRESSTANKHIST(MBAL.MB.TANK[0])",
        )
    )

    # Retrieve results
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MB.TANK.OOIP")
    )
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MB.TANK.GIIP")
    )
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MB.TANK.AQUIF.VOLUME")
    )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'MBAL.SaveFile("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Run History Match",
        commands=commands,
        description=f"Aquifer model: {params.aquifer_model.value}",
    )

    metadata = _create_metadata(start_time, params.model_path)

    # Update session context
    if session is not None:
        session.selected_correlations["aquifer_model"] = params.aquifer_model.value
        session.active_models[params.model_path] = {
            "created_by": "run_history_match",
            "aquifer_model": params.aquifer_model.value,
        }

    return HistoryMatchResult(
        model_path=params.model_path,
        script=script,
        ooip_stb=None,
        giip_scf=None,
        ooip_unit="STB",
        giip_unit="SCF",
        aquifer_volume=None,
        metadata=metadata,
        warnings=[],
    )


async def estimate_ooip(model_path: str) -> dict:
    """Estimate Original Oil In Place from a history-matched MBAL model.

    Retrieves MBAL.MB.TANK.OOIP after history match.

    Args:
        model_path: Path to the MBAL model file.

    Returns:
        Dictionary with OOIP estimate, script, metadata, and warnings.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target=f'MBAL.OPENFILE="{model_path}"',
        )
    )

    # Get OOIP
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MB.TANK.OOIP")
    )

    # Get aquifer volume
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MB.TANK.AQUIF.VOLUME")
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Estimate OOIP",
        commands=commands,
        description="Retrieve OOIP from history-matched model",
    )

    metadata = _create_metadata(start_time, model_path)

    return {
        "model_path": model_path,
        "ooip_stb": None,
        "unit": "STB",
        "aquifer_volume": None,
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
        "warnings": ["Script-only mode: execute the script in MBAL to obtain actual OOIP value."],
    }


async def estimate_giip(model_path: str) -> dict:
    """Estimate Gas Initially In Place from a history-matched MBAL model.

    Retrieves MBAL.MB.TANK.GIIP after history match.

    Args:
        model_path: Path to the MBAL model file.

    Returns:
        Dictionary with GIIP estimate, script, metadata, and warnings.
    """
    start_time = time.perf_counter()
    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target=f'MBAL.OPENFILE="{model_path}"',
        )
    )

    # Get GIIP
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MB.TANK.GIIP")
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Estimate GIIP",
        commands=commands,
        description="Retrieve GIIP from history-matched model",
    )

    metadata = _create_metadata(start_time, model_path)

    return {
        "model_path": model_path,
        "giip_scf": None,
        "unit": "SCF",
        "script": script,
        "metadata": {
            "duration_seconds": metadata.duration_seconds,
            "model_file_path": metadata.model_file_path,
            "timestamp": metadata.timestamp,
        },
        "warnings": ["Script-only mode: execute the script in MBAL to obtain actual GIIP value."],
    }


async def forecast_production(
    params: ForecastParams,
    session: Optional[SessionContext] = None,
) -> ForecastResult:
    """Run production forecast on an MBAL model.

    Uses MBAL.MB.RunPrediction per documentation.
    Results are accessed via MBAL.MB.TRES[prediction_index][well_index][step].

    Args:
        params: Forecast parameters.
        session: Optional session context for state tracking.

    Returns:
        ForecastResult with script and placeholder time series.
    """
    start_time = time.perf_counter()
    warnings: list[str] = []
    commands: list[OpenServerCommand] = []

    # Warn about unusually long forecast periods
    if params.forecast_period > 100.0:
        warnings.append(
            f"Forecast period of {params.forecast_period} years is unusually long. "
            f"Results may be unreliable beyond 30-50 years."
        )

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target=f'MBAL.OPENFILE="{params.model_path}"',
        )
    )

    # Set prediction constraints
    # MBAL prediction constraints are set at MBAL.MB.TANK.CONSTRAINT[0] level
    if params.min_rate is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.CONSTRAINT[0].MINOILRATE",
                value=str(params.min_rate),
            )
        )
    if params.max_water_cut is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.CONSTRAINT[0].MAXWC",
                value=str(params.max_water_cut),
            )
        )
    if params.min_pressure is not None:
        commands.append(
            OpenServerCommand(
                method="DoSet",
                target="MBAL.MB.TANK.CONSTRAINT[0].MINPRESS",
                value=str(params.min_pressure),
            )
        )

    # Set number of prediction steps (years -> steps)
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="MBAL.MB.TANK.NUMWELLS",
            value="1",
        )
    )

    # Run prediction
    commands.append(
        OpenServerCommand(method="DoSlowCmd", target="MBAL.MB.RunPrediction")
    )

    # Retrieve results count
    commands.append(
        OpenServerCommand(
            method="DoGet",
            target="MBAL.MB.TRES[0][0].COUNT",
        )
    )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'MBAL.SaveFile("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Production Forecast",
        commands=commands,
        description=f"Forecast period: {params.forecast_period} years",
    )

    metadata = _create_metadata(start_time, params.model_path)

    # Update session context
    if session is not None:
        session.active_models[params.model_path] = {
            "created_by": "forecast_production",
            "forecast_period": params.forecast_period,
        }

    return ForecastResult(
        model_path=params.model_path,
        script=script,
        forecast_period=params.forecast_period,
        time_series=[],
        abandonment_reason=None,
        metadata=metadata,
        warnings=warnings,
    )


async def montecarlo_reserves(
    params: MonteCarloParams,
    session: Optional[SessionContext] = None,
) -> MonteCarloResult:
    """Run Monte Carlo probabilistic reserves estimation.

    Uses MBAL.MC.Calculate per documentation.

    Args:
        params: Monte Carlo parameters.
        session: Optional session context for state tracking.

    Returns:
        MonteCarloResult with script and placeholder statistics.

    Raises:
        ValueError: If no distributions are provided.
    """
    start_time = time.perf_counter()

    if not params.distributions:
        raise ValueError("At least one distribution must be provided for Monte Carlo analysis.")

    commands: list[OpenServerCommand] = []

    # Open model
    commands.append(
        OpenServerCommand(
            method="DoSlowCmd",
            target=f'MBAL.OPENFILE="{params.model_path}"',
        )
    )

    # Set number of iterations
    commands.append(
        OpenServerCommand(
            method="DoSet",
            target="MBAL.MC.NUMRUNS",
            value=str(params.iterations),
        )
    )

    # Configure distributions
    # Monte Carlo parameters in MBAL are configured through the MC section
    for i, (param_name, dist_config) in enumerate(params.distributions.items()):
        # Set min/max values for the parameter
        if "min" in dist_config:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"MBAL.MC.INPUT[{i}].MIN",
                    value=str(dist_config["min"]),
                )
            )
        if "max" in dist_config:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"MBAL.MC.INPUT[{i}].MAX",
                    value=str(dist_config["max"]),
                )
            )
        if "mean" in dist_config:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"MBAL.MC.INPUT[{i}].MEAN",
                    value=str(dist_config["mean"]),
                )
            )
        if "std" in dist_config:
            commands.append(
                OpenServerCommand(
                    method="DoSet",
                    target=f"MBAL.MC.INPUT[{i}].SD",
                    value=str(dist_config["std"]),
                )
            )

    # Run Monte Carlo calculation
    commands.append(
        OpenServerCommand(method="DoSlowCmd", target="MBAL.MC.Calculate")
    )

    # Retrieve results — P10, P50, P90
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MC.OUTPUT.P10")
    )
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MC.OUTPUT.P50")
    )
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MC.OUTPUT.P90")
    )
    commands.append(
        OpenServerCommand(method="DoGet", target="MBAL.MC.OUTPUT.MEAN")
    )

    # Save
    commands.append(
        OpenServerCommand(
            method="DoCmd",
            target=f'MBAL.SaveFile("{params.model_path}")',
        )
    )

    # Generate script
    script_gen = ScriptGenerator()
    script = script_gen.generate(
        operation="Monte Carlo Reserves Estimation",
        commands=commands,
        description=f"{params.iterations} iterations, {len(params.distributions)} uncertain parameters",
    )

    metadata = _create_metadata(start_time, params.model_path)

    # Update session context
    if session is not None:
        session.active_models[params.model_path] = {
            "created_by": "montecarlo_reserves",
            "iterations": params.iterations,
        }

    return MonteCarloResult(
        model_path=params.model_path,
        script=script,
        p10=None,
        p50=None,
        p90=None,
        mean=None,
        unit="STB",
        iterations=params.iterations,
        metadata=metadata,
        warnings=[],
    )
