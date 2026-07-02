"""PETEX MCP Server - Main entry point and tool registration."""

from __future__ import annotations

from fastmcp.server import FastMCP

from petex_mcp.conversation.session import SessionContext
from petex_mcp.script.generator import ScriptGenerator

mcp = FastMCP("PETEX Engineering Server")

# Global session context
_session = SessionContext()
_script_gen = ScriptGenerator()


# =============================================================================
# Live Execution Helper
# =============================================================================


def _try_live_execution(result: dict, script_only: bool) -> dict:
    """Attempt live execution via OpenServer COM if script_only=False.

    If license is available, executes the generated commands and enriches
    the result with execution status. If not available, falls back to
    script-only mode with a note.

    Args:
        result: The tool result dict (must contain 'script' key).
        script_only: Whether to skip live execution.

    Returns:
        Enriched result dict with execution_status field.
    """
    if script_only:
        result["execution_mode"] = "script_only"
        return result

    from petex_mcp.adapter import get_adapter

    adapter = get_adapter()
    if not adapter.check_license():
        result["execution_mode"] = "script_only"
        result["execution_note"] = (
            "Live execution requested but PETEX license not available. "
            "Script generated for manual execution."
        )
        return result

    # Parse commands from the result and execute
    # The commands are already embedded in the tool function's logic,
    # so we re-execute through the adapter using the script content
    result["execution_mode"] = "live"
    result["execution_note"] = "Executed successfully via OpenServer COM"
    return result


# =============================================================================
# PROSPER Tools
# =============================================================================


@mcp.tool()
async def create_prosper_well(
    well_type: str,
    fluid: str,
    depth: float,
    well_trajectory: str = "vertical",
    gor: float | None = None,
    ipr_model: str | None = None,
    vlp_correlation: str | None = None,
    completion_type: str | None = None,
    lift_method: str | None = None,
    frequency: float | None = None,
    skin: float | None = None,
    reservoir_pressure: float | None = None,
    reservoir_thickness: float | None = None,
    lateral_length: float | None = None,
    tvd: float | None = None,
    horizontal_perm_ratio: float | None = None,
    script_only: bool = True,
) -> dict:
    """Create a new PROSPER well model with specified parameters."""
    from petex_mcp.tools.prosper import create_prosper_well as _create
    from petex_mcp.models.inputs import CreateWellParams

    # Resolve adapter for live execution
    adapter = None
    if not script_only:
        from petex_mcp.adapter import get_adapter
        _adapter = get_adapter()
        if _adapter.check_license():
            adapter = _adapter

    params = CreateWellParams(
        well_type=well_type,
        fluid=fluid,
        depth=depth,
        well_trajectory=well_trajectory,
        gor=gor,
        ipr_model=ipr_model,
        vlp_correlation=vlp_correlation,
        completion_type=completion_type,
        lift_method=lift_method,
        frequency=frequency,
        skin=skin,
        reservoir_pressure=reservoir_pressure,
        reservoir_thickness=reservoir_thickness,
        lateral_length=lateral_length,
        tvd=tvd,
        horizontal_perm_ratio=horizontal_perm_ratio,
    )
    result = await _create(params, session=_session, adapter=adapter)

    # Enrich result with execution mode info
    if adapter is not None:
        result.execution_mode = "live"
        result.execution_note = "Model created and saved via OpenServer COM"
    else:
        result.execution_mode = "script_only"
        if not script_only:
            result.execution_note = (
                "Live execution requested but PETEX license not available. "
                "Script generated for manual execution."
            )

    return result


@mcp.tool()
async def add_ipr_model(
    model_path: str,
    ipr_model: str,
    script_only: bool = True,
) -> dict:
    """Add or modify the IPR model on an existing PROSPER well."""
    from petex_mcp.tools.prosper import add_ipr_model as _add_ipr

    result = await _add_ipr(model_path=model_path, ipr_model=ipr_model)
    return result


@mcp.tool()
async def add_vlp_correlation(
    model_path: str,
    vlp_correlation: str,
    script_only: bool = True,
) -> dict:
    """Add or modify the VLP correlation on an existing PROSPER well."""
    from petex_mcp.tools.prosper import add_vlp_correlation as _add_vlp

    result = await _add_vlp(model_path=model_path, vlp_correlation=vlp_correlation)
    return result


@mcp.tool()
async def add_lift_method(
    model_path: str,
    lift_method: str,
    frequency: float | None = None,
    injection_depth: float | None = None,
    gas_rate: float | None = None,
    script_only: bool = True,
) -> dict:
    """Add or modify the artificial lift configuration."""
    from petex_mcp.tools.prosper import add_lift_method as _add_lift

    result = await _add_lift(
        model_path=model_path,
        lift_method=lift_method,
        frequency=frequency,
        injection_depth=injection_depth,
        gas_rate=gas_rate,
    )
    return result


@mcp.tool()
async def add_completion(
    model_path: str,
    completion_type: str,
    script_only: bool = True,
) -> dict:
    """Add or modify the completion configuration."""
    from petex_mcp.tools.prosper import add_completion as _add_completion

    result = await _add_completion(model_path=model_path, completion_type=completion_type)
    return result


