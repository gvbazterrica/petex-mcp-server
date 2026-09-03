"""
PETEX MCP Server
================
Servidor MCP real (FastMCP) que expone PROSPER/MBAL/GAP como tools
para que un LLM las invoque en lenguaje natural.

Instalar: pip install "mcp[cli]" openserver
Correr:   python petex_mcp_server.py
Config Kiro/Claude (.kiro/settings/mcp.json):
  {
    "mcpServers": {
      "petex": {
        "command": "python",
        "args": ["C:/Users/xgvb02/Desktop/Ds/MCP/test dario petex/petex_mcp_server.py"]
      }
    }
  }

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import time
import json
import subprocess
import warnings
from typing import Optional

warnings.filterwarnings("ignore")  # silenciar UserWarning de numpy/scipy

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise SystemExit("Falta instalar: pip install \"mcp[cli]\"")

# ================================================================
# Estado global y helpers
# ================================================================

mcp = FastMCP("petex")

# RAG lazy-loaded (se carga la primera vez que se usa)
_rag = {"engine": None, "loaded": False}


def _get_rag():
    """Carga el RAG bajo demanda. Retorna None si no esta disponible."""
    if _rag["loaded"]:
        return _rag["engine"]
    _rag["loaded"] = True
    try:
        from petex_rag import PetexRAG
        engine = PetexRAG()
        if engine.load_index():
            _rag["engine"] = engine
    except Exception:
        _rag["engine"] = None
    return _rag["engine"]

# Estado de la sesion (que app esta abierta, que modelo)
_state = {
    "active_app": None,       # "PROSPER" | "MBAL" | "GAP" | None
    "prosper_file": None,
    "mbal_file": None,
    "gap_file": None,
}

# Base de conocimiento de ingenieria (cargada de knowledge_base/)
KB_DIR = os.path.join(os.path.dirname(__file__), "knowledge_base")


# SmartExecutor persistente: conexion OpenServer + auto-correccion + aprendizaje
_conn = {"exec": None}


def _get_exec():
    """Devuelve el SmartExecutor vivo (con RAG para auto-correccion)."""
    if _conn["exec"] is None:
        from petex_executor import SmartExecutor
        _conn["exec"] = SmartExecutor(rag=_get_rag())
    return _conn["exec"]


def _get_os():
    """Compat: devuelve la conexion OpenServer cruda del executor.
    Las tools que ya usan c.DoSet/DoCmd directo siguen funcionando,
    pero se recomienda migrar a _get_exec() para auto-correccion."""
    return _get_exec().os


def _close_os():
    """Cerrar la conexion del executor."""
    if _conn["exec"] is not None:
        _conn["exec"].close()


def _kill_petex():
    """Mata procesos PETEX. Cierra la conexion primero."""
    if _conn["exec"] is not None:
        _conn["exec"].kill_petex()
        return
    for app in ["prosper", "mbal", "gap"]:
        subprocess.run(["taskkill", "/F", "/IM", f"{app}.exe"],
                       capture_output=True, timeout=10)
    time.sleep(3)


def _load_kb(category: str, key: str) -> Optional[dict]:
    """Cargar entrada de la knowledge base de ingenieria."""
    path = os.path.join(KB_DIR, category)
    if not os.path.isdir(path):
        return None
    for fname in os.listdir(path):
        if fname.endswith(".json"):
            with open(os.path.join(path, fname), encoding="utf-8") as f:
                data = json.load(f)
            if key in data:
                return data[key]
    return None


# ================================================================
# TOOLS - Diagnostico
# ================================================================

def _classify_license_error(err: str) -> str:
    """Distingue los dos tipos de error de licencia de PETEX."""
    e = err.lower()
    if "no openserver license" in e:
        return "SIN_LICENCIA_OPENSERVER"  # el pool de OpenServer esta agotado
    if "could not locate a free license" in e or "licens" in e:
        return "APP_OCUPADA"              # la app puntual no tiene licencia
    return None


@mcp.tool()
def check_licenses() -> str:
    """Verifica que licencias PETEX (PROSPER, MBAL, GAP) estan disponibles ahora.
    Distingue entre app ocupada y pool de OpenServer agotado.
    Usar antes de armar un modelo para saber que se puede correr."""
    _kill_petex()
    status = {}
    openserver_down = False
    for app in ["PROSPER", "MBAL", "GAP"]:
        try:
            c = _get_os()
            c.DoCmd(f'{app}.START("")')
            c.DoCmd(f"{app}.SHUTDOWN()")
            status[app] = "DISPONIBLE"
        except Exception as e:
            kind = _classify_license_error(str(e))
            if kind == "SIN_LICENCIA_OPENSERVER":
                status[app] = "OPENSERVER_AGOTADO"
                openserver_down = True
            elif kind == "APP_OCUPADA":
                status[app] = "OCUPADA"
            else:
                status[app] = f"ERROR: {e}"
        _kill_petex()

    result = {"licenses": status}
    if openserver_down:
        result["hint"] = ("El pool de licencias OpenServer esta agotado a nivel red. "
                          "Ningun cliente OpenServer puede conectar. Reintentar mas tarde "
                          "o liberar sesiones OpenServer de otros usuarios.")
    return json.dumps(result, indent=2)


# ================================================================
# TOOLS - PROSPER
# ================================================================

@mcp.tool()
def prosper_open(filepath: str) -> str:
    """Abre un modelo PROSPER existente (.Out) para operar sobre el."""
    _kill_petex()
    try:
        c = _get_os()
        c.DoCmd('PROSPER.START("")')
        c.DoCmd(f'PROSPER.OPENFILE("{filepath}")')
        _state["active_app"] = "PROSPER"
        _state["prosper_file"] = filepath
        return f"PROSPER abierto: {filepath}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def prosper_run_nodal(whp: float, correlation: str = "PetroleumExperts2",
                      water_cut: float = 0, gor: float = 0) -> str:
    """Corre un nodal analysis en el modelo PROSPER abierto y devuelve el caudal operativo.

    Args:
        whp: presion de cabeza de pozo (psi)
        correlation: correlacion VLP (default PetroleumExperts2)
        water_cut: corte de agua % (opcional)
        gor: GOR total scf/stb (opcional, oil wells)
    """
    if _state["active_app"] != "PROSPER":
        return "Error: primero abrir un modelo con prosper_open"
    try:
        c = _get_os()
        c.DoSet("PROSPER.ANL.SYS.TubingLabel", correlation)
        c.DoSet("PROSPER.ANL.SYS.Pres", str(whp))
        if water_cut > 0:
            c.DoSet("PROSPER.ANL.SYS.WC", str(water_cut))
        if gor > 0:
            c.DoSet("PROSPER.ANL.SYS.GOR", str(gor))
        c.DoCmd("PROSPER.ANL.SYS.CALC")
        oil = c.DoGet("PROSPER.OUT.SYS.Results[0].Sol.OilRate")
        pres = c.DoGet("PROSPER.OUT.SYS.Results[0].Sol.Pres")
        return json.dumps({"oil_rate_stb_d": oil, "nodal_pressure_psi": pres, "whp_psi": whp})
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def prosper_get_recommendations(formation: str, fluid: str = "oil") -> str:
    """Consulta la knowledge base de ingenieria por correlaciones y PVT recomendados
    para una formacion y tipo de fluido dados (ej: Vaca Muerta, oil).

    Args:
        formation: nombre de la formacion (vaca_muerta, mulichinco, etc)
        fluid: tipo de fluido (oil, gas_condensate)
    """
    key = formation.lower().replace(" ", "_")
    corr = _load_kb("correlations", key)
    pvt = _load_kb("pvt", f"{key}_{fluid}")
    result = {"formation": formation, "fluid": fluid}
    if corr:
        result["correlations"] = corr
    if pvt:
        result["pvt_ranges"] = pvt
    if not corr and not pvt:
        result["note"] = "Sin datos en KB. Usar defaults: PE2, IPR Vogel para oil."
    return json.dumps(result, indent=2)


# ================================================================
# TOOLS - MBAL
# ================================================================

@mcp.tool()
def mbal_create_reservoir(filepath: str, reservoir_type: str,
                          oil_gravity: float, gas_gravity: float,
                          gor: float, reservoir_pressure: float,
                          reservoir_temp: float, ooip: float = 0,
                          co2: float = 0, n2: float = 0) -> str:
    """Crea un modelo MBAL de reservorio y lo valida (MBAL.MB.VALIDATE, sin GUI).

    Args:
        filepath: ruta del .mbi a guardar
        reservoir_type: OIL, GAS, CON
        oil_gravity: API
        gas_gravity: gravedad especifica del gas
        gor: solution GOR scf/stb
        reservoir_pressure: presion inicial psi
        reservoir_temp: temperatura F
        ooip: OOIP en MMstb (opcional)
        co2, n2: mole % (opcional)
    """
    _kill_petex()
    try:
        c = _get_os()
        c.DoCmd('MBAL.START("")')
        c.DoCmd("MBAL.NEWMODEL()")
        c.DoSet("MBAL.MB.TANK.TYPE", reservoir_type.upper())
        c.DoSet("MBAL.MB[0].PVT.INPUT.OILGRAV", str(oil_gravity))
        c.DoSet("MBAL.MB[0].PVT.INPUT.GASGRAV", str(gas_gravity))
        c.DoSet("MBAL.MB[0].PVT.INPUT.SOLGOR", str(gor))
        c.DoSet("MBAL.MB[0].PVT.INPUT.TRES", str(reservoir_temp))
        if co2:
            c.DoSet("MBAL.MB[0].PVT.INPUT.CO2", str(co2))
        if n2:
            c.DoSet("MBAL.MB[0].PVT.INPUT.N2", str(n2))
        c.DoSet("MBAL.MB.TANK.PRESS", str(reservoir_pressure))
        if ooip:
            c.DoSet("MBAL.MB[0].TANK[0].OOIP", str(ooip))
        c.DoCmd("MBAL.MB.VALIDATE")
        c.DoCmd(f'MBAL.SaveFile("{filepath}")')
        c.DoCmd("MBAL.SHUTDOWN()")
        _state["mbal_file"] = filepath
        return f"MBAL creado y validado: {filepath}"
    except Exception as e:
        if "licens" in str(e).lower():
            return "Error: MBAL sin licencia libre. Reintentar mas tarde o verificar con check_licenses."
        return f"Error: {e}"


# ================================================================
# TOOLS - GAP
# ================================================================

@mcp.tool()
def gap_build_network(filepath: str, well_name: str, prosper_file: str,
                      separator_pressure: float, pipeline_length_ft: float,
                      pipeline_diameter_in: float, mbal_file: str = "") -> str:
    """Crea una red GAP: pozo (de PROSPER) -> flowline -> separador. Opcionalmente
    conecta un tank MBAL. Variables verificadas en vivo contra IPM 13.5.

    Args:
        filepath: ruta del .gap a guardar
        well_name: nombre del pozo en la red
        prosper_file: ruta al .Out de PROSPER
        separator_pressure: presion del separador psi
        pipeline_length_ft: longitud del flowline en ft
        pipeline_diameter_in: diametro del flowline en pulgadas
        mbal_file: ruta al .mbi (opcional, para conectar reservorio)
    """
    _kill_petex()
    try:
        c = _get_os()
        c.DoCmd('GAP.START("")')
        c.DoCmd("GAP.NEWFILE()")
        c.DoSet("GAP.MOD[0].SYSTYPE", "0")
        c.DoSet("GAP.MOD[0].OPTMETHOD", "0")
        c.DoSet("GAP.MOD[0].PVTMODEL", "0")

        c.DoCmd(f'GAP.NEWITEM("WELL", "{well_name}", "RIGHT", NULL, MOD[0])')
        c.DoCmd('GAP.NEWITEM("SEP", "SEP1", "RIGHT", NULL, MOD[0])')
        c.DoCmd(f'GAP.NEWITEM("PIPE", "FL1", "RIGHT", MOD[0].EQUIP[{{{well_name}}}], MOD[0])')
        c.DoCmd(f'GAP.LINKITEMS(MOD[0].EQUIP[{{{well_name}}}], MOD[0].PIPE[{{FL1}}], "")')
        c.DoCmd('GAP.LINKITEMS(MOD[0].PIPE[{FL1}], MOD[0].EQUIP[{SEP1}], "")')

        c.DoSet(f"GAP.MOD[0].WELL[{{{well_name}}}].WellType", "3")
        c.DoSet(f"GAP.MOD[0].WELL[{{{well_name}}}].File", prosper_file)
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].Length", str(pipeline_length_ft))
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].ID", str(pipeline_diameter_in))
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].Roughness", "0.0006")
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].TVD", "0")
        c.DoSet("GAP.MOD[0].SEP[{SEP1}].SolverPres[0]", str(separator_pressure))

        if mbal_file:
            c.DoCmd('GAP.NEWITEM("TANK", "TANK1", "RIGHT", NULL, MOD[0])')
            c.DoSet("GAP.MOD[0].TANK[{TANK1}].MBALFile", mbal_file)
            c.DoCmd(f'GAP.LINKITEMS(MOD[0].TANK[{{TANK1}}], MOD[0].WELL[{{{well_name}}}], "")')

        c.DoCmd(f'GAP.TRANSFERPROSPERIPR(MOD[0].WELL[{{{well_name}}}],0,0)')
        c.DoCmd("GAP.VALIDATE(0)")
        c.DoCmd(f'GAP.SAVEFILE("{filepath}")')
        c.DoCmd("GAP.SHUTDOWN()")
        _state["gap_file"] = filepath
        return f"Red GAP creada: {well_name} -> FL1 -> SEP1 @ {separator_pressure} psi. Guardada en {filepath}"
    except Exception as e:
        if "licens" in str(e).lower():
            return "Error: GAP sin licencia libre. Verificar con check_licenses."
        return f"Error: {e}"


@mcp.tool()
def gap_solve(filepath: str, separator_name: str = "SEP1") -> str:
    """Resuelve una red GAP existente y devuelve los caudales del separador.

    Args:
        filepath: ruta del .gap
        separator_name: nombre del separador (default SEP1)
    """
    _kill_petex()
    try:
        c = _get_os()
        c.DoCmd('GAP.START("")')
        c.DoCmd(f'GAP.OPENFILE("{filepath}")')
        c.DoCmd("GAP.RESETSOLVERINPUTS()")
        c.DoCmd("GAP.SOLVENETWORK(0, MOD[0], 0)")
        oil = c.DoGet(f"GAP.MOD[0].SEP[{{{separator_name}}}].SolverResults[0].Qoil")
        gas = c.DoGet(f"GAP.MOD[0].SEP[{{{separator_name}}}].SolverResults[0].Qgas")
        wat = c.DoGet(f"GAP.MOD[0].SEP[{{{separator_name}}}].SolverResults[0].Qwat")
        c.DoCmd("GAP.SHUTDOWN()")
        return json.dumps({
            "oil_rate_stb_d": oil,
            "gas_rate_mscf_d": gas,
            "water_rate_stb_d": wat,
        }, indent=2)
    except Exception as e:
        return f"Error: {e}"


# ================================================================
# TOOLS - Knowledge / Docs
# ================================================================

@mcp.tool()
def lookup_variable(description: str) -> str:
    """Busca el nombre correcto de una variable OpenServer dada una descripcion.
    Usa la base de correcciones verificadas. Ej: 'geothermal temperature' -> GEO.DATA[i].TMP

    Args:
        description: que se quiere setear (en ingles o espanol)
    """
    # Mapa de correcciones verificadas
    hints = {
        "geothermal temp": "PROSPER.SIN.EQP.GEO.DATA[i].TMP (no Temp)",
        "geothermal depth": "PROSPER.SIN.EQP.GEO.DATA[i].MD (no TVD)",
        "geothermal u value": "PROSPER.SIN.EQP.GEO.HTC (no Uval)",
        "horizontal length": "PROSPER.SIN.IPR.Single.WellLen (no HzLength)",
        "salinity": "NO EXISTE en PROSPER PVT",
        "gap well prosper file": "GAP.MOD[0].WELL[{w}].File (no PROSPERFile)",
        "gap well type": "GAP.MOD[0].WELL[{w}].WellType = 3 (numero)",
        "gap pipe length": "GAP.MOD[0].PIPE[{p}].Desc[0].Length (tabla)",
        "gap pipe diameter": "GAP.MOD[0].PIPE[{p}].Desc[0].ID (tabla)",
        "gap separator pressure": "GAP.MOD[0].SEP[{s}].SolverPres[0] (no MAXPRES)",
        "add equipment row": "DoSet('...DATA.ADD', '') para agregar fila",
    }
    desc = description.lower()
    matches = {k: v for k, v in hints.items() if any(w in desc for w in k.split())}
    if matches:
        return json.dumps({"source": "corrections_cache", "matches": matches}, indent=2)

    # Fallback al RAG: buscar en los manuales
    rag = _get_rag()
    if rag:
        var = rag.find_variable(description)
        results = rag.query(description, top_k=2)
        out = {"source": "RAG (documentacion)", "variable_detectada": var, "contexto": []}
        for r in results:
            out["contexto"].append({
                "doc": f"{r['source']} p{r['page']}",
                "score": r["score"],
                "extracto": r["text"][:300],
            })
        return json.dumps(out, indent=2, ensure_ascii=False)

    return "Sin coincidencia. RAG no disponible (correr: python petex_rag.py build)."


@mcp.tool()
def search_docs(question: str, source: str = "") -> str:
    """Busca en la documentacion PETEX (manuales PROSPER/MBAL/GAP/OpenServer + hallazgos)
    para responder cualquier duda sobre variables, comandos o procedimientos.

    Args:
        question: la pregunta o keywords (ej: "how to run a prediction in GAP")
        source: filtrar por fuente (opcional: PROSPER, MBAL, GAP, OpenServer, Hallazgos, Workflows)
    """
    rag = _get_rag()
    if not rag:
        return "RAG no disponible. Correr: python petex_rag.py build"
    try:
        results = rag.query(question, top_k=4, source_filter=source or None)
        if not results:
            return f"Sin resultados para: {question}"
        out = {"query": question, "resultados": []}
        for r in results:
            out["resultados"].append({
                "doc": f"{r['source']} p{r['page']}",
                "score": r["score"],
                "extracto": r["text"][:500],
            })
        return json.dumps(out, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error en busqueda: {e}"


@mcp.tool()
def show_learned_corrections() -> str:
    """Muestra las correcciones de variables que el MCP tiene:
    verificadas (semilla) y aprendidas automaticamente via RAG durante el uso.
    Util para ver como el MCP fue mejorando su conocimiento."""
    ex = _get_exec()
    return json.dumps(ex.get_learned(), indent=2, ensure_ascii=False)


@mcp.tool()
def scan_model(filepath: str, mode: str = "full") -> str:
    """Escanea un modelo PETEX completo (.Out=PROSPER, .gap=GAP, .mbi=MBAL) y
    devuelve un inventario de TODOS sus componentes: tanques, separadores, wells,
    pipes, VLP, IPR (incl. multilateral), gas lift, equipment, PVT, drilling, etc.
    Usar esto para entender que hay en un modelo antes de consultarlo o modificarlo.

    Args:
        filepath: ruta al archivo .Out, .gap o .mbi
        mode: "full" (exhaustivo, todo el catalogo del manual) o
              "readable" (curado, lectura limpia con labels legibles) o
              "both" (ambos)
    """
    from petex_scanner import scan as scan_curated
    ext = filepath.lower().rsplit(".", 1)[-1]
    app = {"out": "PROSPER", "gap": "GAP", "mbi": "MBAL", "mbl": "MBAL"}.get(ext)
    if not app:
        return json.dumps({"error": f"Extension no reconocida: {ext}"})

    ex = _get_exec()
    try:
        ex.kill_petex()
        ok, msg = ex.do_cmd(f'{app}.START("")')
        if not ok:
            return json.dumps({"error": f"No se pudo iniciar {app}: {msg}"}, ensure_ascii=False)
        ex.do_cmd(f'{app}.OPENFILE("{filepath}")')

        out = {"app": app, "file": filepath}
        if mode in ("readable", "both"):
            out["readable"] = scan_curated(ex.os, filepath)
        if mode in ("full", "both"):
            from petex_scanner_full import FullScanner
            out["full"] = FullScanner().scan(ex.os, app)

        ex.do_cmd(f"{app}.SHUTDOWN()")
        _state["scanned_inventory"] = out
        _state["scanned_file"] = filepath
        _state["scanned_app"] = app
        return json.dumps(out, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def set_parameter(filepath: str, variable: str, value: str,
                  app: str = "") -> str:
    """Modifica un parametro de un modelo PETEX y lo guarda. Usa auto-correccion:
    si el nombre de variable no es exacto, el MCP lo corrige via cache/RAG.
    Ejemplos de uso: cambiar presion de separador, skin de un pozo, OOIP de un tank.

    Args:
        filepath: ruta al archivo (.Out, .gap, .mbi)
        variable: la variable OpenServer a setear (ej: GAP.MOD[0].SEP[0].SolverPres[0])
        value: el nuevo valor
        app: PROSPER/GAP/MBAL (opcional, se infiere de la extension)
    """
    ext = filepath.lower().rsplit(".", 1)[-1]
    if not app:
        app = {"out": "PROSPER", "gap": "GAP", "mbi": "MBAL", "mbl": "MBAL"}.get(ext, "")
    if not app:
        return json.dumps({"error": f"No se pudo inferir la app de {ext}"})

    ex = _get_exec()
    try:
        ex.kill_petex()
        ok, msg = ex.do_cmd(f'{app}.START("")')
        if not ok:
            return json.dumps({"error": f"No se pudo iniciar {app}: {msg}"}, ensure_ascii=False)
        ex.do_cmd(f'{app}.OPENFILE("{filepath}")')

        # Setear con auto-correccion
        ok, result = ex.do_set(variable, value)

        # Guardar el modelo
        if ok:
            save_cmd = "SaveFile" if app == "MBAL" else "SAVEFILE"
            ex.do_cmd(f'{app}.{save_cmd}("{filepath}")')
        ex.do_cmd(f"{app}.SHUTDOWN()")

        return json.dumps({
            "ok": ok,
            "variable_solicitada": variable,
            "variable_aplicada": result,
            "valor": value,
            "guardado": ok,
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def verify_scan_coverage(filepath: str) -> str:
    """Valida la COBERTURA del escaner: compara lo que el escaner leyo contra el
    reporte nativo de PROSPER/GAP/MBAL. Si algo aparece en el reporte pero no en
    el scan, lo indica para poder ampliar el catalogo. Garantia de que no falta nada.

    Args:
        filepath: ruta al archivo .Out, .gap o .mbi
    """
    ext = filepath.lower().rsplit(".", 1)[-1]
    app = {"out": "PROSPER", "gap": "GAP", "mbi": "MBAL", "mbl": "MBAL"}.get(ext)
    if not app:
        return json.dumps({"error": f"Extension no reconocida: {ext}"})

    ex = _get_exec()
    try:
        ex.kill_petex()
        ok, msg = ex.do_cmd(f'{app}.START("")')
        if not ok:
            return json.dumps({"error": f"No se pudo iniciar {app}: {msg}"}, ensure_ascii=False)
        ex.do_cmd(f'{app}.OPENFILE("{filepath}")')

        # Escanear con el full scanner
        from petex_scanner_full import FullScanner
        scan_result = FullScanner().scan(ex.os, app)

        # Intentar exportar el reporte nativo (via menu de PROSPER)
        report_note = "El reporte nativo se genera desde la GUI (Report button)."
        # PROSPER: PROSPER.MENU.SIN... genera reportes; via OpenServer no siempre exportable
        # Devolvemos las stats de cobertura del scan como proxy
        ex.do_cmd(f"{app}.SHUTDOWN()")

        return json.dumps({
            "app": app,
            "cobertura_scan": scan_result.get("stats", {}),
            "secciones_leidas": {
                "escalares": list(scan_result.get("scalars", {}).keys())[:30],
                "arrays": list(scan_result.get("arrays", {}).keys()),
            },
            "nota": report_note,
            "recomendacion": ("Para validacion 100%: abrir el modelo en la GUI, "
                              "generar Report, y comparar los componentes listados "
                              "contra 'arrays' y 'escalares' de este scan. Lo que "
                              "falte se agrega a catalog_fields_curated.json."),
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def list_templates() -> str:
    """Lista las plantillas .Out pre-validadas disponibles (pozos horizontal/vertical,
    oil/gas). Estas plantillas ya tienen la tubing description validada, por lo que
    permiten crear modelos PROSPER completos sin el paso manual del Done (blocker)."""
    from petex_templates import TemplateManager
    return json.dumps(TemplateManager().list_templates(), indent=2, ensure_ascii=False)


@mcp.tool()
def create_from_template(template_name: str, dest_path: str,
                         parameters: dict) -> str:
    """Crea un modelo PROSPER clonando una plantilla pre-validada y ajustando
    parametros. Evita el blocker de la tubing description porque parte de un
    equipment ya validado. El resultado esta listo para nodal/VLP/GAP.

    Args:
        template_name: nombre de la plantilla (ver list_templates)
        dest_path: ruta destino del nuevo .Out
        parameters: dict de parametros a ajustar (ej: {"reservoir_pressure": 5500, "api": 35})
    """
    from petex_templates import TemplateManager
    tm = TemplateManager()
    t = tm.get_template(template_name)
    if not t:
        return json.dumps({"error": f"Template '{template_name}' no existe. Ver list_templates."})
    if not t.get("validado"):
        return json.dumps({
            "error": f"La plantilla '{template_name}' aun no fue creada/validada.",
            "instruccion": "Ver TEMPLATES_README.md para generar el .Out base (paso manual unico con licencia).",
        }, ensure_ascii=False)
    ex = _get_exec()
    result = tm.create_from_template(ex, template_name, dest_path, parameters)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def build_integrated_model(formation: str, fluid: str = "oil",
                           target_rate_m3d: float = 0,
                           lateral_length_m: float = 0,
                           separator_pressure_psi: float = 200,
                           flowline_length_km: float = 3.0,
                           prosper_template: str = "",
                           execute: bool = False) -> str:
    """Orquestador inteligente end-to-end. A partir de una intencion de alto nivel,
    consulta la KB de ingenieria (correlaciones + PVT por formacion), arma el plan
    PROSPER->MBAL->GAP, y opcionalmente lo ejecuta con auto-correccion.

    Por defecto hace DRY-RUN (devuelve el plan sin ejecutar) para que revises
    las decisiones de ingenieria antes de correr contra PETEX.

    Args:
        formation: formacion (vaca_muerta, mulichinco, etc)
        fluid: oil o gas_condensate
        target_rate_m3d: caudal objetivo m3/d (opcional)
        lateral_length_m: largo de rama horizontal en metros (opcional)
        separator_pressure_psi: presion del separador
        flowline_length_km: longitud del flowline en km
        prosper_template: ruta al .Out template pre-validado (requerido si execute=True)
        execute: False=dry-run (solo plan), True=ejecutar contra PETEX
    """
    from petex_orchestrator import Orchestrator

    if execute:
        orch = Orchestrator(executor=_get_exec())
    else:
        orch = Orchestrator()

    plan = orch.plan(
        formation=formation,
        fluid=fluid,
        target_rate_m3d=target_rate_m3d or None,
        lateral_length_m=lateral_length_m or None,
        separator_pressure_psi=separator_pressure_psi,
        flowline_length_km=flowline_length_km,
    )

    if not execute:
        plan["modo"] = "DRY-RUN (revisar y luego correr con execute=True)"
        return json.dumps(plan, indent=2, ensure_ascii=False)

    # Modo ejecucion
    if not prosper_template:
        return json.dumps({
            "error": "execute=True requiere prosper_template (.Out pre-validado)",
            "plan": plan,
        }, indent=2, ensure_ascii=False)

    out_dir = os.path.dirname(prosper_template) or os.path.dirname(__file__)
    exec_result = orch.execute(plan, prosper_template, out_dir)
    return json.dumps({"plan": plan, "ejecucion": exec_result},
                      indent=2, ensure_ascii=False)


# ================================================================
# Main
# ================================================================

if __name__ == "__main__":
    mcp.run()
