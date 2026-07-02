# ═══════════════════════════════════════════════════════════════════════
# PETEX MCP Server — Instalador desde repositorio
# ═══════════════════════════════════════════════════════════════════════
# Ejecutar desde la raíz del repo clonado:
#   .\install.ps1
#
# Instala el MCP server y configura Kiro automáticamente.
# ═══════════════════════════════════════════════════════════════════════

param(
    [string]$InstallDir = "$env:USERPROFILE\.petex-mcp"
)

$ErrorActionPreference = "Stop"
$REPO_DIR = $PSScriptRoot
$VENV_DIR = "$InstallDir\.venv"
$KIRO_MCP_PATH = "$env:USERPROFILE\.kiro\settings\mcp.json"

Write-Host ""
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  PETEX MCP Server — Instalador" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ─── Verificar Python ───────────────────────────────────────────────
Write-Host "[1/4] Verificando Python..." -ForegroundColor Yellow
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "  ✗ Python no encontrado. Instalar Python 3.11+ primero." -ForegroundColor Red
    exit 1
}
$pyVersion = python --version 2>&1
Write-Host "  ✓ $pyVersion"

# ─── Crear virtualenv ──────────────────────────────────────────────
Write-Host ""
Write-Host "[2/4] Creando entorno virtual en: $VENV_DIR" -ForegroundColor Yellow
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
    python -m venv $VENV_DIR
    Write-Host "  ✓ Virtualenv creado"
} else {
    Write-Host "  ✓ Virtualenv existente reutilizado"
}

# ─── Instalar paquete ─────────────────────────────────────────────
Write-Host ""
Write-Host "[3/4] Instalando PETEX MCP Server..." -ForegroundColor Yellow

$pipPython = "$VENV_DIR\Scripts\python.exe"
& $pipPython -m pip install --upgrade pip --quiet 2>$null

# Instalar en modo editable desde el repo (o desde wheel si existe)
$wheelFile = Get-ChildItem "$REPO_DIR\dist\*.whl" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($wheelFile) {
    Write-Host "  Instalando desde wheel: $($wheelFile.Name)"
    & $pipPython -m pip install $wheelFile.FullName --quiet
} else {
    Write-Host "  Instalando desde fuente (modo editable)..."
    & $pipPython -m pip install -e $REPO_DIR --quiet
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Error en la instalación." -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Paquete instalado"

# ─── Configurar Kiro MCP ──────────────────────────────────────────
Write-Host ""
Write-Host "[4/4] Configurando Kiro..." -ForegroundColor Yellow

$kiroDir = Split-Path $KIRO_MCP_PATH
New-Item -ItemType Directory -Path $kiroDir -Force | Out-Null

# Leer config existente o crear nueva
$mcpConfig = @{}
if (Test-Path $KIRO_MCP_PATH) {
    try {
        $existing = Get-Content $KIRO_MCP_PATH -Raw | ConvertFrom-Json -AsHashtable
        if ($existing) { $mcpConfig = $existing }
    } catch {}
}

if (-not $mcpConfig.ContainsKey("mcpServers")) {
    $mcpConfig["mcpServers"] = @{}
}

$mcpConfig["mcpServers"]["petex"] = @{
    command = "$VENV_DIR\Scripts\python.exe"
    args = @("-m", "petex_mcp.server")
    env = @{
        PYTHONUNBUFFERED = "1"
    }
    disabled = $false
    autoApprove = @(
        "create_prosper_well", "set_pvt_data", "match_pvt_correlations",
        "set_equipment_data", "add_ipr_model", "add_vlp_correlation",
        "run_nodal_analysis", "run_sensitivity", "run_gradient_calculation",
        "generate_vlp_curves", "run_vlp_ipr_match", "design_gas_lift",
        "export_prosper_results", "load_well_survey",
        "create_mbal_model", "run_history_match", "estimate_ooip",
        "estimate_giip", "forecast_production", "montecarlo_reserves",
        "create_gap_model", "add_well_to_network", "add_pipeline",
        "add_separator", "add_compressor", "run_network",
        "optimize_network", "identify_bottlenecks", "run_prediction",
        "configure_well_control", "set_constraints",
        "generate_well_iprs", "generate_well_vlps",
        "add_tank", "add_schedule_event", "initialise_iprs_from_tanks",
        "import_production_data", "query_session", "reset_session",
        "get_consolidated_script", "carry_forward_context",
        "run_integrated_workflow"
    )
}

$mcpConfig | ConvertTo-Json -Depth 5 | Set-Content $KIRO_MCP_PATH -Encoding UTF8
Write-Host "  ✓ Kiro configurado: $KIRO_MCP_PATH"

# ─── Resumen ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✓ INSTALACIÓN COMPLETA" -ForegroundColor Green
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Instalado en: $InstallDir"
Write-Host "  Config Kiro:  $KIRO_MCP_PATH"
Write-Host ""
Write-Host "  → Reiniciá Kiro para activar el MCP server." -ForegroundColor Yellow
Write-Host ""
