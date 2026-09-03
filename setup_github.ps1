# Setup del repo GitHub para MCP PETEX v2
# Reemplazar la URL del repo con la tuya antes de correr.

$REPO_URL = "https://github.com/TU_USUARIO/mcp-petex-v2.git"

git init

# --- MCP core ---
git add petex_mcp_server.py          # el server (14 tools)
git add petex_rag.py                 # motor RAG
git add petex_corrections.py         # cache de correcciones
git add petex_executor.py            # SmartExecutor (auto-correccion)
git add petex_orchestrator.py        # orquestador end-to-end
git add petex_scanner.py             # escaner curado (legible)
git add petex_scanner_full.py        # escaner exhaustivo
git add mcp_petex_v2_prototype.py    # funciones de workflow
git add wait_for_mbal.py             # espera de licencia + auto-run

# --- Catalogos y config ---
git add corrections_seed.json        # correcciones verificadas (semilla)
git add petex_catalog.json           # catalogo de variables del manual
git add catalog_fields_curated.json  # campos verificados por array
git add mcp_config_para_kiro.json    # config para Kiro
git add build_catalog.py             # generador del catalogo
git add consolidate_catalog.py       # consolidador del catalogo

# --- Documentacion ---
git add MCP_PETEX_Hallazgos.md
git add mcp_petex_design.md
git add mcp_petex_variables.md
git add mcp_petex_mbal_variables.md
git add mcp_petex_gap_variables.md
git add mcp_petex_workflows.md
git add roadmap_mcp_petex.html
git add guia_mcp_petex.html

# --- Knowledge base de ingenieria ---
git add knowledge_base/

# --- Config del repo ---
git add .gitignore
git add setup_github.ps1

git commit -m "MCP PETEX v2: server 14 tools, RAG, auto-correccion, orquestador, escaner exhaustivo"
git branch -M main
git remote add origin $REPO_URL
git push -u origin main
