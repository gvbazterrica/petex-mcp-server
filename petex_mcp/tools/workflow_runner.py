"""
Workflow Runner - Ejecuta secuencia integrada MBAL -> PROSPER -> GAP
====================================================================
Detecta automaticamente el tipo de fluido (oil/gas) y configura cada
aplicacion de acuerdo a las convenciones PETEX:

OIL:
  - MBAL: ResType=0 (Oil), OOIP, Np/Wp/GOR history
  - PROSPER: Fluid=0, PVT oil (API, GOR, Sg), IPR=Vogel/PI, VLP=PE2
  - GAP: WellType=1 (Oil producer), OptMethod=0 (Max Oil)

GAS:
  - MBAL: ResType=1 (Gas), GIIP, Gp/WGR history
  - PROSPER: Fluid=1, PVT gas (Sg, CGR), IPR=C&n, VLP=PE5
  - GAP: WellType=0 (Gas producer), OptMethod=1 (Max Gas)

Deteccion de fluido:
  - Si reservoir_params tiene "oil_gravity" o "api" -> OIL
  - Si reservoir_params tiene "gor" (no cgr) -> OIL
  - Si reservoir_params tiene "fluid" == "oil" -> OIL
  - Default: GAS

Secuencia segun documentacion PETEX IPM:
1. MBAL: Crear modelo de reservorio, history match, obtener Pi
2. PROSPER: Crear modelo de pozo, generar VLP curves (.tpd)
3. GAP: Crear red, importar VLP/IPR, conectar tank, solve
"""
from __future__ import annotations

import os
import time
from datetime import datetime


class PetexCOM:
    """Wrapper COM con los metodos correctos para IPM 14+."""

    def __init__(self):
        import win32com.client  # lazy: solo se importa si se usa COM real
        self.server = win32com.client.Dispatch("PX32.OpenServer.1")
        self.log: list[dict] = []

    def cmd(self, target: str) -> int:
        ts = datetime.now().strftime("%H:%M:%S")
        result = self.server.DoCommand(target)
        self.log.append({"time": ts, "type": "CMD", "target": target, "result": result})
        return result

    def s(self, target: str, value) -> None:
        self.server.SetValue(target, str(value))

    def g(self, target: str) -> str:
        return self.server.GetValue(target)

    def err(self) -> str:
        return self.server.GetLastErrorMessage()


def _create_run_folder(well_name: str, base_dir: str | None = None) -> str:
    """Crea carpeta timestamped para el run actual."""
    if base_dir is None:
        base_dir = os.path.join(os.getcwd(), "runs")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    folder = os.path.join(base_dir, f"{ts}_{well_name}")
    os.makedirs(folder, exist_ok=True)
    return os.path.abspath(folder)


def _verify_file(path: str, min_size: int = 100) -> bool:
    """Verifica que el archivo existe y tiene contenido."""
    return os.path.isfile(path) and os.path.getsize(path) > min_size


def fast_license_check(timeout_sec: float = 6.0) -> bool:
    """Probe rapido de licencia PETEX usando un subproceso con kill duro.

    Importar win32com o hacer Dispatch puede COLGARSE indefinidamente en
    algunas maquinas (generacion de cache gen_py, escaneo de type-libs, o
    COM sin responder). Para no bloquear NUNCA el proceso principal, el
    probe corre en un subproceso separado que se mata si excede el timeout.

    Returns:
        True solo si el subproceso confirma licencia funcional dentro del timeout.
    """
    import subprocess
    import sys

    probe_code = (
        "import win32com.client as w;"
        "s=w.Dispatch('PX32.OpenServer.1');"
        "rc=s.DoCommand('PROSPER.START(\"\")');"
        "s.DoCommand('PROSPER.SHUTDOWN()') if rc==0 else None;"
        "print('LICENSE_OK' if rc==0 else 'NO_LICENSE')"
    )
    try:
        out = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        return "LICENSE_OK" in (out.stdout or "")
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _check_license_per_app(timeout_sec: float = 6.0) -> dict[str, bool]:
    """Verifica licencia para cada app PETEX por separado.

    Prueba PROSPER, MBAL y GAP individualmente. Cada probe usa un
    subproceso con timeout para no colgarse.

    Estrategia de 1 licencia a la vez:
    - Cada probe hace START → SHUTDOWN inmediato
    - Si una app responde OK, la marcamos como disponible
    - El workflow luego las usa de a una (serial)

    Returns:
        Dict con {"mbal": bool, "prosper": bool, "gap": bool}
    """
    import subprocess
    import sys

    results = {"mbal": False, "prosper": False, "gap": False}

    probes = {
        "prosper": (
            "import win32com.client as w;"
            "s=w.Dispatch('PX32.OpenServer.1');"
            "rc=s.DoCommand('PROSPER.START(\"\")');"
            "s.DoCommand('PROSPER.SHUTDOWN()') if rc==0 else None;"
            "print('OK' if rc==0 else 'NO')"
        ),
        "mbal": (
            "import win32com.client as w;"
            "s=w.Dispatch('PX32.OpenServer.1');"
            "rc=s.DoCommand('MBAL.START(\"\")');"
            "s.DoCommand('MBAL.SHUTDOWN()') if rc==0 else None;"
            "print('OK' if rc==0 else 'NO')"
        ),
        "gap": (
            "import win32com.client as w;"
            "s=w.Dispatch('PX32.OpenServer.1');"
            "rc=s.DoCommand('GAP.START(\"\")');"
            "s.DoCommand('GAP.SHUTDOWN()') if rc==0 else None;"
            "print('OK' if rc==0 else 'NO')"
        ),
    }

    # Probar PROSPER primero (más común). Si funciona, asumir que
    # MBAL y GAP también están disponibles (misma licencia OpenServer).
    for app, code in probes.items():
        try:
            out = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=timeout_sec,
            )
            if "OK" in (out.stdout or ""):
                # Si una app funciona, todas funcionan (misma licencia)
                results["mbal"] = True
                results["prosper"] = True
                results["gap"] = True
                return results
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    return results


