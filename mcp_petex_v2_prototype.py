"""
MCP PETEX v2 - Prototype (Actualizado)
=======================================
MCP server para PROSPER/MBAL/GAP via OpenServer Python.
Incluye todas las correcciones de la sesion de discovery.

Requisitos: pip install openserver
Opcional:   pip install chromadb sentence-transformers (para RAG)

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
Fecha: 2026-08-27
"""

import os
import time
import subprocess
import logging
from typing import Optional, Tuple, Dict, Any

log = logging.getLogger("mcp_petex")


# ================================================================
# 1. CORRECTIONS CACHE - Variables verificadas contra IPM 13.5
# ================================================================

KNOWN_CORRECTIONS = {
    # PVT
    "PROSPER.PVT.Input.Salinity": None,

    # Geothermal (3 de 3 incorrectas en MCP original)
    "PROSPER.SIN.EQP.Geo.Data[{i}].TVD": "PROSPER.SIN.EQP.GEO.DATA[{i}].MD",
    "PROSPER.SIN.EQP.Geo.Data[{i}].Temp": "PROSPER.SIN.EQP.GEO.DATA[{i}].TMP",
    "PROSPER.SIN.EQP.Geo.Data[{i}].Temperature": "PROSPER.SIN.EQP.GEO.DATA[{i}].TMP",
    "PROSPER.SIN.EQP.Geo.Uval": "PROSPER.SIN.EQP.GEO.HTC",
    "PROSPER.SIN.EQP.Geo.Uvalue": "PROSPER.SIN.EQP.GEO.HTC",
    "PROSPER.SIN.EQP.Geo.HTC": "PROSPER.SIN.EQP.GEO.HTC",

    # IPR
    "PROSPER.SIN.IPR.Single.HzLength": "PROSPER.SIN.IPR.Single.WellLen",
    "PROSPER.SIN.IPR.Single.HzPermRatio": None,
    "PROSPER.SIN.IPR.Single.Temp": None,

    # System/VLP
    "PROSPER.ANL.SYS.Temp": None,
    "PROSPER.ANL.SYS.NodePosition": None,
    "PROSPER.ANL.SYS.WHT": None,
}

# Variables read-only (no intentar DoSet)
READ_ONLY_VARS = {
    "PROSPER.SIN.EQP.DEVN.DATA.COUNT",
    "PROSPER.SIN.EQP.DOWN.DATA.COUNT",
    "PROSPER.SIN.EQP.SURF.DATA.COUNT",
    "PROSPER.SIN.EQP.GEO.DATA.COUNT",
    "PROSPER.SIN.EQP.TEMP.DATA.COUNT",
}


# ================================================================
# 2. SMART OPENSERVER EXECUTOR
# ================================================================

