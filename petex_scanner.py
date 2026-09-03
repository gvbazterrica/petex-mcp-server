"""
PETEX Model Scanner
===================
Escanea archivos .Out (PROSPER), .mbi (MBAL) y .gap (GAP) y extrae
TODA su estructura: tanques, separadores, wells, pipes, VLP, IPR,
equipment, PVT, etc. Devuelve un inventario estructurado (dict/JSON)
que sirve de contexto para reaccionar a pedidos en lenguaje natural.

Uso:
    from petex_scanner import scan_prosper, scan_gap, scan_mbal
    inv = scan_prosper(os_connection, "path.Out")

Requiere una conexion OpenServer activa (se pasa como argumento).
Nunca crea/destruye la conexion; solo lee.

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

FNA = "3.4e+35"   # valor que PROSPER devuelve para campos vacios


def _get(c, var):
    """DoGet seguro: devuelve None si falla o si es FNA."""
    try:
        v = c.DoGet(var)
        if v is None:
            return None
        s = str(v).strip()
        if s == "" or s.startswith("3.4e+35") or s == "1e+37":
            return None
        return v
    except Exception:
        return None


def _get_count(c, var):
    """Lee un COUNT y lo devuelve como int (0 si falla)."""
    v = _get(c, var)
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


# ================================================================
# PROSPER
# ================================================================

# Mapa de labels legibles para los codigos de System Summary
_SUM_MAPS = {
    "WellType": {"0": "Producer", "1": "Injector", "2": "Water Injector"},
    "Fluid": {"0": "Oil", "1": "Gas / Condensate"},
    "FlowType": {"0": "Tubing", "1": "Annular", "2": "Tubing+Annular"},
    "LiftMethod": {"0": "None", "1": "Gas Lift", "2": "ESP", "3": "HSP",
                   "4": "PCP", "7": "Jet Pump", "9": "Sucker Rod"},
    "Completion": {"0": "Cased Hole", "1": "Open Hole"},
    "PVTmodel": {"0": "Black Oil", "1": "EOS"},
}


def scan_prosper(c, filepath: str) -> dict:
    """Escanea un modelo PROSPER completo. c = conexion OpenServer con el archivo abierto."""
    inv = {"app": "PROSPER", "file": filepath, "components": {}}

    # --- System Summary ---
    summary = {}
    for var in ["WellType", "Fluid", "FlowType", "InflowType", "LiftMethod",
                "Completion", "PVTmodel", "PREDICT", "TEMPMODEL"]:
        raw = _get(c, f"PROSPER.SIN.SUM.{var}")
        if raw is not None:
            label = _SUM_MAPS.get(var, {}).get(str(raw).strip(), raw)
            summary[var] = label
    inv["components"]["system_summary"] = summary

    # --- PVT ---
    pvt = {}
    pvt_fields = {
        "Api": "API gravity", "GrvGas": "Gas gravity", "SolGOR": "Solution GOR",
        "Wgr": "Water gravity", "Tres": "Reservoir temp (F)",
        "H2S": "H2S %", "CO2": "CO2 %", "N2": "N2 %", "Pb": "Bubble point",
    }
    for var, desc in pvt_fields.items():
        val = _get(c, f"PROSPER.PVT.Input.{var}")
        if val is not None:
            pvt[desc] = val
    inv["components"]["pvt"] = pvt

    # --- IPR (todos los parametros relevantes) ---
    ipr = {}
    ipr["model"] = _get(c, "PROSPER.SIN.IPR.Single.IprModel")
    ipr_fields = {
        "Pres": "Reservoir pressure (psi)", "Skin": "Skin",
        "Thickness": "Thickness (ft)", "WellLen": "Horizontal length (ft)",
        "Drainage": "Drainage", "WBR": "Wellbore radius", "WC": "Water cut",
        "Perm": "Permeability", "PI": "Productivity index",
        "Qtest": "Test rate", "AOF": "AOF",
    }
    for var, desc in ipr_fields.items():
        val = _get(c, f"PROSPER.SIN.IPR.Single.{var}")
        if val is not None:
            ipr[desc] = val
    inv["components"]["ipr"] = ipr

    # --- Equipment: Deviation Survey ---
    devn = []
    n = _get_count(c, "PROSPER.SIN.EQP.DEVN.DATA.COUNT")
    for i in range(n):
        md = _get(c, f"PROSPER.SIN.EQP.Devn.Data[{i}].Md")
        tvd = _get(c, f"PROSPER.SIN.EQP.Devn.Data[{i}].Tvd")
        devn.append({"md": md, "tvd": tvd})
    inv["components"]["deviation_survey"] = {"points": n, "data": devn}

    # --- Equipment: Downhole ---
    downhole = []
    n = _get_count(c, "PROSPER.SIN.EQP.DOWN.DATA.COUNT")
    for i in range(n):
        item = {}
        for f in ["LABEL", "TYPE", "DEPTH", "TID", "TIR", "TOD", "TOR",
                  "CID", "CIR", "COD", "COR", "MULT"]:
            v = _get(c, f"PROSPER.SIN.EQP.DOWN.DATA[{i}].{f}")
            if v is not None:
                item[f.lower()] = v
        downhole.append(item)
    inv["components"]["downhole_equipment"] = {"items": n, "data": downhole}

    # --- Equipment: Surface ---
    surface = []
    n = _get_count(c, "PROSPER.SIN.EQP.SURF.DATA.COUNT")
    for i in range(n):
        item = {}
        for f in ["LABEL", "TYPE", "LENGTH", "TVD", "ID", "ROUGH", "MULT", "HTC"]:
            v = _get(c, f"PROSPER.SIN.EQP.SURF.DATA[{i}].{f}")
            if v is not None:
                item[f.lower()] = v
        surface.append(item)
    inv["components"]["surface_equipment"] = {"items": n, "data": surface}

    # --- Equipment: Geothermal ---
    geo = []
    n = _get_count(c, "PROSPER.SIN.EQP.GEO.DATA.COUNT")
    for i in range(n):
        md = _get(c, f"PROSPER.SIN.EQP.GEO.DATA[{i}].MD")
        tmp = _get(c, f"PROSPER.SIN.EQP.GEO.DATA[{i}].TMP")
        geo.append({"md": md, "temp": tmp})
    htc = _get(c, "PROSPER.SIN.EQP.GEO.HTC")
    inv["components"]["geothermal"] = {"points": n, "htc": htc, "data": geo}

    # --- VLP correlation ---
    inv["components"]["vlp"] = {
        "tubing_correlation": _get(c, "PROSPER.ANL.SYS.TubingLabel"),
    }

    return inv


# ================================================================
# GAP
# ================================================================

_GAP_NODE_TYPES = ["WELL", "PIPE", "SEP", "TANK", "JOINT", "PUMP", "COMP",
                   "SOURCE", "SINK", "VALVE", "INLSEP", "INLCHK"]


def scan_gap(c, filepath: str) -> dict:
    """Escanea una red GAP completa: todos los nodos y sus conexiones."""
    inv = {"app": "GAP", "file": filepath, "components": {}}

    # System config
    inv["components"]["system"] = {
        "type": _get(c, "GAP.MOD[0].SYSTYPE"),
        "optimization": _get(c, "GAP.MOD[0].OPTMETHOD"),
        "pvt_model": _get(c, "GAP.MOD[0].PVTMODEL"),
        "prediction": _get(c, "GAP.MOD[0].PREDICTION"),
    }

    # Recorrer cada tipo de nodo
    for node_type in _GAP_NODE_TYPES:
        n = _get_count(c, f"GAP.MOD[0].{node_type}.COUNT")
        if n == 0:
            continue
        nodes = []
        for i in range(n):
            node = {"index": i}
            label = _get(c, f"GAP.MOD[0].{node_type}[{i}].Label")
            if label:
                node["label"] = label
            # Campos comunes segun tipo
            if node_type == "WELL":
                node["well_type"] = _get(c, f"GAP.MOD[0].WELL[{i}].WellType")
                node["prosper_file"] = _get(c, f"GAP.MOD[0].WELL[{i}].File")
                node["masked"] = _get(c, f"GAP.MOD[0].WELL[{i}].MASKFLAG")
            elif node_type == "PIPE":
                node["length"] = _get(c, f"GAP.MOD[0].PIPE[{i}].Desc[0].Length")
                node["diameter"] = _get(c, f"GAP.MOD[0].PIPE[{i}].Desc[0].ID")
                node["from"] = _get(c, f"GAP.MOD[0].PIPE[{i}].ENDA.Label")
                node["to"] = _get(c, f"GAP.MOD[0].PIPE[{i}].ENDB.Label")
            elif node_type == "SEP":
                node["solver_pressure"] = _get(c, f"GAP.MOD[0].SEP[{i}].SolverPres[0]")
                node["max_liquid"] = _get(c, f"GAP.MOD[0].SEP[{i}].MAXQLIQ")
            elif node_type == "TANK":
                node["mbal_file"] = _get(c, f"GAP.MOD[0].TANK[{i}].MBALFile")
                node["pressure"] = _get(c, f"GAP.MOD[0].TANK[{i}].PRESS")
            nodes.append(node)
        inv["components"][node_type.lower() + "s"] = {"count": n, "data": nodes}

    return inv


# ================================================================
# MBAL
# ================================================================

def scan_mbal(c, filepath: str) -> dict:
    """Escanea un modelo MBAL: tanques, PVT, aquifer, production history."""
    inv = {"app": "MBAL", "file": filepath, "components": {}}

    # Tank(s)
    tanks = []
    # MBAL puede tener multiples tanks; intentamos leer hasta que falle
    for i in range(20):
        ttype = _get(c, f"MBAL.MB[0].TANK[{i}].TYPE")
        if ttype is None and i > 0:
            break
        tank = {"index": i, "type": ttype}
        for var, desc in [("OOIP", "OOIP (MMstb)"), ("OGIP", "OGIP (Bscf)"),
                          ("PRESS", "Pressure (psi)"), ("TEMP", "Temperature (F)"),
                          ("POR", "Porosity"), ("CONWAT", "Connate water"),
                          ("PERM", "Permeability")]:
            v = _get(c, f"MBAL.MB[0].TANK[{i}].{var}")
            if v is not None:
                tank[desc] = v
        # Aquifer
        aq_model = _get(c, f"MBAL.MB[0].TANK[{i}].AQUIFER.MODEL")
        if aq_model:
            tank["aquifer"] = {"model": aq_model}
        # Production history count
        ph = _get_count(c, f"MBAL.MB[0].TANK[{i}].PRODHIST.COUNT")
        if ph:
            tank["production_history_records"] = ph
        if len(tank) > 2:  # tiene datos ademas de index/type
            tanks.append(tank)
        if i > 0 and ttype is None:
            break
    inv["components"]["tanks"] = {"count": len(tanks), "data": tanks}

    # PVT
    pvt = {}
    for var, desc in [("OILGRAV", "Oil gravity (API)"), ("GASGRAV", "Gas gravity"),
                      ("SOLGOR", "Solution GOR"), ("WATSAL", "Water salinity"),
                      ("CO2", "CO2 %"), ("N2", "N2 %"), ("H2S", "H2S %"),
                      ("TRES", "Reservoir temp (F)")]:
        v = _get(c, f"MBAL.MB[0].PVT.INPUT.{var}")
        if v is not None:
            pvt[desc] = v
    inv["components"]["pvt"] = pvt

    return inv


# ================================================================
# Dispatcher
# ================================================================

def scan(c, filepath: str) -> dict:
    """Detecta el tipo de archivo por extension y escanea."""
    ext = filepath.lower().rsplit(".", 1)[-1]
    if ext == "out":
        return scan_prosper(c, filepath)
    if ext == "gap":
        return scan_gap(c, filepath)
    if ext in ("mbi", "mbl"):
        return scan_mbal(c, filepath)
    return {"error": f"Extension no reconocida: {ext}"}