def _generate_workflow_script(
    well_name: str,
    reservoir_params: dict,
    well_params: dict,
    surface_params: dict,
    production_data: list,
    run_folder: str,
    fluid: str,
) -> str:
    """Genera un script .py autocontenido y ejecutable del workflow completo.

    El script importa workflow_runner y ejecuta el workflow con script_only=False
    (ejecucion COM real) en una maquina con licencia PETEX.
    """
    import json

    prod_list = [list(row) for row in production_data]
    # Replace backslashes in paths for the docstring (avoid \U unicode escape)
    safe_folder = run_folder.replace("\\", "/")
    script = f'''"""
PETEX Integrated Workflow Script - {well_name}
Fluido detectado: {fluid.upper()}
Generado: {datetime.now().isoformat()}
Carpeta: {safe_folder}

Secuencia: MBAL -> PROSPER -> GAP (1 licencia a la vez, SHUTDOWN entre apps)
Ejecutar en maquina con PETEX IPM + licencia OpenServer:
    python {well_name}_workflow.py
"""
import sys
import os

# PYTHONPATH al paquete petex_mcp
sys.path.insert(0, r"C:\\Users\\xgvb02\\Desktop\\Ds\\MCP\\Petex")

from petex_mcp.tools.workflow_runner import run_integrated_workflow

WELL_NAME = {json.dumps(well_name)}
RESERVOIR_PARAMS = {json.dumps(reservoir_params, indent=4)}
WELL_PARAMS = {json.dumps(well_params, indent=4)}
SURFACE_PARAMS = {json.dumps(surface_params, indent=4)}
PRODUCTION_DATA = {json.dumps(prod_list, indent=4)}
OUTPUT_DIR = r"{run_folder}"

if __name__ == "__main__":
    result = run_integrated_workflow(
        well_name=WELL_NAME,
        reservoir_params=RESERVOIR_PARAMS,
        well_params=WELL_PARAMS,
        surface_params=SURFACE_PARAMS,
        production_data=[tuple(r) for r in PRODUCTION_DATA],
        output_dir=os.path.dirname(OUTPUT_DIR) or None,
        script_only=False,  # ejecucion COM real
    )
    import json as _json
    print(_json.dumps(result, indent=2, default=str))
'''
    return script


def _detect_fluid(reservoir_params: dict) -> str:
    """
    Detecta el tipo de fluido del reservorio basado en los parametros.

    Returns: "oil" o "gas"

    Logica de deteccion:
    - Si tiene key "fluid" explicito -> usa ese valor
    - Si tiene "oil_gravity" o "api" -> oil
    - Si tiene "gor" (gas-oil ratio, no CGR) -> oil
    - Si tiene "ooip_mmstb" -> oil
    - Default -> gas
    """
    # Explicit fluid key
    fluid_explicit = reservoir_params.get("fluid", "").lower()
    if fluid_explicit in ("oil", "black_oil", "heavy_oil"):
        return "oil"
    if fluid_explicit in ("gas", "dry_gas", "wet_gas", "condensate"):
        return "gas"

    # Detect by presence of oil-specific keys
    if "oil_gravity" in reservoir_params or "api" in reservoir_params:
        return "oil"
    if "gor" in reservoir_params and "cgr_bbl_mmscf" not in reservoir_params:
        return "oil"
    if "ooip_mmstb" in reservoir_params:
        return "oil"

    # Detect by CGR value — high CGR (>100 bbl/MMscf) suggests wet gas / near-oil
    # but still gas-condensate system in PROSPER
    if "giip_bcf" in reservoir_params:
        return "gas"

    return "gas"