class SmartOpenServer:
    """OpenServer wrapper con retry inteligente y correcciones."""

    def __init__(self, rag=None):
        self.rag = rag
        self.error_log = []
        self.corrections = dict(KNOWN_CORRECTIONS)
        self._os = None

    def connect(self):
        from openserver import OpenServer
        self._os = OpenServer()
        return self._os

    @property
    def os(self):
        if self._os is None:
            self.connect()
        return self._os

    def _apply_correction(self, variable: str) -> Optional[str]:
        """Buscar correccion conocida. None = variable no existe."""
        # Correccion exacta
        if variable in self.corrections:
            return self.corrections[variable]
        # Correccion con pattern {i}
        import re
        for pattern, replacement in self.corrections.items():
            if "{i}" in pattern:
                regex = pattern.replace("[{i}]", r"\[\d+\]")
                if re.match(regex, variable):
                    if replacement is None:
                        return None
                    idx = re.search(r"\[(\d+)\]", variable).group(0)
                    return replacement.replace("[{i}]", idx)
        return variable  # Sin correccion

    def do_set(self, variable: str, value: str) -> Tuple[bool, str]:
        """DoSet con correccion automatica."""
        if variable in READ_ONLY_VARS:
            return False, f"{variable} es READ-ONLY. Usar .ADD para agregar filas."

        corrected = self._apply_correction(variable)
        if corrected is None:
            log.warning(f"Variable {variable} no existe, ignorando")
            return False, f"Variable {variable} no existe en PROSPER"
        variable = corrected

        try:
            self.os.DoSet(variable, str(value))
            return True, variable
        except ValueError as e:
            error = str(e)
            # Intentar RAG si disponible
            if "Variable name was not found" in error and self.rag:
                suggestion = self.rag.find_variable(variable)
                if suggestion:
                    try:
                        self.os.DoSet(suggestion, str(value))
                        self.corrections[variable] = suggestion
                        log.info(f"RAG corrigio: {variable} -> {suggestion}")
                        return True, f"Corregido via RAG: {suggestion}"
                    except:
                        pass
            self.error_log.append({"action": "SET", "var": variable, "val": value, "err": error})
            return False, error

    def do_get(self, variable: str) -> Any:
        """DoGet con correccion."""
        corrected = self._apply_correction(variable)
        if corrected is None:
            return None
        return self.os.DoGet(corrected)

    def do_cmd(self, command: str) -> Tuple[bool, str]:
        """DoCmd. Nota: DoSlowCmd NO existe en Python, siempre usar DoCmd."""
        try:
            self.os.DoCmd(command)
            return True, "OK"
        except ValueError as e:
            error = str(e)
            self.error_log.append({"action": "CMD", "cmd": command, "err": error})
            return False, error

    def add_row(self, array_path: str) -> bool:
        """Agregar fila a array variable (DOWN.DATA, SURF.DATA, etc)."""
        try:
            self.os.DoSet(f"{array_path}.ADD", "")
            return True
        except:
            return False

    def kill_petex(self):
        """Matar todos los procesos PETEX."""
        for app in ["prosper", "mbal", "gap"]:
            subprocess.run(["taskkill", "/F", "/IM", f"{app}.exe"],
                           capture_output=True, timeout=10)
        time.sleep(4)

    def check_license(self, app: str) -> bool:
        """Verificar si una app tiene licencia disponible SIN dejarla abierta."""
        self.kill_petex()
        try:
            self.os.DoCmd(f'{app}.START("")')
            self.os.DoCmd(f"{app}.SHUTDOWN()")
            return True
        except ValueError as e:
            if "license" in str(e).lower():
                return False
            return False

    def check_all_licenses(self) -> dict:
        """Diagnostico de las 3 licencias. Retorna {app: bool}."""
        status = {}
        for app in ["PROSPER", "MBAL", "GAP"]:
            status[app] = self.check_license(app)
            self.kill_petex()
        return status

    def safe_start(self, app: str, max_retries: int = 3, wait_sec: int = 10):
        """Start con reintentos si la licencia esta ocupada.
        Espera y reintenta por si se libera una licencia flotante."""
        self.kill_petex()
        for attempt in range(max_retries):
            ok, msg = self.do_cmd(f'{app}.START("")')
            if ok:
                return True, msg
            if "license" in msg.lower():
                log.warning(f"{app} sin licencia (intento {attempt+1}/{max_retries}), esperando {wait_sec}s...")
                time.sleep(wait_sec)
            else:
                return False, msg
        return False, f"{app}: sin licencia libre despues de {max_retries} intentos"


# ================================================================
# 3. PROSPER WORKFLOWS
# ================================================================

def prosper_set_pvt(sos: SmartOpenServer, pvt: dict):
    """Configurar PVT. Keys: api, gor, gas_gravity, water_gravity, tres, h2s, co2, n2, pb_corr"""
    mapping = {
        "api": "PROSPER.PVT.Input.Api",
        "gor": "PROSPER.PVT.Input.SolGOR",
        "gas_gravity": "PROSPER.PVT.Input.GrvGas",
        "water_gravity": "PROSPER.PVT.Input.Wgr",
        "tres": "PROSPER.PVT.Input.Tres",
        "h2s": "PROSPER.PVT.Input.H2S",
        "co2": "PROSPER.PVT.Input.CO2",
        "n2": "PROSPER.PVT.Input.N2",
        "pb_corr": "PROSPER.PVT.Input.PbCorr",
    }
    for key, var in mapping.items():
        if key in pvt:
            sos.do_set(var, str(pvt[key]))


def prosper_set_deviation(sos: SmartOpenServer, points: list):
    """Configurar deviation survey. points = [(md, tvd), ...]
    Auto-extends, no necesita ADD."""
    for i, (md, tvd) in enumerate(points):
        sos.do_set(f"PROSPER.SIN.EQP.Devn.Data[{i}].Md", str(md))
        sos.do_set(f"PROSPER.SIN.EQP.Devn.Data[{i}].Tvd", str(tvd))


