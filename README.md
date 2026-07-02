# PETEX MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An MCP (Model Context Protocol) server that enables natural-language interaction with Petroleum Experts (PETEX) engineering tools — PROSPER, MBAL, and GAP — through AI assistants.

## What it does

This server exposes PETEX workflows as MCP tools that AI agents can invoke conversationally. Instead of manually navigating PETEX GUIs or writing OpenServer scripts from scratch, you describe what you need in plain language and the server generates complete, executable Python/OpenServer scripts.

```
User: "Create a horizontal oil well at 3000m with ESP at 60 Hz"

→ Server generates 49 OpenServer commands covering:
  System Summary, PVT, Equipment, IPR, VLP, Lift, Analysis
→ Returns a ready-to-run .py script for PROSPER
```

## Features

- **PROSPER** — Well modeling, nodal analysis, sensitivity studies, result export
- **MBAL** — Material balance, history matching, OOIP/GIIP estimation, production forecasting, Monte Carlo reserves
- **GAP** — Production network modeling, optimization, bottleneck identification
- **Data Import** — CSV/TXT ingestion with automatic column detection (English/Spanish headers)
- **Survey Loader** — Deviation survey import from CSV into PROSPER
- **Session Context** — Tracks state across tool calls, carries forward context between workflows

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

### Requirements

- Python 3.11+
- PETEX software installed (PROSPER, MBAL, GAP) — required only for script execution
- Windows (OpenServer COM interface requires Windows)

## Usage

### As an MCP server

```bash
petex-mcp
```

Or directly:

```bash
python -m petex_mcp.server
```

### MCP client configuration

Add to your MCP client config (e.g., `.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "petex": {
      "command": "petex-mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Available Tools

### PROSPER (Well Modeling)

| Tool | Description |
|------|-------------|
| `create_prosper_well` | Create a complete well model with all 7 sections configured |
| `add_ipr_model` | Add or modify the IPR model |
| `add_vlp_correlation` | Add or modify the VLP correlation |
| `add_lift_method` | Add or modify artificial lift configuration |
| `add_completion` | Add or modify completion type |
| `run_nodal_analysis` | Run system analysis at one or multiple conditions |
| `run_sensitivity` | Parametric sensitivity on any well variable |
| `export_prosper_results` | Export results to CSV, Excel, or JSON |
| `load_well_survey` | Load deviation survey from CSV/TXT |

### MBAL (Material Balance)

| Tool | Description |
|------|-------------|
| `create_mbal_model` | Create a material balance model with PVT and production history |
| `run_history_match` | Run analytical history matching with aquifer models |
| `estimate_ooip` | Retrieve OOIP from a matched model |
| `estimate_giip` | Retrieve GIIP from a matched model |
| `forecast_production` | Run production forecast with abandonment conditions |
| `montecarlo_reserves` | Probabilistic reserves estimation (P10/P50/P90) |

### GAP (Network Modeling)

| Tool | Description |
|------|-------------|
| `create_gap_model` | Create a new production network |
| `open_network` | Open and inspect an existing network |
| `add_well_to_network` | Add a well (optionally linked to a PROSPER model) |
| `add_pipeline` | Add a pipeline between nodes |
| `add_separator` | Add a separator with capacity |
| `add_compressor` | Add a compressor with pressure settings |
| `run_network` | Solve the network |
| `optimize_network` | Optimize for max oil, max gas, or min energy |
| `identify_bottlenecks` | Find restricted wells, pipelines, and facilities |

### Utilities

| Tool | Description |
|------|-------------|
| `import_production_data` | Import CSV/TXT with auto-detection of columns and units |
| `query_session` | Inspect current session state |
| `reset_session` | Clear session context |
| `get_consolidated_script` | Get a single script combining all session operations |
| `carry_forward_context` | Transfer context between workflows (e.g., PROSPER → GAP) |

## Architecture

```
petex_mcp/
├── server.py              # MCP tool registration and entry point
├── tools/
│   ├── prosper.py         # PROSPER well modeling tools (~49 commands per well)
│   ├── mbal.py            # MBAL material balance tools
│   ├── gap.py             # GAP network modeling tools
│   ├── survey.py          # Deviation survey loader
│   └── data.py            # Production data import with column mapping
├── models/
│   ├── commands.py        # OpenServerCommand dataclass
│   ├── enums.py           # All PETEX enumerations
│   ├── inputs.py          # Pydantic input models (validation + defaults)
│   └── outputs.py         # Result dataclasses
├── script/
│   └── generator.py       # Python/OpenServer script generation
├── conversation/
│   ├── session.py         # Session state management
│   └── engine.py          # Conversational completeness checking
└── errors/
    └── exceptions.py      # Structured error hierarchy
```

## Design Principles

1. **Always generates executable models** — Every `create_prosper_well` call produces a complete .Out file with all 7 sections (System Summary, PVT, Equipment, IPR, VLP, Lift, Analysis).

2. **Smart defaults, always disclosed** — The server applies engineering defaults (correlations, dimensions, gradients) and reports exactly what it chose. Users can override anything incrementally.

3. **Compatibility validation** — Catches invalid combinations before generating scripts (e.g., horizontal IPR on a vertical well, Fetkovitch on an oil well, ESP on an injector).

4. **Incremental workflow** — Each tool adds to the model without losing previous work. Session context tracks what's been configured.

5. **Script-only by default** — Generates scripts without requiring a live PETEX connection. Scripts can be executed later on a machine with PETEX installed.

## Example Workflow

```python
# 1. Create a well model
create_prosper_well(well_type="producer", fluid="oil", depth=3000,
                    well_trajectory="horizontal", lateral_length=1500,
                    lift_method="ESP", frequency=60)

# 2. Load a real deviation survey
load_well_survey(file_path="survey.csv", model_path="PROSPER_producer_oil.Out")

# 3. Run nodal analysis at multiple WHPs
run_nodal_analysis(model_path="PROSPER_producer_oil.Out",
                   whp_range=[100, 200, 300, 400])

# 4. Create a network and link the well
create_gap_model(model_name="Field_Network")
add_well_to_network(model_path="Field_Network.gap", well_name="Well_1",
                    prosper_model_path="PROSPER_producer_oil.Out")
add_separator(model_path="Field_Network.gap", separator_name="Sep_1",
              capacity=20000)
add_pipeline(model_path="Field_Network.gap", pipeline_name="Line_1",
             source_node="Well_1", destination_node="Sep_1",
             length=2000, diameter=4)

# 5. Solve and optimize
run_network(model_path="Field_Network.gap")
optimize_network(model_path="Field_Network.gap", objective="max_oil")
```

## Testing

```bash
pytest
```

The test suite covers all three tool modules with 100+ unit tests validating script generation, default application, compatibility checks, and session management.

## License

MIT