def run_integrated_workflow(
    well_name: str,
    reservoir_params: dict,
    well_params: dict,
    surface_params: dict,
    production_data: list[tuple],
    output_dir: str | None = None,
    script_only: bool = True,
) -> dict:
    """
    Ejecuta el workflow integrado completo:
    MBAL (reservorio) -> PROSPER (pozo + VLP) -> GAP (red + solve)

    Detecta automaticamente si es oil o gas y configura cada modelo
    con los parametros, correlaciones e IPR correctos.

    Args:
        well_name: Nombre/sigla del pozo
        reservoir_params: Dict con propiedades del reservorio
            Gas: gas_gravity, ti_f, pi_psi, co2_pct, n2_pct, h2s_pct,
                 giip_bcf, cgr_bbl_mmscf
            Oil: oil_gravity OR api, gor, gas_gravity, ti_f, pi_psi,
                 ooip_mmstb, water_cut (optional)
        well_params: Dict con datos del pozo
            Gas: tvd_ft, lateral_ft, tubing_id_in, liner_id_in, ip_mscfd
            Oil: tvd_ft, lateral_ft, tubing_id_in, liner_id_in, ip_bopd
        surface_params: Dict con datos de superficie
            sep_pres_psi, whp_initial_psi, wht_f,
            flowline_length_ft, flowline_id_in,
            trunk_length_ft, trunk_id_in, ambient_t_f, u_value
        production_data: Lista de tuplas
            Gas: (mes, gas_Mm3, cond_m3, agua_m3, dias)
            Oil: (mes, oil_m3, gas_Mm3, agua_m3, dias)
        output_dir: Directorio base para runs (default: cwd/runs/)

    Returns:
        Dict con paths de archivos, resultados, log, y status
    """
    start_time = datetime.now()

    # Detectar fluido
    fluid = _detect_fluid(reservoir_params)
    is_oil = fluid == "oil"

    # Crear carpeta del run
    run_folder = _create_run_folder(well_name, output_dir)

    results = {
        "well_name": well_name,
        "fluid_type": fluid,
        "run_folder": run_folder,
        "start_time": start_time.isoformat(),
        "files": {},
        "results": {},
        "sequence": [],
        "status": {"mbal": "pending", "prosper": "pending", "gap": "pending"},
        "errors": [],
    }

    print(f"\n{'='*70}")
    print(f"  FLUID DETECTED: {'OIL' if is_oil else 'GAS'}")
    print(f"  Well: {well_name}")
    print(f"  Output: {run_folder}")
    print(f"{'='*70}")

    # ==================================================================
    # PASO 0: Generar script ejecutable SIEMPRE (rapido, sin COM)
    # ==================================================================
    script_text = _generate_workflow_script(
        well_name, reservoir_params, well_params, surface_params,
        production_data, run_folder, fluid,
    )
    script_path = os.path.join(run_folder, f"{well_name}_workflow.py")
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_text)
        results["files"]["script"] = script_path
        results["script"] = script_text
        results["sequence"].append("Script .py generado OK")
    except Exception as e:
        results["errors"].append(f"Script write: {e}")

    # ==================================================================
    # MODO SCRIPT-ONLY: no intentar COM, retornar al instante
    # ==================================================================
    if script_only:
        results["execution_mode"] = "script_only"
        results["status"] = {"mbal": "script_only", "prosper": "script_only", "gap": "script_only"}
        results["sequence"].append("Modo script_only: sin ejecucion COM")
        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()
        # Generar reporte HTML+PDF
        try:
            report_paths = _generate_report(
                run_folder, well_name, results,
                reservoir_params, well_params, surface_params, production_data,
            )
            results["files"]["report_html"] = report_paths["html"]
            results["files"]["report_pdf"] = report_paths["pdf"]
        except Exception as e:
            results["errors"].append(f"Reporte: {e}")
        return results

    # ==================================================================
    # CHECK DE LICENCIA PER-APP (intenta cada app por separado)
    # ==================================================================
    # Estrategia: probar cada app individualmente.
    # Si alguna está disponible, usarla y guardar el archivo.
    # 1 licencia a la vez: SHUTDOWN entre apps.
    # PROSPER se itera por pozo (solo 1 instancia activa).

    license_available = _check_license_per_app(timeout_sec=6.0)

    if not any(license_available.values()):
        results["execution_mode"] = "script_only"
        results["status"] = {"mbal": "no_license", "prosper": "no_license", "gap": "no_license"}
        results["execution_note"] = (
            "PETEX license no disponible para ninguna app (check rapido). "
            "Script generado para ejecucion manual en maquina con licencia."
        )
        results["sequence"].append("Sin licencia: workflow no ejecutado, script listo")
        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()
        # Generar reporte HTML+PDF
        try:
            report_paths = _generate_report(
                run_folder, well_name, results,
                reservoir_params, well_params, surface_params, production_data,
            )
            results["files"]["report_html"] = report_paths["html"]
            results["files"]["report_pdf"] = report_paths["pdf"]
        except Exception as e:
            results["errors"].append(f"Reporte: {e}")
        return results

    results["execution_mode"] = "live"
    px = PetexCOM()

    # ==================================================================
    # PASO 1: MBAL - Modelo de Reservorio
    # ==================================================================
    print("\n" + "=" * 70)
    print(f"PASO 1/3: MBAL - Modelo de Reservorio ({'OIL' if is_oil else 'GAS'})")
    print("=" * 70)

    mbal_path = os.path.join(run_folder, f"{well_name}_reservoir.mbi")

    try:
        px.cmd('MBAL.START("")')
        time.sleep(5)
        px.cmd("MBAL.NEWFILE()")
        time.sleep(1)

        if is_oil:
            _configure_mbal_oil(px, well_name, reservoir_params, production_data)
        else:
            _configure_mbal_gas(px, well_name, reservoir_params, production_data)

        # Validar y guardar
        px.cmd("MBAL.MB.VALIDATE")
        time.sleep(3)

        px.cmd(f'MBAL.SaveFile("{mbal_path}")')
        time.sleep(2)

        if _verify_file(mbal_path):
            results["files"]["mbal"] = mbal_path
            results["status"]["mbal"] = "ok"
            results["sequence"].append(f"MBAL: Reservorio {fluid} creado OK")
            print(f"  [OK] MBAL guardado: {mbal_path}")
        else:
            results["status"]["mbal"] = "error"
            results["errors"].append("MBAL: Archivo no se guardo correctamente")

        px.cmd("MBAL.SHUTDOWN()")
        time.sleep(2)

    except Exception as e:
        results["status"]["mbal"] = "error"
        results["errors"].append(f"MBAL: {e}")
        print(f"  [ERROR] MBAL: {e}")
        try:
            px.cmd("MBAL.SHUTDOWN()")
        except Exception:
            pass

    # ==================================================================
    # PASO 2: PROSPER - Modelo de Pozo + Generacion VLP
    # ==================================================================
    print("\n" + "=" * 70)
    print(f"PASO 2/3: PROSPER - Modelo de Pozo ({'OIL' if is_oil else 'GAS'}) + VLP")
    print("=" * 70)

    prosper_path = os.path.join(run_folder, f"{well_name}.Out")
    vlp_path = os.path.join(run_folder, f"{well_name}.tpd")

    try:
        px.cmd('PROSPER.START("")')
        time.sleep(5)
        px.cmd("PROSPER.NEWFILE()")
        time.sleep(1)

        if is_oil:
            _configure_prosper_oil(px, reservoir_params, well_params, surface_params)
        else:
            _configure_prosper_gas(px, reservoir_params, well_params, surface_params)

        # --- System Calc (nodal analysis) ---
        print("  Ejecutando System Calc (nodal analysis)...")
        px.s("PROSPER.ANL.SYS.Pres", surface_params["whp_initial_psi"])
        px.s("PROSPER.ANL.SYS.Temp", surface_params.get("wht_f", 120))
        px.cmd("PROSPER.ANL.SYS.CALC")
        time.sleep(12)

        if is_oil:
            rate = px.g("PROSPER.OUT.SYS.Results[0].Sol.OilRate")
            liq = px.g("PROSPER.OUT.SYS.Results[0].Sol.LiqRate")
            bhp = px.g("PROSPER.OUT.SYS.Results[0].Sol.Pres")
            print(f"  Resultado nodal: Qo={rate} STB/d, Qliq={liq}, BHP={bhp} psi")
            results["results"]["nodal_oil_rate_stbd"] = rate
            results["results"]["nodal_liq_rate_stbd"] = liq
            results["results"]["nodal_bhp_psi"] = bhp
        else:
            rate = px.g("PROSPER.OUT.SYS.Results[0].Sol.GasRate")
            bhp = px.g("PROSPER.OUT.SYS.Results[0].Sol.Pres")
            print(f"  Resultado nodal: Qg={rate} Mscf/d, BHP={bhp} psi")
            results["results"]["nodal_rate_mscfd"] = rate
            results["results"]["nodal_bhp_psi"] = bhp

        # --- Generar VLP Curves para GAP ---
        print("  Generando VLP curves (.tpd) para GAP...")
        _generate_vlp_curves(px, is_oil, vlp_path)

        # Guardar PROSPER
        px.cmd(f'PROSPER.SAVEFILE("{prosper_path}")')
        time.sleep(3)

        # Verificar archivos
        prosper_verified = _verify_file(prosper_path)
        vlp_verified = _verify_file(vlp_path, min_size=50)

        if prosper_verified:
            results["files"]["prosper"] = prosper_path
            print(f"  [OK] PROSPER: {prosper_path} ({os.path.getsize(prosper_path)} bytes)")
        if vlp_verified:
            results["files"]["vlp_tpd"] = vlp_path
            print(f"  [OK] VLP: {vlp_path} ({os.path.getsize(vlp_path)} bytes)")
        else:
            # Retry
            print("  [WARN] VLP no generado, reintentando...")
            px.cmd("PROSPER.ANL.VLP.CALC")
            time.sleep(40)
            px.cmd(f'PROSPER.ANL.VLP.EXPORT(0,"{vlp_path}")')
            time.sleep(5)
            if _verify_file(vlp_path, min_size=50):
                results["files"]["vlp_tpd"] = vlp_path
                print(f"  [OK] VLP (retry): {vlp_path}")
            else:
                results["errors"].append("PROSPER: VLP .tpd no generado")

        results["status"]["prosper"] = "ok"
        results["sequence"].append(f"PROSPER: Modelo {fluid} + VLP generadas")

        px.cmd("PROSPER.SHUTDOWN()")
        time.sleep(2)

    except Exception as e:
        results["status"]["prosper"] = "error"
        results["errors"].append(f"PROSPER: {e}")
        print(f"  [ERROR] PROSPER: {e}")
        try:
            px.cmd("PROSPER.SHUTDOWN()")
        except Exception:
            pass

    # ==================================================================
    # PASO 3: GAP - Red Integrada
    # ==================================================================
    print("\n" + "=" * 70)
    print(f"PASO 3/3: GAP - Red de Produccion ({'OIL' if is_oil else 'GAS'})")
    print("=" * 70)

    gap_path = os.path.join(run_folder, f"{well_name}_network.gap")

    try:
        px.cmd('GAP.START("")')
        time.sleep(5)
        px.cmd("GAP.NEWFILE()")
        time.sleep(2)

        _configure_gap(px, well_name, is_oil, reservoir_params, well_params,
                       surface_params, results)

        # --- Solve Network ---
        print("  Resolviendo red...")
        px.cmd("GAP.SOLVENETWORK")
        time.sleep(15)

        # Leer resultados segun fluido
        if is_oil:
            sep_oil = px.g("GAP.MOD.SEP[0].Results.Oil")
            sep_liq = px.g("GAP.MOD.SEP[0].Results.Liquid")
            well_whp = px.g("GAP.MOD.WELL[0].Results.WHP")
            well_bhp = px.g("GAP.MOD.WELL[0].Results.BHP")
            print(f"  Resultado: Qo_sep={sep_oil}, Qliq={sep_liq}, WHP={well_whp}, BHP={well_bhp}")
            results["results"]["network_oil_stbd"] = sep_oil
            results["results"]["network_liq_stbd"] = sep_liq
            result_check = sep_oil
        else:
            sep_gas = px.g("GAP.MOD.SEP[0].Results.Gas")
            well_whp = px.g("GAP.MOD.WELL[0].Results.WHP")
            well_bhp = px.g("GAP.MOD.WELL[0].Results.BHP")
            print(f"  Resultado: Qg_sep={sep_gas}, WHP={well_whp}, BHP={well_bhp}")
            results["results"]["network_gas_mscfd"] = sep_gas
            result_check = sep_gas

        results["results"]["network_whp_psi"] = well_whp
        results["results"]["network_bhp_psi"] = well_bhp

        # Validar resultado
        try:
            check_f = float(result_check) if result_check else 0
        except (ValueError, TypeError):
            check_f = 0

        if check_f <= 0:
            print("  [WARN] Red sin resultados, reintentando...")
            time.sleep(5)
            px.cmd("GAP.SOLVENETWORK")
            time.sleep(20)

        # Guardar
        px.cmd(f'GAP.SaveFile("{gap_path}")')
        time.sleep(3)

        if _verify_file(gap_path):
            results["files"]["gap"] = gap_path
            results["status"]["gap"] = "ok"
            results["sequence"].append(f"GAP: Red {fluid} resuelta")
            print(f"  [OK] GAP: {gap_path} ({os.path.getsize(gap_path)} bytes)")
        else:
            results["status"]["gap"] = "error"
            results["errors"].append("GAP: Archivo no guardado")

        px.cmd("GAP.SHUTDOWN()")
        time.sleep(2)

    except Exception as e:
        results["status"]["gap"] = "error"
        results["errors"].append(f"GAP: {e}")
        print(f"  [ERROR] GAP: {e}")
        try:
            px.cmd("GAP.SHUTDOWN()")
        except Exception:
            pass

    # ==================================================================
    # RESUMEN FINAL
    # ==================================================================
    end_time = datetime.now()
    duration = end_time - start_time
    results["end_time"] = end_time.isoformat()
    results["duration_seconds"] = duration.total_seconds()
    results["com_log"] = px.log

    print(f"\n{'='*70}")
    print(f"WORKFLOW COMPLETADO — Fluido: {fluid.upper()}")
    print(f"{'='*70}")
    print(f"  Carpeta: {run_folder}")
    print(f"  Duracion: {duration}")
    for app in ["mbal", "prosper", "gap"]:
        status = results["status"][app]
        icon = "OK" if status == "ok" else "ERROR"
        path = results["files"].get(app, "N/A")
        print(f"  {app.upper():8s}: [{icon}] {path}")
    if results["errors"]:
        for err in results["errors"]:
            print(f"  [!] {err}")
    print(f"{'='*70}")

    # ==================================================================
    # GENERAR REPORTE HTML + PDF
    # ==================================================================
    try:
        report_paths = _generate_report(
            run_folder, well_name, results,
            reservoir_params, well_params, surface_params, production_data,
        )
        results["files"]["report_html"] = report_paths["html"]
        results["files"]["report_pdf"] = report_paths["pdf"]
        print(f"  [OK] Reporte HTML: {report_paths['html']}")
        print(f"  [OK] Reporte PDF:  {report_paths['pdf']}")
    except Exception as e:
        results["errors"].append(f"Reporte: {e}")
        print(f"  [WARN] Reporte no generado: {e}")

    return results