def prosper_set_geothermal(sos: SmartOpenServer, points: list, htc: float = 5.0):
    """Configurar geothermal. points = [(md, tmp), ...]. Usa MD no TVD."""
    for i, (md, tmp) in enumerate(points):
        sos.do_set(f"PROSPER.SIN.EQP.GEO.DATA[{i}].MD", str(md))
        sos.do_set(f"PROSPER.SIN.EQP.GEO.DATA[{i}].TMP", str(tmp))
    sos.do_set("PROSPER.SIN.EQP.GEO.HTC", str(htc))


def prosper_set_downhole(sos: SmartOpenServer, equipment: list):
    """Configurar downhole equipment usando ADD.
    equipment = [
        {"type": 1, "label": "X-mas Tree", "depth": 0, "mult": 1},
        {"type": 0, "label": "Tubing", "depth": 9843,
         "tid": 4.052, "tir": 0.0006, "tod": 4.8, "tor": 0.0006,
         "cid": 6.4, "cir": 0.0006, "mult": 1},
        {"type": 2, "label": "Casing", "depth": 9900,
         "cid": 6.4, "cir": 0.0006, "mult": 1},
    ]
    """
    base = "PROSPER.SIN.EQP.DOWN.DATA"

    for i, eq in enumerate(equipment):
        if i > 0:
            sos.add_row(base)

        sos.do_set(f"{base}[{i}].TYPE", str(eq.get("type", 0)))
        if "label" in eq:
            sos.do_set(f"{base}[{i}].LABEL", eq["label"])
        if "depth" in eq:
            sos.do_set(f"{base}[{i}].DEPTH", str(eq["depth"]))

        # Tubing dimensions (obligatorias para TYPE=0)
        for field in ["TID", "TIR", "TOD", "TOR", "CID", "CIR", "COD", "COR"]:
            key = field.lower()
            if key in eq:
                sos.do_set(f"{base}[{i}].{field}", str(eq[key]))

        # MULT siempre obligatorio
        sos.do_set(f"{base}[{i}].MULT", str(eq.get("mult", 1)))


def prosper_set_surface(sos: SmartOpenServer, equipment: list, htc: float = 5.0, tmp: float = 77.0):
    """Configurar surface equipment.
    equipment = [
        {"label": "Flowline", "type": 1, "length": 100,
         "id": 4.052, "rough": 0.0006, "tvd": 0, "mult": 1, "htc": 5}
    ]
    """
    sos.do_set("PROSPER.SIN.EQP.SURF.HTC", str(htc))
    sos.do_set("PROSPER.SIN.EQP.SURF.TMP", str(tmp))

    base = "PROSPER.SIN.EQP.SURF.DATA"
    for i, eq in enumerate(equipment):
        if i > 0:
            sos.add_row(base)

        for field, key in [("LABEL", "label"), ("TYPE", "type"), ("LENGTH", "length"),
                           ("TVD", "tvd"), ("ID", "id"), ("ROUGH", "rough"),
                           ("MULT", "mult"), ("HTC", "htc")]:
            if key in eq:
                sos.do_set(f"{base}[{i}].{field}", str(eq[key]))


def prosper_set_ipr(sos: SmartOpenServer, ipr: dict):
    """Configurar IPR. Keys: model, pres, skin, thickness, well_len, drainage, wbr"""
    mapping = {
        "model": "PROSPER.SIN.IPR.Single.IprModel",
        "pres": "PROSPER.SIN.IPR.Single.Pres",
        "skin": "PROSPER.SIN.IPR.Single.Skin",
        "thickness": "PROSPER.SIN.IPR.Single.Thickness",
        "well_len": "PROSPER.SIN.IPR.Single.WellLen",
        "drainage": "PROSPER.SIN.IPR.Single.Drainage",
        "wbr": "PROSPER.SIN.IPR.Single.WBR",
    }
    for key, var in mapping.items():
        if key in ipr:
            sos.do_set(var, str(ipr[key]))


def prosper_run_nodal(sos: SmartOpenServer, whp: float,
                      correlation: str = "PetroleumExperts2",
                      wc: float = 0, gor: float = 0) -> dict:
    """Correr nodal analysis."""
    sos.do_set("PROSPER.ANL.SYS.TubingLabel", correlation)
    sos.do_set("PROSPER.ANL.SYS.Pres", str(whp))
    if wc > 0:
        sos.do_set("PROSPER.ANL.SYS.WC", str(wc))
    if gor > 0:
        sos.do_set("PROSPER.ANL.SYS.GOR", str(gor))

    ok, msg = sos.do_cmd("PROSPER.ANL.SYS.CALC")
    if not ok:
        return {"error": msg}

    return {
        "oil_rate": sos.do_get("PROSPER.OUT.SYS.Results[0].Sol.OilRate"),
        "pressure": sos.do_get("PROSPER.OUT.SYS.Results[0].Sol.Pres"),
    }