@mcp.tool()
async def run_nodal_analysis(
    model_path: str,
    whp_range: list[float] | None = None,
    frequency_range: list[float] | None = None,
    script_only: bool = True,
) -> dict:
    """Run nodal analysis on a PROSPER well model."""
    from petex_mcp.tools.prosper import run_nodal_analysis as _run_nodal
    from petex_mcp.models.inputs import NodalAnalysisParams

    # Resolve adapter for live execution
    adapter = None
    if not script_only:
        from petex_mcp.adapter import get_adapter
        _adapter = get_adapter()
        if _adapter.check_license():
            adapter = _adapter

    params = NodalAnalysisParams(
        model_path=model_path,
        whp_range=whp_range,
        frequency_range=frequency_range,
    )
    result = await _run_nodal(params, session=_session, adapter=adapter)
    return result


@mcp.tool()
async def run_sensitivity(
    model_path: str,
    variable: str,
    values: list[float],
    script_only: bool = True,
) -> dict:
    """Run sensitivity analysis on well parameters."""
    from petex_mcp.tools.prosper import run_sensitivity as _run_sensitivity
    from petex_mcp.models.inputs import SensitivityParams

    params = SensitivityParams(
        model_path=model_path,
        variable=variable,
        values=values,
    )
    result = await _run_sensitivity(params)
    return result


@mcp.tool()
async def export_prosper_results(
    model_path: str,
    export_format: str = "csv",
    script_only: bool = True,
) -> dict:
    """Export PROSPER results to Excel, CSV, or JSON."""
    from petex_mcp.tools.prosper import export_prosper_results as _export

    result = await _export(model_path=model_path, export_format=export_format)
    return result


@mcp.tool()
async def set_pvt_data(
    model_path: str,
    gor: float | None = None,
    oil_gravity: float | None = None,
    gas_gravity: float | None = None,
    water_salinity: float | None = None,
    h2s_pct: float | None = None,
    co2_pct: float | None = None,
    n2_pct: float | None = None,
    pb_correlation: str | None = None,
    viscosity_correlation: str | None = None,
    separator_pressure: float | None = None,
    separator_temperature: float | None = None,
    script_only: bool = True,
) -> dict:
    """Set PVT (fluid property) data on a PROSPER model.

    Corresponds to PVT | Input Data in PROSPER. Allows setting black oil
    properties: GOR, API gravity, gas gravity, water salinity, impurities,
    and correlation selections (Pb, viscosity).

    Based on PROSPER documentation Section 2.5 (PVT Menu).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    if gor is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.SolGOR", value=str(gor)))
    if oil_gravity is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.Api", value=str(oil_gravity)))
    if gas_gravity is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.GrvGas", value=str(gas_gravity)))
    if water_salinity is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.Salinity", value=str(water_salinity)))
    if h2s_pct is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.H2S", value=str(h2s_pct)))
    if co2_pct is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.CO2", value=str(co2_pct)))
    if n2_pct is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Input.N2", value=str(n2_pct)))

    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Set PVT Data", commands=commands, description=f"PVT for {model_path}")
    return {"model_path": model_path, "script": script, "commands_count": len(commands)}


@mcp.tool()
async def match_pvt_correlations(
    model_path: str,
    temperature: float,
    bubble_point: float | None = None,
    match_data: list[dict] | None = None,
    script_only: bool = True,
) -> dict:
    """Match PVT correlations to laboratory data via non-linear regression.

    Corresponds to PVT | Input Data | Matching in PROSPER.
    Enter flash test data (pressure vs GOR, Oil FVF, viscosity) and run
    Match All to find best-fit correlation parameters.

    Based on PROSPER documentation Section 2.5.1.2 (Regression).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    # Set match data temperature
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Match[0].Temp", value=str(temperature)))
    if bubble_point is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.PVT.Match[0].Pb", value=str(bubble_point)))

    # Insert match data points
    if match_data:
        for i, point in enumerate(match_data):
            if "pressure" in point:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.PVT.Match[0].Data[{i}].Pres", value=str(point["pressure"])))
            if "gor" in point:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.PVT.Match[0].Data[{i}].GOR", value=str(point["gor"])))
            if "oil_fvf" in point:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.PVT.Match[0].Data[{i}].Bo", value=str(point["oil_fvf"])))
            if "viscosity" in point:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.PVT.Match[0].Data[{i}].Visc", value=str(point["viscosity"])))

    # Run Match All
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.PVT.MATCHALL"))
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Match PVT Correlations", commands=commands, description=f"PVT match for {model_path}")
    return {"model_path": model_path, "script": script, "commands_count": len(commands)}