# ======================================================================
# HELPER FUNCTIONS — Report Generation
# ======================================================================

def _generate_report(
    run_folder: str,
    well_name: str,
    results: dict,
    reservoir_params: dict,
    well_params: dict,
    surface_params: dict,
    production_data: list,
) -> dict[str, str]:
    """Genera reporte HTML + PDF del workflow."""
    from petex_mcp.report.generator import ReportGenerator

    gen = ReportGenerator(run_folder=run_folder, well_name=well_name)
    return gen.generate(
        results=results,
        reservoir_params=reservoir_params,
        well_params=well_params,
        surface_params=surface_params,
        production_data=production_data,
    )


# ======================================================================
# HELPER FUNCTIONS — MBAL Configuration
# ======================================================================

def _configure_mbal_oil(px: PetexCOM, well_name: str, rp: dict, prod: list[tuple]):
    """Configura MBAL para reservorio de oil."""
    px.s("MBAL.MB.GENERAL.Title", f"{well_name} - Oil Reservoir")
    px.s("MBAL.MB.GENERAL.ResType", "0")  # Oil reservoir

    # PVT Oil
    api = rp.get("api", rp.get("oil_gravity", 35))
    gor = rp.get("gor", 500)  # scf/stb
    sg = rp.get("gas_gravity", 0.75)
    px.s("MBAL.MB.PVT.Api", api)
    px.s("MBAL.MB.PVT.GasGrav", sg)
    px.s("MBAL.MB.PVT.GOR", gor)
    px.s("MBAL.MB.PVT.Tres", rp["ti_f"])
    px.s("MBAL.MB.PVT.Pres", rp["pi_psi"])
    px.s("MBAL.MB.PVT.CO2", rp.get("co2_pct", 0))
    px.s("MBAL.MB.PVT.N2", rp.get("n2_pct", 0))
    print(f"  PVT Oil: API={api}, GOR={gor} scf/stb, Sg={sg}")

    # Tank - OOIP
    ooip = rp.get("ooip_mmstb", 10)  # MMstb
    ooip_stb = ooip * 1e6
    px.s("MBAL.MB.TANK.OOIP", f"{ooip_stb:.0f}")
    px.s("MBAL.MB.TANK.Pi", rp["pi_psi"])
    px.s("MBAL.MB.TANK.Ti", rp["ti_f"])
    px.s("MBAL.MB.TANK.AQUIF.Model", "0")  # No aquifer (shale)
    print(f"  Tank: OOIP={ooip} MMstb, Pi={rp['pi_psi']} psi")

    # Produccion historica — oil: (mes, oil_m3, gas_Mm3, agua_m3, dias)
    np_acum_m3 = 0.0
    pi = float(rp["pi_psi"])
    ooip_m3 = ooip * 1e6 * 0.159  # STB to m3 (approx)

    for i, row in enumerate(prod):
        mes = row[0]
        oil_m3 = float(row[1])
        gas_mm3 = float(row[2]) if len(row) > 2 else 0
        agua_m3 = float(row[3]) if len(row) > 3 else 0
        dias = float(row[4]) if len(row) > 4 else 30

        np_acum_m3 += oil_m3
        # Simple pressure decline (material balance approx)
        pres = pi * (1 - 0.5 * np_acum_m3 / ooip_m3) if ooip_m3 > 0 else pi

        qo_stbd = oil_m3 / 0.159 / dias  # m3 -> STB/d
        np_stb = np_acum_m3 / 0.159
        wc = agua_m3 / (oil_m3 + agua_m3) * 100 if (oil_m3 + agua_m3) > 0 else 0

        px.s(f"MBAL.MB.HIST[{i}].Date", f"01/{mes[5:7]}/{mes[:4]}")
        px.s(f"MBAL.MB.HIST[{i}].Qo", f"{qo_stbd:.0f}")
        px.s(f"MBAL.MB.HIST[{i}].Np", f"{np_stb:.0f}")
        px.s(f"MBAL.MB.HIST[{i}].Pres", f"{pres:.0f}")
        px.s(f"MBAL.MB.HIST[{i}].WC", f"{wc:.1f}")

    print(f"  Historia: {len(prod)} meses cargados")