def prosper_generate_vlp(sos: SmartOpenServer, whp_values: list,
                         wc_values: list, gor_values: list, export_path: str):
    """Generar VLP curves y exportar a .tpd para GAP."""
    for i, v in enumerate(whp_values):
        sos.do_set(f"PROSPER.ANL.VLP.Sens[0].Val[{i}]", str(float(v)))
    for i, v in enumerate(wc_values):
        sos.do_set(f"PROSPER.ANL.VLP.Sens[1].Val[{i}]", str(float(v)))
    for i, v in enumerate(gor_values):
        sos.do_set(f"PROSPER.ANL.VLP.Sens[2].Val[{i}]", str(float(v)))

    sos.do_cmd("PROSPER.ANL.VLP.CALC")
    sos.do_cmd(f'PROSPER.ANL.VLP.EXPORT(0,"{export_path}")')


# ================================================================
# 4. MBAL WORKFLOWS
# ================================================================

def mbal_create(sos: SmartOpenServer, filepath: str, params: dict) -> str:
    """Crear modelo MBAL completo.
    params = {
        "type": "OIL",
        "pvt": {"OILGRAV": 35, "GASGRAV": 0.75, "SOLGOR": 800, "TRES": 248},
        "pressure": 5500,
        "ooip": 45,  # MMstb (opcional)
    }
    """
    sos.safe_start("MBAL")
    sos.do_cmd("MBAL.NEWMODEL()")

    # Tank type
    sos.do_set("MBAL.MB.TANK.TYPE", params.get("type", "OIL"))

    # PVT
    for key, val in params.get("pvt", {}).items():
        sos.do_set(f"MBAL.MB[0].PVT.INPUT.{key}", str(val))

    # Reservoir parameters
    if "pressure" in params:
        sos.do_set("MBAL.MB.TANK.PRESS", str(params["pressure"]))
    if "ooip" in params:
        sos.do_set("MBAL.MB[0].TANK[0].OOIP", str(params["ooip"]))
    if "ogip" in params:
        sos.do_set("MBAL.MB[0].TANK[0].OGIP", str(params["ogip"]))

    # Validar (equivalente al Done de GUI - funciona en MBAL!)
    sos.do_cmd("MBAL.MB.VALIDATE")

    # Guardar
    sos.do_cmd(f'MBAL.SaveFile("{filepath}")')
    sos.do_cmd("MBAL.SHUTDOWN()")
    return filepath


def mbal_run_prediction(sos: SmartOpenServer, filepath: str) -> list:
    """Correr prediccion MBAL step-by-step."""
    sos.safe_start("MBAL")
    sos.do_cmd(f'MBAL.OPENFILE("{filepath}")')

    sos.do_cmd("MBAL.MB.STARTPRED")
    results = []

    while True:
        sos.do_cmd("MBAL.MB.NEXTSTEPPRED")
        finished = sos.do_get("MBAL.MB.PREDFINISHED")
        current_time = sos.do_get("MBAL.MB.CURRENTPREDTIME")

        if str(finished).lower() in ("true", "1", "-1"):
            break

    sos.do_cmd("MBAL.MB.ENDPRED")

    # Leer resultados
    count = int(sos.do_get("MBAL.MB[0].TRES[{Prediction}][{Prediction}].COUNT") or 0)
    for i in range(count):
        t = sos.do_get(f"MBAL.MB[0].TRES[{{Prediction}}][{{Prediction}}][{i}].TIME")
        oil = sos.do_get(f"MBAL.MB[0].TRES[{{Prediction}}][{{Prediction}}][{i}].OILRATE")
        results.append({"time": t, "oil_rate": oil})

    sos.do_cmd(f'MBAL.SaveFile("{filepath}")')
    sos.do_cmd("MBAL.SHUTDOWN()")
    return results


# ================================================================
# 5. GAP WORKFLOWS
# ================================================================