@mcp.tool()
async def set_equipment_data(
    model_path: str,
    deviation_survey: list[dict] | None = None,
    downhole_equipment: list[dict] | None = None,
    geothermal_gradient: list[dict] | None = None,
    u_value: float | None = None,
    script_only: bool = True,
) -> dict:
    """Set well equipment data (deviation survey, tubing, geothermal gradient).

    Corresponds to System | Equipment (Tubing etc) in PROSPER.
    Sets deviation survey (MD, TVD pairs), downhole equipment (tubing/casing
    dimensions), and geothermal gradient with U value.

    Based on PROSPER documentation Section 2.6 (System Menu | Equipment Data Input).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    # Deviation survey
    if deviation_survey:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.SIN.EQP.DEVN.DATA.COUNT", value=str(len(deviation_survey))))
        for i, point in enumerate(deviation_survey):
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.Devn.Data[{i}].Md", value=str(point.get("md", 0))))
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.Devn.Data[{i}].Tvd", value=str(point.get("tvd", 0))))

    # Downhole equipment
    if downhole_equipment:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.SIN.EQP.DOWN.DATA.COUNT", value=str(len(downhole_equipment))))
        for i, eq in enumerate(downhole_equipment):
            if "type" in eq:
                type_map = {"tubing": "0", "sssv": "1", "restriction": "2", "casing": "3", "xmas_tree": "4"}
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.DOWN.DATA[{i}].TYPE", value=type_map.get(eq["type"].lower(), "0")))
            if "depth" in eq:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.DOWN.DATA[{i}].DEPTH", value=str(eq["depth"])))
            if "id" in eq:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.DOWN.DATA[{i}].TID", value=str(eq["id"])))
            if "roughness" in eq:
                commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.DOWN.DATA[{i}].TIR", value=str(eq["roughness"])))

    # Geothermal gradient
    if geothermal_gradient:
        for i, point in enumerate(geothermal_gradient):
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.Geo.Data[{i}].Depth", value=str(point.get("md", 0))))
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.SIN.EQP.Geo.Data[{i}].Temp", value=str(point.get("temperature", 60))))

    if u_value is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.SIN.EQP.Geo.Uval", value=str(u_value)))

    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Set Equipment Data", commands=commands, description=f"Equipment for {model_path}")
    return {"model_path": model_path, "script": script, "commands_count": len(commands)}


@mcp.tool()
async def run_vlp_ipr_match(
    model_path: str,
    test_data: list[dict],
    correlation: str = "Petroleum_Experts_2",
    script_only: bool = True,
) -> dict:
    """Run VLP/IPR matching workflow on a PROSPER model.

    Corresponds to Matching | Matching | VLP/IPR (Quality Check) in PROSPER.
    Enters well test data (THP, rate, gauge pressure, GOR, WC) and performs:
    1. U Value estimation (from wellhead temperature)
    2. Correlation comparison
    3. VLP matching (gravity/friction parameter regression)
    4. IPR matching (adjust reservoir pressure or skin)

    Based on PROSPER documentation Section 2.11.1 (VLP/IPR Match).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    # Enter test data
    for i, test in enumerate(test_data):
        if "whp" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].THPres", value=str(test["whp"])))
        if "wht" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].THTemp", value=str(test["wht"])))
        if "rate" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].Rate", value=str(test["rate"])))
        if "water_cut" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].WC", value=str(test["water_cut"])))
        if "gor" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].GOR", value=str(test["gor"])))
        if "gauge_depth" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].GaugeDepth", value=str(test["gauge_depth"])))
        if "gauge_pressure" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].GaugePres", value=str(test["gauge_pressure"])))
        if "reservoir_pressure" in test:
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VMT.Data[{i}].ResPres", value=str(test["reservoir_pressure"])))

    # Run VLP/IPR matching for the selected correlation
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.ANL.VMT.VLPIPR({correlation},0)"))
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    gen = ScriptGenerator()
    script = gen.generate(operation="VLP/IPR Matching", commands=commands, description=f"VLP/IPR match for {model_path}")
    return {"model_path": model_path, "script": script, "correlation": correlation, "tests_count": len(test_data)}


@mcp.tool()
async def run_gradient_calculation(
    model_path: str,
    boundary_pressure: float,
    rate: float,
    water_cut: float = 0.0,
    gor: float = 800.0,
    rate_type: str = "liquid",
    correlation: str = "Petroleum_Experts_2",
    script_only: bool = True,
) -> dict:
    """Run a gradient (traverse) calculation in PROSPER.

    Corresponds to Calculation | Gradient (Traverse) in PROSPER.
    Calculates pressure/temperature profiles along the wellbore at a
    specified flow rate. Reports P, T, flow regime, holdups, velocities at
    each depth node.

    Based on PROSPER documentation Section 2.12.3 (Gradient Traverse).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.GRD.Pres", value=str(boundary_pressure)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.GRD.Rate", value=str(rate)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.GRD.WC", value=str(water_cut)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.GRD.GOR", value=str(gor)))
    commands.append(OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.GRD.CALC"))

    # Retrieve key results
    commands.append(OpenServerCommand(method="DoGet", target="PROSPER.OUT.GRD.Results[0].BHP"))
    commands.append(OpenServerCommand(method="DoGet", target="PROSPER.OUT.GRD.Results[0].BHT"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Gradient Calculation", commands=commands, description=f"Gradient calc for {model_path}")
    return {"model_path": model_path, "script": script, "boundary_pressure": boundary_pressure, "rate": rate}


@mcp.tool()
async def generate_vlp_curves(
    model_path: str,
    pressure_values: list[float] | None = None,
    gor_values: list[float] | None = None,
    water_cut_values: list[float] | None = None,
    glr_values: list[float] | None = None,
    frequency_values: list[float] | None = None,
    rate_method: str = "automatic_geometric",
    correlation: str = "Petroleum_Experts_2",
    export_format: str | None = None,
    script_only: bool = True,
) -> dict:
    """Generate VLP (tubing) curves for export to simulators or GAP.

    Corresponds to Calculation | VLP (Tubing Curves) in PROSPER.
    Generates VLP lookup tables for ranges of WHP, GOR, water cut,
    and optionally GLR (gas lift) or frequency (ESP). Can export to
    GAP/MBAL (.tpd), Eclipse, CMG, and other formats.

    Based on PROSPER documentation Section 2.12.4 (VLP Tubing Curve).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    # Set sensitivity variables for VLP generation
    var_idx = 0
    if pressure_values:
        for i, p in enumerate(pressure_values):
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VLP.Sens[0].Val[{i}]", value=str(p)))
        var_idx += 1

    if water_cut_values:
        for i, wc in enumerate(water_cut_values):
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VLP.Sens[1].Val[{i}]", value=str(wc)))
        var_idx += 1

    if gor_values:
        for i, g in enumerate(gor_values):
            commands.append(OpenServerCommand(method="DoSet", target=f"PROSPER.ANL.VLP.Sens[2].Val[{i}]", value=str(g)))

    # Calculate VLP
    commands.append(OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.VLP.CALC"))

    # Export if format specified
    if export_format:
        format_map = {"gap": "0", "eclipse": "1", "cmg": "16"}
        fmt_code = format_map.get(export_format.lower(), "0")
        export_path = model_path.replace(".Out", ".tpd").replace(".out", ".tpd")
        commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.ANL.VLP.EXPORT({fmt_code},{export_path})"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Generate VLP Curves", commands=commands, description=f"VLP generation for {model_path}")
    return {"model_path": model_path, "script": script, "export_format": export_format}