def _configure_mbal_gas(px: PetexCOM, well_name: str, rp: dict, prod: list[tuple]):
    """Configura MBAL para reservorio de gas."""
    px.s("MBAL.MB.GENERAL.Title", f"{well_name} - Gas Reservoir")
    px.s("MBAL.MB.GENERAL.ResType", "1")  # Gas reservoir

    # PVT Gas
    px.s("MBAL.MB.PVT.GasGrav", rp["gas_gravity"])
    px.s("MBAL.MB.PVT.Tres", rp["ti_f"])
    px.s("MBAL.MB.PVT.Pres", rp["pi_psi"])
    px.s("MBAL.MB.PVT.CO2", rp.get("co2_pct", 0))
    px.s("MBAL.MB.PVT.N2", rp.get("n2_pct", 0))
    print(f"  PVT Gas: Sg={rp['gas_gravity']}, CGR={rp.get('cgr_bbl_mmscf', 5)}")

    # Tank - GIIP
    giip_bcf = rp.get("giip_bcf", 10)
    giip_scf = giip_bcf * 1e9
    px.s("MBAL.MB.TANK.GIIP", f"{giip_scf:.0f}")
    px.s("MBAL.MB.TANK.Pi", rp["pi_psi"])
    px.s("MBAL.MB.TANK.Ti", rp["ti_f"])
    px.s("MBAL.MB.TANK.AQUIF.Model", "0")
    print(f"  Tank: GIIP={giip_bcf:.1f} Bcf, Pi={rp['pi_psi']} psi")

    # Produccion historica — gas: (mes, gas_Mm3, cond_m3, agua_m3, dias)
    gp_acum_mm3 = 0.0
    pi = float(rp["pi_psi"])
    giip_bcf = rp.get("giip_bcf", 10)
    giip_mm3 = giip_bcf * 1000 / 35.3147

    for i, row in enumerate(prod):
        mes = row[0]
        gas_mm3 = float(row[1])
        dias = float(row[4]) if len(row) > 4 else 30

        gp_acum_mm3 += gas_mm3
        pres = pi * (1 - gp_acum_mm3 / giip_mm3)
        qg_mscfd = gas_mm3 * 35.3147 * 1000 / dias
        gp_scf = gp_acum_mm3 * 35.3147 * 1e6

        px.s(f"MBAL.MB.HIST[{i}].Date", f"01/{mes[5:7]}/{mes[:4]}")
        px.s(f"MBAL.MB.HIST[{i}].Qg", f"{qg_mscfd:.0f}")
        px.s(f"MBAL.MB.HIST[{i}].Gp", f"{gp_scf:.0f}")
        px.s(f"MBAL.MB.HIST[{i}].Pres", f"{pres:.0f}")

    print(f"  Historia: {len(prod)} meses cargados")


# ======================================================================
# HELPER FUNCTIONS — PROSPER Configuration
# ======================================================================