def gap_create_network(sos: SmartOpenServer, filepath: str, config: dict) -> str:
    """Crear red GAP.
    config = {
        "well": {"name": "W1", "prosper_file": "path.Out", "type": "OilProducerNoLift"},
        "separator": {"name": "SEP1", "pressure": 200, "max_liq": 50000},
        "pipeline": {"name": "FL1", "length_ft": 9843, "diameter_in": 6},
        "tank": {"name": "T1", "mbal_file": "path.mbi"},  # opcional
    }
    """
    sos.safe_start("GAP")

    # Nuevo modelo (GAP usa DoGAPFunc pero en Python probamos DoCmd)
    sos.do_cmd("GAP.NEWFILE()")

    # Config sistema
    sos.do_set("GAP.MOD[0].SYSTYPE", "0")      # Production
    sos.do_set("GAP.MOD[0].OPTMETHOD", "0")    # Max Oil
    sos.do_set("GAP.MOD[0].PVTMODEL", "0")     # Black Oil

    well = config["well"]
    sep = config["separator"]
    pipe = config["pipeline"]

    # Crear elementos via NEWITEM (VERIFICADO: funciona via DoCmd)
    wn = well["name"]
    sn = sep["name"]
    pn = pipe["name"]

    sos.do_cmd(f'GAP.NEWITEM("WELL", "{wn}", "RIGHT", NULL, MOD[0])')
    sos.do_cmd(f'GAP.NEWITEM("SEP", "{sn}", "RIGHT", NULL, MOD[0])')
    sos.do_cmd(f'GAP.NEWITEM("PIPE", "{pn}", "RIGHT", MOD[0].EQUIP[{{{wn}}}], MOD[0])')

    # Conectar: Well -> Pipe -> Separator (VERIFICADO)
    sos.do_cmd(f'GAP.LINKITEMS(MOD[0].EQUIP[{{{wn}}}], MOD[0].PIPE[{{{pn}}}], "")')
    sos.do_cmd(f'GAP.LINKITEMS(MOD[0].PIPE[{{{pn}}}], MOD[0].EQUIP[{{{sn}}}], "")')

    # Well config (VERIFICADO: WellType numero "3", File no PROSPERFile)
    sos.do_set(f"GAP.MOD[0].WELL[{{{wn}}}].WellType", "3")
    sos.do_set(f"GAP.MOD[0].WELL[{{{wn}}}].File", well["prosper_file"])

    # Separator (VERIFICADO: SolverPres[0] no MAXPRES)
    sos.do_set(f"GAP.MOD[0].SEP[{{{sn}}}].SolverPres[0]", str(sep.get("pressure", 200)))

    # Pipeline (VERIFICADO: tabla Desc[i], no Length/Diameter directos)
    sos.do_set(f"GAP.MOD[0].PIPE[{{{pn}}}].Desc[0].Length", str(pipe.get("length_ft", 0)))
    sos.do_set(f"GAP.MOD[0].PIPE[{{{pn}}}].Desc[0].ID", str(pipe.get("diameter_in", 6)))
    sos.do_set(f"GAP.MOD[0].PIPE[{{{pn}}}].Desc[0].Roughness", str(pipe.get("roughness", 0.0006)))
    sos.do_set(f"GAP.MOD[0].PIPE[{{{pn}}}].Desc[0].TVD", str(pipe.get("elevation", 0)))

    # Tank (MBAL) - solo si hay licencia y archivo
    if "tank" in config:
        tank = config["tank"]
        tn = tank["name"]
        sos.do_cmd(f'GAP.NEWITEM("TANK", "{tn}", "RIGHT", NULL, MOD[0])')
        sos.do_set(f"GAP.MOD[0].TANK[{{{tn}}}].MBALFile", tank["mbal_file"])
        sos.do_cmd(f'GAP.LINKITEMS(MOD[0].TANK[{{{tn}}}], MOD[0].WELL[{{{wn}}}], "")')

    # Transferir IPR de PROSPER y VLP (necesario para SOLVE)
    sos.do_cmd(f'GAP.TRANSFERPROSPERIPR(MOD[0].WELL[{{{wn}}}],0,0)')
    if "vlp_file" in well:
        sos.do_cmd(f'GAP.VLPIMPORT(MOD[0].WELL[{{{wn}}}], "{well["vlp_file"]}")')

    # Validar red
    sos.do_cmd("GAP.VALIDATE(0)")

    sos.do_cmd(f'GAP.SAVEFILE("{filepath}")')
    return filepath