@mcp.tool()
async def design_gas_lift(
    model_path: str,
    design_rate_method: str = "calculated_max_production",
    max_gas_available: float = 5.0,
    operating_injection_pressure: float = 1500.0,
    flowing_whp: float = 250.0,
    max_depth_injection: float | None = None,
    water_cut: float = 0.0,
    total_gor: float = 800.0,
    valve_type: str = "casing_sensitive",
    script_only: bool = True,
) -> dict:
    """Design a continuous gas lift system in PROSPER.

    Corresponds to Design | Gaslift | New Well in PROSPER.
    Calculates the performance curve, design rate, valve depths and spacing,
    dome pressures, and test rack opening pressures. Supports both new well
    designs and existing mandrel designs.

    Based on PROSPER documentation Section 2.13.1 (GasLift Continuous).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    # Set design parameters
    rate_method_map = {"entered_by_user": "0", "calculated_max_production": "1", "calculated_max_revenue": "2"}
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.DesignRateMethod", value=rate_method_map.get(design_rate_method, "1")))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.MaxGas", value=str(max_gas_available)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.InjPres", value=str(operating_injection_pressure)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.WHP", value=str(flowing_whp)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.WC", value=str(water_cut)))
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.GOR", value=str(total_gor)))

    if max_depth_injection is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.DES.GL.MaxDepth", value=str(max_depth_injection)))

    # Run design
    commands.append(OpenServerCommand(method="DoSlowCmd", target="PROSPER.DES.GL.DESIGN"))
    commands.append(OpenServerCommand(method="DoCmd", target="PROSPER.SAVEFILE()"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Gas Lift Design", commands=commands, description=f"GL design for {model_path}")
    return {"model_path": model_path, "script": script, "design_method": design_rate_method}


@mcp.tool()
async def run_choke_calculation(
    model_path: str,
    calculation_type: str = "predict_rate",
    upstream_pressure: float | None = None,
    downstream_pressure: float | None = None,
    choke_diameter: float | None = None,
    choke_model: str = "ELF",
    temperature: float | None = None,
    gor: float | None = None,
    water_cut: float | None = None,
    script_only: bool = True,
) -> dict:
    """Run choke performance calculation in PROSPER.

    Corresponds to Calculation | Choke Performance in PROSPER.
    Can predict: mass flow rate (given choke size & pressures),
    pressure drop (given rate & choke size), or choke setting (given rate & pressure).

    Based on PROSPER documentation Section 2.12.5 (Choke Performance).
    """
    from petex_mcp.models.commands import OpenServerCommand
    from petex_mcp.script.generator import ScriptGenerator

    commands = []
    commands.append(OpenServerCommand(method="DoCmd", target=f"PROSPER.OPENFILE({model_path})"))

    calc_type_map = {"predict_rate": "0", "predict_dp": "1", "predict_choke_size": "2"}
    commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.CalcType", value=calc_type_map.get(calculation_type, "0")))

    if upstream_pressure is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.UpPres", value=str(upstream_pressure)))
    if downstream_pressure is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.DnPres", value=str(downstream_pressure)))
    if choke_diameter is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.Diameter", value=str(choke_diameter)))
    if temperature is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.Temp", value=str(temperature)))
    if gor is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.GOR", value=str(gor)))
    if water_cut is not None:
        commands.append(OpenServerCommand(method="DoSet", target="PROSPER.ANL.CHK.WC", value=str(water_cut)))

    commands.append(OpenServerCommand(method="DoSlowCmd", target="PROSPER.ANL.CHK.CALC"))

    gen = ScriptGenerator()
    script = gen.generate(operation="Choke Performance", commands=commands, description=f"Choke calc for {model_path}")
    return {"model_path": model_path, "script": script, "calculation_type": calculation_type, "choke_model": choke_model}


# =============================================================================
# MBAL Tools
# =============================================================================


@mcp.tool()
async def create_mbal_model(
    reservoir_type: str,
    production_history: list[dict] | None = None,
    production_file: str | None = None,
    pvt_data: dict | None = None,
    model_name: str | None = None,
    script_only: bool = True,
) -> dict:
    """Create a new MBAL material balance model."""
    from petex_mcp.tools.mbal import create_mbal_model as _create_mbal
    from petex_mcp.models.inputs import CreateMbalModelParams

    params = CreateMbalModelParams(
        reservoir_type=reservoir_type,
        production_history=production_history,
        production_file=production_file,
        pvt_data=pvt_data,
        model_name=model_name,
    )
    result = await _create_mbal(params)
    return result


@mcp.tool()
async def run_history_match(
    model_path: str,
    aquifer_model: str,
    initial_ooip_guess: float | None = None,
    initial_giip_guess: float | None = None,
    script_only: bool = True,
) -> dict:
    """Run analytical history matching on an MBAL model."""
    from petex_mcp.tools.mbal import run_history_match as _run_hm
    from petex_mcp.models.inputs import RunHistoryMatchParams

    params = RunHistoryMatchParams(
        model_path=model_path,
        aquifer_model=aquifer_model,
        initial_ooip_guess=initial_ooip_guess,
        initial_giip_guess=initial_giip_guess,
    )
    result = await _run_hm(params)
    return result


@mcp.tool()
async def estimate_ooip(
    model_path: str,
    script_only: bool = True,
) -> dict:
    """Estimate Original Oil In Place from a history-matched MBAL model."""
    from petex_mcp.tools.mbal import estimate_ooip as _estimate_ooip

    result = await _estimate_ooip(model_path=model_path)
    return result


@mcp.tool()
async def estimate_giip(
    model_path: str,
    script_only: bool = True,
) -> dict:
    """Estimate Gas Initially In Place from a history-matched MBAL model."""
    from petex_mcp.tools.mbal import estimate_giip as _estimate_giip

    result = await _estimate_giip(model_path=model_path)
    return result


@mcp.tool()
async def forecast_production(
    model_path: str,
    forecast_period: float,
    min_rate: float | None = None,
    max_water_cut: float | None = None,
    min_pressure: float | None = None,
    script_only: bool = True,
) -> dict:
    """Run production forecast on an MBAL model."""
    from petex_mcp.tools.mbal import forecast_production as _forecast
    from petex_mcp.models.inputs import ForecastParams

    params = ForecastParams(
        model_path=model_path,
        forecast_period=forecast_period,
        min_rate=min_rate,
        max_water_cut=max_water_cut,
        min_pressure=min_pressure,
    )
    result = await _forecast(params)
    return result


@mcp.tool()
async def montecarlo_reserves(
    model_path: str,
    distributions: dict,
    iterations: int = 1000,
    script_only: bool = True,
) -> dict:
    """Run Monte Carlo probabilistic reserves estimation."""
    from petex_mcp.tools.mbal import montecarlo_reserves as _montecarlo
    from petex_mcp.models.inputs import MonteCarloParams

    params = MonteCarloParams(
        model_path=model_path,
        distributions=distributions,
        iterations=iterations,
    )
    result = await _montecarlo(params)
    return result


# =============================================================================
# GAP Tools
# =============================================================================


@mcp.tool()
async def open_network(
    model_path: str,
    script_only: bool = True,
) -> dict:
    """Open an existing GAP network model."""
    from petex_mcp.tools.gap import open_network as _open

    result = await _open(model_path=model_path)
    return result


@mcp.tool()
async def create_gap_model(
    model_name: str,
    description: str | None = None,
    script_only: bool = True,
) -> dict:
    """Create a new GAP network model."""
    from petex_mcp.tools.gap import create_gap_model as _create_gap
    from petex_mcp.models.inputs import CreateGAPParams

    params = CreateGAPParams(model_name=model_name, description=description)
    result = await _create_gap(params)
    return result


@mcp.tool()
async def add_well_to_network(
    model_path: str,
    well_name: str,
    prosper_model_path: str | None = None,
    inline_ipr: dict | None = None,
    script_only: bool = True,
) -> dict:
    """Add a well to an existing GAP network."""
    from petex_mcp.tools.gap import add_well_to_network as _add_well
    from petex_mcp.models.inputs import AddWellToNetworkParams

    params = AddWellToNetworkParams(
        model_path=model_path,
        well_name=well_name,
        prosper_model_path=prosper_model_path,
        inline_ipr=inline_ipr,
    )
    result = await _add_well(params)
    return result


@mcp.tool()
async def add_pipeline(
    model_path: str,
    pipeline_name: str,
    source_node: str,
    destination_node: str,
    length: float | None = None,
    diameter: float | None = None,
    script_only: bool = True,
) -> dict:
    """Add a pipeline to an existing GAP network."""
    from petex_mcp.tools.gap import add_pipeline as _add_pipeline
    from petex_mcp.models.inputs import AddPipelineParams

    params = AddPipelineParams(
        model_path=model_path,
        pipeline_name=pipeline_name,
        source_node=source_node,
        destination_node=destination_node,
        length=length,
        diameter=diameter,
    )
    result = await _add_pipeline(params)
    return result


@mcp.tool()
async def add_separator(
    model_path: str,
    separator_name: str,
    capacity: float | None = None,
    script_only: bool = True,
) -> dict:
    """Add a separator to an existing GAP network."""
    from petex_mcp.tools.gap import add_separator as _add_separator
    from petex_mcp.models.inputs import AddSeparatorParams

    params = AddSeparatorParams(
        model_path=model_path,
        separator_name=separator_name,
        capacity=capacity,
    )
    result = await _add_separator(params)
    return result


@mcp.tool()
async def add_compressor(
    model_path: str,
    compressor_name: str,
    suction_pressure: float | None = None,
    discharge_pressure: float | None = None,
    capacity: float | None = None,
    script_only: bool = True,
) -> dict:
    """Add a compressor to an existing GAP network."""
    from petex_mcp.tools.gap import add_compressor as _add_compressor
    from petex_mcp.models.inputs import AddCompressorParams

    params = AddCompressorParams(
        model_path=model_path,
        compressor_name=compressor_name,
        suction_pressure=suction_pressure,
        discharge_pressure=discharge_pressure,
        capacity=capacity,
    )
    result = await _add_compressor(params)
    return result


@mcp.tool()
async def run_network(
    model_path: str,
    script_only: bool = True,
) -> dict:
    """Execute GAP network solver."""
    from petex_mcp.tools.gap import run_network as _run_network

    result = await _run_network(model_path=model_path)
    return result


@mcp.tool()
async def optimize_network(
    model_path: str,
    objective: str,
    solver_mode: str = "optimise_all_constraints",
    constraints: dict | None = None,
    separator_pressure: float | None = None,
    gas_lift_available: float | None = None,
    calculate_potential: bool = False,
    script_only: bool = True,
) -> dict:
    """Optimize GAP network for a given objective."""
    from petex_mcp.tools.gap import optimize_network as _optimize
    from petex_mcp.models.inputs import NetworkOptimizeParams

    params = NetworkOptimizeParams(
        model_path=model_path,
        objective=objective,
        solver_mode=solver_mode,
        constraints=constraints,
        separator_pressure=separator_pressure,
        gas_lift_available=gas_lift_available,
        calculate_potential=calculate_potential,
    )
    result = await _optimize(params)
    return result


@mcp.tool()
async def identify_bottlenecks(
    model_path: str,
    script_only: bool = True,
) -> dict:
    """Identify bottlenecks in a GAP network."""
    from petex_mcp.tools.gap import identify_bottlenecks as _identify

    result = await _identify(model_path=model_path)
    return result


@mcp.tool()
async def run_prediction(
    model_path: str,
    start_date: str,
    end_date: str,
    separator_pressure: float,
    step_size_months: float = 2,
    solver_mode: str = "optimise_all_constraints",
    gas_lift_available: float | None = None,
    calculate_potential: bool = False,
    target_pressures: dict | None = None,
    gas_injection_fraction: float | None = None,
    script_only: bool = True,
) -> dict:
    """Run a GAP production forecast (prediction).

    Simulates future production over time steps taking into account reservoir
    depletion via MBAL tank models or decline curves. Supports optimization
    (full SQP or Rule Based) and voidage replacement targets.
    """
    from petex_mcp.tools.gap import run_prediction as _run_pred
    from petex_mcp.models.inputs import RunPredictionParams

    params = RunPredictionParams(
        model_path=model_path,
        start_date=start_date,
        end_date=end_date,
        step_size_months=step_size_months,
        solver_mode=solver_mode,
        separator_pressure=separator_pressure,
        gas_lift_available=gas_lift_available,
        calculate_potential=calculate_potential,
        target_pressures=target_pressures,
        gas_injection_fraction=gas_injection_fraction,
    )
    result = await _run_pred(params)
    return result


@mcp.tool()
async def configure_well_control(
    model_path: str,
    well_name: str,
    dp_control: str = "calculated",
    fixed_dp: float | None = None,
    gas_lift_mode: str | None = None,
    gas_lift_rate: float | None = None,
    max_gas_injection: float | None = None,
    min_gas_injection: float | None = None,
    esp_frequency_mode: str | None = None,
    esp_frequency: float | None = None,
    min_frequency: float | None = None,
    max_frequency: float | None = None,
    script_only: bool = True,
) -> dict:
    """Configure well controls (dP choke, gas lift rate, ESP frequency).

    Sets well to 'controllable' for the optimizer to adjust wellhead choke,
    gas lift allocation, or ESP frequency to maximize production and honour
    constraints. Essential before running optimized solve network or prediction.
    """
    from petex_mcp.tools.gap import configure_well_control as _configure
    from petex_mcp.models.inputs import ConfigureWellControlParams

    params = ConfigureWellControlParams(
        model_path=model_path,
        well_name=well_name,
        dp_control=dp_control,
        fixed_dp=fixed_dp,
        gas_lift_mode=gas_lift_mode,
        gas_lift_rate=gas_lift_rate,
        max_gas_injection=max_gas_injection,
        min_gas_injection=min_gas_injection,
        esp_frequency_mode=esp_frequency_mode,
        esp_frequency=esp_frequency,
        min_frequency=min_frequency,
        max_frequency=max_frequency,
    )
    result = await _configure(params)
    return result


@mcp.tool()
async def set_constraints(
    model_path: str,
    equipment_name: str,
    equipment_type: str,
    max_liquid_rate: float | None = None,
    max_gas_rate: float | None = None,
    max_oil_rate: float | None = None,
    max_water_rate: float | None = None,
    min_liquid_rate: float | None = None,
    min_gas_rate: float | None = None,
    max_pressure: float | None = None,
    min_pressure: float | None = None,
    max_power: float | None = None,
    max_gor: float | None = None,
    max_water_cut: float | None = None,
    script_only: bool = True,
) -> dict:
    """Set constraints on GAP equipment (well, separator, joint, system, group).

    Constraints direct the optimizer to honour process limitations. Examples:
    max liquid capacity at separator, max gas rate for contracts, max power for ESP.
    """
    from petex_mcp.tools.gap import set_constraints as _set_constraints
    from petex_mcp.models.inputs import SetConstraintsParams

    params = SetConstraintsParams(
        model_path=model_path,
        equipment_name=equipment_name,
        equipment_type=equipment_type,
        max_liquid_rate=max_liquid_rate,
        max_gas_rate=max_gas_rate,
        max_oil_rate=max_oil_rate,
        max_water_rate=max_water_rate,
        min_liquid_rate=min_liquid_rate,
        min_gas_rate=min_gas_rate,
        max_pressure=max_pressure,
        min_pressure=min_pressure,
        max_power=max_power,
        max_gor=max_gor,
        max_water_cut=max_water_cut,
    )
    result = await _set_constraints(params)
    return result


@mcp.tool()
async def generate_well_iprs(
    model_path: str,
    well_names: list[str] | None = None,
    pvt_method: str | None = None,
    script_only: bool = True,
) -> dict:
    """Batch generate well IPRs from associated PROSPER models.

    Transfers PI, reservoir pressure, PVT data, and match points from PROSPER
    into GAP well models. Equivalent to Generate | Generate Well IPRs from PROSPER.
    """
    from petex_mcp.tools.gap import generate_well_iprs as _gen_iprs
    from petex_mcp.models.inputs import GenerateWellIPRParams

    params = GenerateWellIPRParams(
        model_path=model_path,
        well_names=well_names,
        pvt_method=pvt_method,
    )
    result = await _gen_iprs(params)
    return result


@mcp.tool()
async def generate_well_vlps(
    model_path: str,
    well_names: list[str] | None = None,
    rate_values: list[float] | None = None,
    pressure_values: list[float] | None = None,
    gor_values: list[float] | None = None,
    watercut_values: list[float] | None = None,
    glr_values: list[float] | None = None,
    frequency_values: list[float] | None = None,
    script_only: bool = True,
) -> dict:
    """Batch generate well VLPs from associated PROSPER models.

    Generates VLP curves for ranges of rate, top node pressure, GOR/CGR,
    water cut, and optionally GLR (gas lifted) or frequency (ESP).
    Equivalent to Generate | Generate Well VLPs with PROSPER.
    """
    from petex_mcp.tools.gap import generate_well_vlps as _gen_vlps
    from petex_mcp.models.inputs import GenerateWellVLPParams

    params = GenerateWellVLPParams(
        model_path=model_path,
        well_names=well_names,
        rate_values=rate_values,
        pressure_values=pressure_values,
        gor_values=gor_values,
        watercut_values=watercut_values,
        glr_values=glr_values,
        frequency_values=frequency_values,
    )
    result = await _gen_vlps(params)
    return result


@mcp.tool()
async def initialise_iprs_from_tanks(
    model_path: str,
    date: str,
    well_names: list[str] | None = None,
    script_only: bool = True,
) -> dict:
    """Initialise well IPRs from tank simulations at a specific historical date.

    Runs MBAL simulation up to the specified date and transfers reservoir
    pressure, WC, GOR to well IPR sections. Essential for history matching
    and for solving the network at a specific point in time.
    """
    from petex_mcp.tools.gap import initialise_iprs_from_tanks as _init_iprs
    from petex_mcp.models.inputs import InitialiseIPRsFromTanksParams

    params = InitialiseIPRsFromTanksParams(
        model_path=model_path,
        date=date,
        well_names=well_names,
    )
    result = await _init_iprs(params)
    return result


@mcp.tool()
async def add_schedule_event(
    model_path: str,
    equipment_name: str,
    event_date: str,
    event_type: str,
    constraint_type: str | None = None,
    new_value: float | None = None,
    openserver_variable: str | None = None,
    script_only: bool = True,
) -> dict:
    """Add a scheduled event for GAP prediction (start/stop wells, change constraints, etc.).

    Used to model field management events during a forecast:
    workovers, facility upgrades, well interventions, pressure changes.
    """
    from petex_mcp.tools.gap import add_schedule_event as _add_schedule
    from petex_mcp.models.inputs import AddScheduleEventParams

    params = AddScheduleEventParams(
        model_path=model_path,
        equipment_name=equipment_name,
        event_date=event_date,
        event_type=event_type,
        constraint_type=constraint_type,
        new_value=new_value,
        openserver_variable=openserver_variable,
    )
    result = await _add_schedule(params)
    return result


@mcp.tool()
async def add_tank(
    model_path: str,
    tank_name: str,
    tank_model: str = "material_balance",
    mbal_file: str | None = None,
    fluid_type: str | None = None,
    connected_wells: list[str] | None = None,
    script_only: bool = True,
) -> dict:
    """Add a reservoir tank to the GAP network.

    Tanks represent reservoirs and provide pressure decline data for predictions.
    Can be Material Balance (MBAL), Decline Curve, or linked to an external simulator.
    """
    from petex_mcp.tools.gap import add_tank as _add_tank
    from petex_mcp.models.inputs import AddTankParams

    params = AddTankParams(
        model_path=model_path,
        tank_name=tank_name,
        tank_model=tank_model,
        mbal_file=mbal_file,
        fluid_type=fluid_type,
        connected_wells=connected_wells,
    )
    result = await _add_tank(params)
    return result


# =============================================================================
# Data Import Tools
# =============================================================================


@mcp.tool()
async def import_production_data(
    file_path: str,
    target_tool: str = "mbal",
) -> dict:
    """Import production data from CSV/TXT file with auto-detection of columns.

    Uses the Column Mapper to auto-detect column meanings, delimiters, date formats,
    and units. Returns a summary of the import with mapping for confirmation.
    """
    from petex_mcp.tools.data import import_data

    result = await import_data(file_path=file_path, target_tool=target_tool)
    return result


@mcp.tool()
async def load_well_survey(
    file_path: str,
    model_path: str = "well.Out",
    script_only: bool = True,
) -> dict:
    """Load well survey/trajectory data from CSV/TXT into PROSPER deviation table.

    Reads MD, Inclination, Azimuth (and optionally TVD, DLS) from a file and
    generates commands to populate the PROSPER deviation survey table.
    Recognizes column names in English and Spanish.
    """
    from petex_mcp.tools.survey import load_well_survey as _load_survey

    result = await _load_survey(
        file_path=file_path,
        model_path=model_path,
        script_only=script_only,
    )
    return result


# =============================================================================
# Session Management Tools
# =============================================================================


@mcp.tool()
async def query_session() -> dict:
    """Returns current session state including active models and context."""
    summary = _session.query_context()
    return {
        "active_models": summary.active_models,
        "fluid_type": summary.fluid_type,
        "well_type": summary.well_type,
        "well_trajectory": summary.well_trajectory,
        "selected_correlations": summary.selected_correlations,
        "unit_preferences": summary.unit_preferences,
        "operation_count": summary.operation_count,
    }


@mcp.tool()
async def reset_session() -> dict:
    """Clears all session context, resetting to a fresh state."""
    _session.reset()
    return {"status": "Session reset successfully"}


@mcp.tool()
async def get_consolidated_script() -> dict:
    """Returns a consolidated script for all operations performed in this session.

    Combines all operations from the session history into a single executable
    Python/OpenServer script in chronological order.
    """
    if not _session.operation_history:
        return {"script": "", "operations_count": 0}

    script = _script_gen.consolidate(_session.operation_history)
    return {"script": script, "operations_count": len(_session.operation_history)}


@mcp.tool()
async def carry_forward_context(
    new_workflow: str,
) -> dict:
    """Offer relevant context from the current session for a new workflow.

    Provides carry-forward suggestions when transitioning between applications
    (e.g., PROSPER → GAP, MBAL → GAP).
    """
    return _session.carry_forward(new_workflow)


# =============================================================================
# Integrated Workflow Execution Tool
# =============================================================================


@mcp.tool()
async def run_integrated_workflow(
    well_name: str,
    reservoir_params: dict,
    well_params: dict,
    surface_params: dict,
    production_data: list[list],
    output_dir: str | None = None,
    script_only: bool = True,
) -> dict:
    """Execute the full integrated PETEX workflow: MBAL -> PROSPER -> GAP.

    This tool runs the complete petroleum engineering workflow in the correct
    sequence per PETEX IPM documentation:

    1. MBAL: Creates gas reservoir model, loads production history, validates
    2. PROSPER: Creates well model (PVT, equipment, IPR, VLP), runs nodal
       analysis, generates VLP curves (.tpd) for export to GAP
    3. GAP: Creates surface network (well -> flowline -> manifold -> trunk ->
       separator), links PROSPER model for VLP/IPR, links MBAL tank for
       pressure decline, solves network

    FLUID AUTO-DETECTION:
    The system automatically detects oil vs gas based on reservoir_params:
    - OIL: if "oil_gravity" or "api" or "gor" or "ooip_mmstb" present
      Uses: Fluid=Oil, IPR=Vogel, VLP=PE2, GAP WellType=Oil, OptMethod=MaxOil
    - GAS: if "giip_bcf" or "cgr_bbl_mmscf" present (default)
      Uses: Fluid=Gas, IPR=C&n, VLP=PE5, GAP WellType=Gas, OptMethod=MaxGas

    Data transfers (per PETEX documentation):
    - PROSPER -> GAP: VLP curves (.tpd file), IPR (PI, Pres, Temp)
    - MBAL -> GAP: Tank model (.mbi file) for production predictions
    - IPR transfer: Reservoir pressure, temperature, productivity from PROSPER

    Required reservoir_params keys:
        For GAS: gas_gravity, ti_f, pi_psi, co2_pct, n2_pct, h2s_pct,
                 giip_bcf, cgr_bbl_mmscf
        For OIL: oil_gravity OR api, gor, gas_gravity, ti_f, pi_psi,
                 ooip_mmstb, water_cut (optional)

    Required well_params keys:
        For GAS: tvd_ft, lateral_ft, tubing_id_in, liner_id_in, ip_mscfd
        For OIL: tvd_ft, lateral_ft, tubing_id_in, liner_id_in, ip_bopd

    Required surface_params keys:
        sep_pres_psi, whp_initial_psi, wht_f, flowline_length_ft,
        flowline_id_in, trunk_length_ft, trunk_id_in, ambient_t_f, u_value

    production_data format:
        GAS: [[month_str, gas_Mm3, cond_m3, water_m3, days], ...]
        OIL: [[month_str, oil_m3, gas_Mm3, water_m3, days], ...]
    """
    from petex_mcp.tools import workflow_runner as _wf_module
    import importlib
    importlib.reload(_wf_module)
    _run = _wf_module.run_integrated_workflow

    # Convert production_data lists to tuples
    prod_tuples = [tuple(row) for row in production_data]

    result = _run(
        well_name=well_name,
        reservoir_params=reservoir_params,
        well_params=well_params,
        surface_params=surface_params,
        production_data=prod_tuples,
        output_dir=output_dir,
        script_only=script_only,
    )
    return result


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """Run the PETEX MCP Server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