def _configure_prosper_oil(px: PetexCOM, rp: dict, wp: dict, sp: dict):
    """
    Configura PROSPER para pozo de oil.

    PROSPER System Summary:
    - Fluid = 0 (Oil and Water)
    - Predict = 0 (Pressure only) or 1 (P&T)

    PVT: API, GOR, Gas Gravity, Solution GOR, Water salinity
    IPR: Vogel (below Pb), PI linear (above Pb), or Fetkovich
    VLP: Petroleum Experts 2 (oil multiphase)
    """
    print("  Configurando PROSPER para OIL...")

    # --- System Summary ---
    px.s("PROSPER.SIN.SUM.WellType", "0")       # Producer
    px.s("PROSPER.SIN.SUM.Fluid", "0")          # Oil and Water
    px.s("PROSPER.SIN.SUM.FlowType", "0")       # Tubing
    px.s("PROSPER.SIN.SUM.InflowType", "0")     # Single branch
    px.s("PROSPER.SIN.SUM.LiftMethod", "0")     # Natural flow
    px.s("PROSPER.SIN.SUM.Completion", "0")     # Cased hole
    px.s("PROSPER.SIN.SUM.GravelPack", "0")
    px.s("PROSPER.SIN.SUM.Predict", "1")        # Pressure & Temperature
    px.s("PROSPER.SIN.SUM.TemModel", "1")       # Rough approximation
    print("    System Summary: Oil, Natural Flow, Cased")

    # --- PVT Oil ---
    api = rp.get("api", rp.get("oil_gravity", 35))
    gor = rp.get("gor", 500)
    sg = rp.get("gas_gravity", 0.75)
    wc = rp.get("water_cut", 0)

    px.s("PROSPER.PVT.Input.Api", api)
    px.s("PROSPER.PVT.Input.GOR", gor)
    px.s("PROSPER.PVT.Input.Sg", sg)
    px.s("PROSPER.PVT.Input.SepPres", sp["sep_pres_psi"])
    px.s("PROSPER.PVT.Input.SepTemp", sp.get("wht_f", 120))
    px.s("PROSPER.PVT.Input.Salinity", rp.get("salinity", 100000))
    px.s("PROSPER.PVT.Input.H2S", rp.get("h2s_pct", 0))
    px.s("PROSPER.PVT.Input.CO2", rp.get("co2_pct", 0))
    px.s("PROSPER.PVT.Input.N2", rp.get("n2_pct", 0))
    print(f"    PVT: API={api}, GOR={gor} scf/stb, Sg={sg}")

    # --- Deviation + Equipment ---
    _configure_prosper_equipment(px, wp, sp, rp)

    # --- IPR: Vogel (oil below Pb) ---
    # IprModel: 0=PI, 1=Vogel, 2=Composite(PI+Vogel), 5=Darcy, 4=C&n
    # For oil shale: Vogel is standard
    px.s("PROSPER.SIN.IPR.Single.IprModel", "1")  # Vogel
    px.s("PROSPER.SIN.IPR.Single.Pres", rp["pi_psi"])
    px.s("PROSPER.SIN.IPR.Single.Temp", rp["ti_f"])
    px.s("PROSPER.SIN.IPR.Single.WC", wc)

    # Calculate AOF from IP
    ip_bopd = wp.get("ip_bopd", wp.get("ip_mscfd", 1000))
    # Vogel: q = AOF * [1 - 0.2*(Pwf/Pr) - 0.8*(Pwf/Pr)^2]
    # At Pwf ~ 0.7*Pr: q/AOF ~ 0.468, so AOF ~ IP/0.468
    aof = ip_bopd / 0.468
    px.s("PROSPER.SIN.IPR.Single.AOF", f"{aof:.0f}")
    print(f"    IPR: Vogel, AOF={aof:.0f} STB/d (IP={ip_bopd} STB/d)")

    # --- VLP Correlation: PE2 for oil multiphase ---
    px.s("PROSPER.ANL.VLP.TubingLabel", "PetroleumExperts2")
    print("    VLP Correlation: Petroleum Experts 2 (oil multiphase)")


def _configure_prosper_gas(px: PetexCOM, rp: dict, wp: dict, sp: dict):
    """
    Configura PROSPER para pozo de gas.

    PROSPER System Summary:
    - Fluid = 1 (Dry/Wet Gas)

    PVT: Gas gravity, CGR, condensate gravity
    IPR: C & n (backpressure equation for gas)
    VLP: Petroleum Experts 5 (gas/condensate)
    """
    print("  Configurando PROSPER para GAS...")

    # --- System Summary ---
    px.s("PROSPER.SIN.SUM.WellType", "0")       # Producer
    px.s("PROSPER.SIN.SUM.Fluid", "1")          # Gas
    px.s("PROSPER.SIN.SUM.FlowType", "0")       # Tubing
    px.s("PROSPER.SIN.SUM.InflowType", "0")     # Single branch
    px.s("PROSPER.SIN.SUM.LiftMethod", "0")     # Natural flow
    px.s("PROSPER.SIN.SUM.Completion", "0")     # Cased hole
    px.s("PROSPER.SIN.SUM.GravelPack", "0")
    px.s("PROSPER.SIN.SUM.Predict", "1")        # P&T
    px.s("PROSPER.SIN.SUM.TemModel", "1")       # Rough approx
    print("    System Summary: Gas, Natural Flow, Cased")

    # --- PVT Gas ---
    px.s("PROSPER.PVT.Input.GrvGas", rp["gas_gravity"])
    px.s("PROSPER.PVT.Input.CGR", rp.get("cgr_bbl_mmscf", 5))
    px.s("PROSPER.PVT.Input.CondGrav", rp.get("cond_gravity", 55))
    px.s("PROSPER.PVT.Input.SepPres", sp["sep_pres_psi"])
    px.s("PROSPER.PVT.Input.Wgr", "0")
    px.s("PROSPER.PVT.Input.Salinity", rp.get("salinity", 100000))
    px.s("PROSPER.PVT.Input.H2S", rp.get("h2s_pct", 0))
    px.s("PROSPER.PVT.Input.CO2", rp.get("co2_pct", 0))
    px.s("PROSPER.PVT.Input.N2", rp.get("n2_pct", 0))
    print(f"    PVT: Sg={rp['gas_gravity']}, CGR={rp.get('cgr_bbl_mmscf', 5)}")

    # --- Deviation + Equipment ---
    _configure_prosper_equipment(px, wp, sp, rp)

    # --- IPR: C&n (gas backpressure) ---
    px.s("PROSPER.SIN.IPR.Single.IprModel", "4")  # C and n
    px.s("PROSPER.SIN.IPR.Single.Pres", rp["pi_psi"])
    px.s("PROSPER.SIN.IPR.Single.Temp", rp["ti_f"])
    px.s("PROSPER.SIN.IPR.Single.WGR", "0")

    # Calibrate C from IP
    pr2 = float(rp["pi_psi"]) ** 2
    pwf_test = min(5000, float(rp["pi_psi"]) * 0.7)
    dp2 = (pr2 - pwf_test**2) / 1e6
    ip_scfd = float(wp.get("ip_mscfd", 5000)) * 1000
    c_val = ip_scfd / dp2 if dp2 > 0 else 1.0
    px.s("PROSPER.SIN.IPR.Single.Cn.C", f"{c_val:.4f}")
    px.s("PROSPER.SIN.IPR.Single.Cn.n", "1.0")
    print(f"    IPR: C&n, C={c_val:.2f}, IP={wp.get('ip_mscfd', 5000)} Mscf/d")

    # --- VLP Correlation: PE5 for gas ---
    px.s("PROSPER.ANL.VLP.TubingLabel", "PetroleumExperts5")
    print("    VLP Correlation: Petroleum Experts 5 (gas)")