def gap_solve(sos: SmartOpenServer, sep_name: str = "SEP1") -> dict:
    """Resolver red y leer resultados."""
    sos.do_cmd("GAP.RESETSOLVERINPUTS()")
    ok, msg = sos.do_cmd("GAP.SOLVENETWORK(0, MOD[0], 0)")
    if not ok:
        return {"error": msg}

    return {
        "oil_rate": sos.do_get(f"GAP.MOD[0].SEP[{{{sep_name}}}].SolverResults[0].Qoil"),
        "gas_rate": sos.do_get(f"GAP.MOD[0].SEP[{{{sep_name}}}].SolverResults[0].Qgas"),
        "water_rate": sos.do_get(f"GAP.MOD[0].SEP[{{{sep_name}}}].SolverResults[0].Qwat"),
    }


# ================================================================
# 6. INTEGRATED WORKFLOW
# ================================================================

def run_integrated_model(base_dir: str, prosper_file: str, config: dict):
    """Workflow integrado: PROSPER existente -> MBAL -> GAP -> Solve.

    config = {
        "mbal": {
            "type": "OIL",
            "pvt": {"OILGRAV": 35, "GASGRAV": 0.75, "SOLGOR": 800, "TRES": 248},
            "pressure": 5500,
            "ooip": 45,
        },
        "gap": {
            "well_name": "W1",
            "separator": {"name": "SEP1", "pressure": 200},
            "pipeline": {"name": "FL1", "length_ft": 9843, "diameter_in": 6},
        }
    }
    """
    sos = SmartOpenServer()

    mbal_file = os.path.join(base_dir, "model_MBAL.mbi")
    gap_file = os.path.join(base_dir, "model_GAP.gap")

    print("=" * 50)
    print("PASO 1: Creando MBAL...")
    mbal_create(sos, mbal_file, config["mbal"])
    print(f"  MBAL: {mbal_file}")

    print("\nPASO 2: Creando GAP...")
    well_name = config["gap"]["well_name"]
    gap_create_network(sos, gap_file, {
        "well": {"name": well_name, "prosper_file": prosper_file},
        "separator": config["gap"]["separator"],
        "pipeline": config["gap"]["pipeline"],
        "tank": {"name": "TANK1", "mbal_file": mbal_file},
    })
    print(f"  GAP: {gap_file}")

    print("\nPASO 3: Resolviendo red...")
    results = gap_solve(sos, config["gap"]["separator"]["name"])
    print(f"  Oil:   {results.get('oil_rate')} STB/d")
    print(f"  Gas:   {results.get('gas_rate')} MSCF/d")
    print(f"  Water: {results.get('water_rate')} STB/d")

    sos.do_cmd(f'GAP.SAVEFILE("{gap_file}")')
    sos.do_cmd("GAP.SHUTDOWN()")

    print("\n" + "=" * 50)
    print("MODELO COMPLETO")
    print(f"  PROSPER: {prosper_file}")
    print(f"  MBAL:    {mbal_file}")
    print(f"  GAP:     {gap_file}")

    if sos.error_log:
        print(f"\n  Errores ({len(sos.error_log)}):")
        for err in sos.error_log:
            print(f"    {err}")

    return results


# ================================================================
# 7. MAIN
# ================================================================

if __name__ == "__main__":
    base = r"C:\Users\xgvb02\Desktop\Ds\MCP\test dario petex"
    prosper = os.path.join(base, "APO-135(h).Out")

    # Diagnostico de licencias primero
    print("Verificando licencias PETEX...")
    sos_check = SmartOpenServer()
    licenses = sos_check.check_all_licenses()
    for app, avail in licenses.items():
        print(f"  {app}: {'DISPONIBLE' if avail else 'OCUPADA'}")
    print()

    # Si MBAL no esta disponible, se puede seguir con PROSPER->GAP
    if not licenses.get("MBAL"):
        print("MBAL sin licencia - el modelo se armara sin tank (PROSPER->GAP)")
    print()

    run_integrated_model(base, prosper, {
        "mbal": {
            "type": "OIL",
            "pvt": {
                "OILGRAV": "55",
                "GASGRAV": "0.568",
                "SOLGOR": "0",
                "CO2": "0.44",
                "N2": "0.24",
                "TRES": "219",
            },
            "pressure": "7441",
        },
        "gap": {
            "well_name": "APO_135H",
            "separator": {"name": "SEP1", "pressure": 200, "max_liq": 50000},
            "pipeline": {"name": "FL1", "length_ft": 9843, "diameter_in": 6},
        },
    })