def _configure_prosper_equipment(px: PetexCOM, wp: dict, sp: dict, rp: dict):
    """Configura deviation survey, downhole equipment y geothermal (comun oil/gas)."""
    tvd = wp["tvd_ft"]
    lateral = wp.get("lateral_ft", 0)

    if lateral > 0:
        # Horizontal well
        kop = int(tvd * 0.75)
        heel = int(tvd + 500)
        toe = int(heel + lateral)
        px.s("PROSPER.SIN.EQP.DEVN.DATA.COUNT", "4")
        px.s("PROSPER.SIN.EQP.Devn.Data[0].Md", "0")
        px.s("PROSPER.SIN.EQP.Devn.Data[0].Tvd", "0")
        px.s("PROSPER.SIN.EQP.Devn.Data[1].Md", str(kop))
        px.s("PROSPER.SIN.EQP.Devn.Data[1].Tvd", str(kop))
        px.s("PROSPER.SIN.EQP.Devn.Data[2].Md", str(heel))
        px.s("PROSPER.SIN.EQP.Devn.Data[2].Tvd", str(tvd))
        px.s("PROSPER.SIN.EQP.Devn.Data[3].Md", str(toe))
        px.s("PROSPER.SIN.EQP.Devn.Data[3].Tvd", str(tvd))
        eq_depth = toe
    else:
        # Vertical well
        px.s("PROSPER.SIN.EQP.DEVN.DATA.COUNT", "2")
        px.s("PROSPER.SIN.EQP.Devn.Data[0].Md", "0")
        px.s("PROSPER.SIN.EQP.Devn.Data[0].Tvd", "0")
        px.s("PROSPER.SIN.EQP.Devn.Data[1].Md", str(tvd))
        px.s("PROSPER.SIN.EQP.Devn.Data[1].Tvd", str(tvd))
        eq_depth = tvd
        heel = tvd

    # Downhole Equipment
    px.s("PROSPER.SIN.EQP.DOWN.DATA.COUNT", "3")
    px.s("PROSPER.SIN.EQP.DOWN.DATA[0].TYPE", "4")  # Xmas tree
    px.s("PROSPER.SIN.EQP.DOWN.DATA[0].DEPTH", "0")
    px.s("PROSPER.SIN.EQP.DOWN.DATA[1].TYPE", "0")  # Tubing
    px.s("PROSPER.SIN.EQP.DOWN.DATA[1].DEPTH", str(heel))
    px.s("PROSPER.SIN.EQP.DOWN.DATA[1].TID", wp.get("tubing_id_in", "3.958"))
    px.s("PROSPER.SIN.EQP.DOWN.DATA[1].TIR", "0.0006")
    px.s("PROSPER.SIN.EQP.DOWN.DATA[2].TYPE", "3")  # Liner/casing
    px.s("PROSPER.SIN.EQP.DOWN.DATA[2].DEPTH", str(eq_depth))
    px.s("PROSPER.SIN.EQP.DOWN.DATA[2].TID", wp.get("liner_id_in", "4.67"))
    px.s("PROSPER.SIN.EQP.DOWN.DATA[2].TIR", "0.0006")
    print(f"    Equipment: Tubing to {heel}ft, Liner to {eq_depth}ft")

    # Geothermal gradient
    px.s("PROSPER.SIN.EQP.Geo.Data[0].Depth", "0")
    px.s("PROSPER.SIN.EQP.Geo.Data[0].Temp", sp.get("ambient_t_f", 59))
    px.s("PROSPER.SIN.EQP.Geo.Data[1].Depth", str(eq_depth))
    px.s("PROSPER.SIN.EQP.Geo.Data[1].Temp", rp["ti_f"])
    px.s("PROSPER.SIN.EQP.Geo.Uval", sp.get("u_value", 3.0))
    print(f"    Geothermal: {sp.get('ambient_t_f', 59)}F surface -> {rp['ti_f']}F reservoir")


# ======================================================================
# HELPER FUNCTIONS — VLP Generation
# ======================================================================

def _generate_vlp_curves(px: PetexCOM, is_oil: bool, vlp_path: str):
    """Genera VLP curves con sensitividades apropiadas al fluido."""
    if is_oil:
        # Oil: sensitividades en WHP y Water Cut
        whp_values = [60, 100, 200, 500, 1000, 1500, 2000, 3000, 4000, 5000]
        px.s("PROSPER.ANL.VLP.Sens[0].Var", "0")  # Top node pressure
        px.s("PROSPER.ANL.VLP.Sens[0].Vals", str(len(whp_values)))
        for i, p in enumerate(whp_values):
            px.s(f"PROSPER.ANL.VLP.Sens[0].Val[{i}]", str(p))

        wc_values = [0, 10, 20, 40, 60, 80]
        px.s("PROSPER.ANL.VLP.Sens[1].Var", "2")  # Water cut
        px.s("PROSPER.ANL.VLP.Sens[1].Vals", str(len(wc_values)))
        for i, w in enumerate(wc_values):
            px.s(f"PROSPER.ANL.VLP.Sens[1].Val[{i}]", str(w))
        print(f"    VLP sensitivities: {len(whp_values)} WHPs x {len(wc_values)} WCs")
    else:
        # Gas: sensitividades en WHP y WGR
        whp_values = [100, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000]
        px.s("PROSPER.ANL.VLP.Sens[0].Var", "0")  # Top node pressure
        px.s("PROSPER.ANL.VLP.Sens[0].Vals", str(len(whp_values)))
        for i, p in enumerate(whp_values):
            px.s(f"PROSPER.ANL.VLP.Sens[0].Val[{i}]", str(p))

        wgr_values = [0, 1, 5, 10, 20, 50]
        px.s("PROSPER.ANL.VLP.Sens[1].Var", "1")  # WGR
        px.s("PROSPER.ANL.VLP.Sens[1].Vals", str(len(wgr_values)))
        for i, w in enumerate(wgr_values):
            px.s(f"PROSPER.ANL.VLP.Sens[1].Val[{i}]", str(w))
        print(f"    VLP sensitivities: {len(whp_values)} WHPs x {len(wgr_values)} WGRs")

    # Calcular y exportar
    px.cmd("PROSPER.ANL.VLP.CALC")
    time.sleep(25)
    px.cmd(f'PROSPER.ANL.VLP.EXPORT(0,"{vlp_path}")')
    time.sleep(3)


# ======================================================================
# HELPER FUNCTIONS — GAP Configuration
# ======================================================================

def _configure_gap(px: PetexCOM, well_name: str, is_oil: bool,
                   rp: dict, wp: dict, sp: dict, results: dict):
    """Configura GAP con los parametros correctos segun fluido."""
    # Sistema
    px.s("GAP.MOD.TITLE", f"{well_name} - {'Oil' if is_oil else 'Gas'} Network")
    px.s("GAP.MOD.SYSOPT.SystemType", "0")       # Production
    px.s("GAP.MOD.SYSOPT.OptMethod", "0" if is_oil else "1")  # Max Oil vs Max Gas
    px.s("GAP.MOD.SYSOPT.SolverMode", "0")       # Solve only
    px.s("GAP.MOD.SYSOPT.PVTModel", "0")         # Black oil
    print(f"    System: {'Max Oil' if is_oil else 'Max Gas'}")

    # Separador
    px.s("GAP.MOD.SEP[0].Label", "Separator")
    px.s("GAP.MOD.SEP[0].Pres", sp["sep_pres_psi"])
    px.s("GAP.MOD.SEP[0].Temp", sp.get("wht_f", 120))
    print(f"    Separator: {sp['sep_pres_psi']} psi")

    # Manifold
    px.s("GAP.MOD.JOINT[0].Label", "Manifold")

    # Pozo
    px.s("GAP.MOD.WELL[0].Label", well_name)
    px.s("GAP.MOD.WELL[0].WellType", "1" if is_oil else "0")  # Oil vs Gas producer
    px.s("GAP.MOD.WELL[0].WellModel", "0")       # VLP/IPR intersection
    px.s("GAP.MOD.WELL[0].Status", "1")          # ON

    # Link PROSPER
    if results["status"]["prosper"] == "ok" and "prosper" in results["files"]:
        px.s("GAP.MOD.WELL[0].ProsperFile", results["files"]["prosper"])

    # IPR inline
    if is_oil:
        # Vogel IPR
        px.s("GAP.MOD.WELL[0].IPR.Type", "1")    # Vogel
        px.s("GAP.MOD.WELL[0].IPR.Pres", rp["pi_psi"])
        px.s("GAP.MOD.WELL[0].IPR.Temp", rp["ti_f"])
        wc = rp.get("water_cut", 0)
        px.s("GAP.MOD.WELL[0].IPR.WC", wc)
        ip_bopd = wp.get("ip_bopd", wp.get("ip_mscfd", 1000))
        aof = ip_bopd / 0.468
        px.s("GAP.MOD.WELL[0].IPR.AOF", f"{aof:.0f}")
        print(f"    Well IPR: Vogel, AOF={aof:.0f}, WC={wc}%")
    else:
        # C&n IPR
        px.s("GAP.MOD.WELL[0].IPR.Type", "4")    # C and n
        px.s("GAP.MOD.WELL[0].IPR.Pres", rp["pi_psi"])
        px.s("GAP.MOD.WELL[0].IPR.Temp", rp["ti_f"])
        px.s("GAP.MOD.WELL[0].IPR.WGR", "0")
        pr2 = float(rp["pi_psi"]) ** 2
        pwf_test = min(5000, float(rp["pi_psi"]) * 0.7)
        dp2 = (pr2 - pwf_test**2) / 1e6
        ip_scfd = float(wp.get("ip_mscfd", 5000)) * 1000
        c_val = ip_scfd / dp2 if dp2 > 0 else 1.0
        px.s("GAP.MOD.WELL[0].IPR.Cn.C", f"{c_val:.4f}")
        px.s("GAP.MOD.WELL[0].IPR.Cn.n", "1.0")
        print(f"    Well IPR: C&n, C={c_val:.2f}")

    # VLP link
    if "vlp_tpd" in results["files"] and _verify_file(results["files"]["vlp_tpd"]):
        px.s("GAP.MOD.WELL[0].VLPFile", results["files"]["vlp_tpd"])
        px.s("GAP.MOD.WELL[0].VLPType", "1")     # From file
        print(f"    VLP: from .tpd file")
    else:
        px.s("GAP.MOD.WELL[0].VLPType", "0")     # Calculated
        corr = "10" if is_oil else "14"           # PE2 vs PE5
        px.s("GAP.MOD.WELL[0].VLP.Correlation", corr)
        px.s("GAP.MOD.WELL[0].VLP.TubingID", wp.get("tubing_id_in", "3.958"))
        px.s("GAP.MOD.WELL[0].VLP.Depth", str(wp["tvd_ft"]))
        print(f"    VLP: inline calculated ({'PE2' if is_oil else 'PE5'})")

    # Flowline
    px.s("GAP.MOD.PIPE[0].Label", "FL_well")
    px.s("GAP.MOD.PIPE[0].Source", well_name)
    px.s("GAP.MOD.PIPE[0].Dest", "Manifold")
    px.s("GAP.MOD.PIPE[0].Length", sp["flowline_length_ft"])
    px.s("GAP.MOD.PIPE[0].ID", sp["flowline_id_in"])
    px.s("GAP.MOD.PIPE[0].Roughness", "0.0018")
    px.s("GAP.MOD.PIPE[0].Correlation", "10")    # PE2 for multiphase
    px.s("GAP.MOD.PIPE[0].AmbTemp", sp.get("ambient_t_f", 59))
    px.s("GAP.MOD.PIPE[0].Uvalue", sp.get("u_value", 3.0))

    # Troncal
    px.s("GAP.MOD.PIPE[1].Label", "Trunk")
    px.s("GAP.MOD.PIPE[1].Source", "Manifold")
    px.s("GAP.MOD.PIPE[1].Dest", "Separator")
    px.s("GAP.MOD.PIPE[1].Length", sp["trunk_length_ft"])
    px.s("GAP.MOD.PIPE[1].ID", sp["trunk_id_in"])
    px.s("GAP.MOD.PIPE[1].Roughness", "0.0018")
    px.s("GAP.MOD.PIPE[1].Correlation", "10")
    px.s("GAP.MOD.PIPE[1].AmbTemp", sp.get("ambient_t_f", 59))
    px.s("GAP.MOD.PIPE[1].Uvalue", sp.get("u_value", 3.0))
    print(f"    Network: Well -> FL({sp['flowline_length_ft']}ft) -> Manifold -> Trunk({sp['trunk_length_ft']}ft) -> Sep")

    # Tank MBAL
    if results["status"]["mbal"] == "ok" and "mbal" in results["files"]:
        px.s("GAP.MOD.TANK[0].Label", "Reservoir")
        px.s("GAP.MOD.TANK[0].Model", "0")       # Material balance
        px.s("GAP.MOD.TANK[0].MbalFile", results["files"]["mbal"])
        px.s("GAP.MOD.TANK[0].Well[0]", well_name)
        print("    Tank: MBAL linked")
