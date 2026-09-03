"""
PETEX Orchestrator
==================
Workflow inteligente end-to-end. Recibe una intencion de alto nivel
(formacion, tipo de fluido, target) y:
  1. Consulta la KB de ingenieria -> elige correlaciones, PVT, rangos
  2. Arma el plan de pasos (PROSPER template -> MBAL -> GAP)
  3. En modo dry_run: devuelve el plan sin ejecutar
  4. En modo execute: corre contra PETEX via SmartExecutor (auto-correccion)
  5. Maneja licencias (fallback si MBAL no esta)

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import json
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")


def _load_kb(category: str, key: str) -> Optional[dict]:
    """Carga una entrada de la knowledge base de ingenieria."""
    path = os.path.join(KB_DIR, category)
    if not os.path.isdir(path):
        return None
    for fname in os.listdir(path):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(path, fname), encoding="utf-8") as f:
                    data = json.load(f)
                if key in data:
                    return data[key]
            except Exception:
                continue
    return None


def _pvt_defaults(pvt_kb: dict) -> dict:
    """Extrae valores tipicos de los rangos PVT de la KB."""
    if not pvt_kb or "typical_ranges" not in pvt_kb:
        return {}
    out = {}
    for param, rng in pvt_kb["typical_ranges"].items():
        if isinstance(rng, dict) and "typical" in rng:
            out[param] = rng["typical"]
    return out


class Orchestrator:
    def __init__(self, executor=None):
        self.executor = executor   # SmartExecutor (None en dry_run)

    def plan(self, formation: str, fluid: str = "oil",
             target_rate_m3d: float = None,
             lateral_length_m: float = None,
             separator_pressure_psi: float = 200,
             flowline_length_km: float = 3.0) -> dict:
        """Arma el plan de ingenieria consultando la KB. No ejecuta nada."""
        key = formation.lower().replace(" ", "_")

        # 1. Correlaciones recomendadas
        corr_kb = _load_kb("correlations", key) or _load_kb("correlations", "default") or {}
        # 2. PVT tipico
        pvt_kb = _load_kb("pvt", f"{key}_{fluid}") or {}
        pvt = _pvt_defaults(pvt_kb)

        # 3. Decisiones de ingenieria
        vlp = (corr_kb.get("vlp_tubing", {}) or {}).get("recommended", "PetroleumExperts2")
        ipr_block = (corr_kb.get("ipr_model", {}) or {}).get(fluid, {})
        ipr = ipr_block.get("recommended", "Vogel")

        plan = {
            "intencion": {
                "formation": formation,
                "fluid": fluid,
                "target_rate_m3d": target_rate_m3d,
                "lateral_length_m": lateral_length_m,
                "separator_pressure_psi": separator_pressure_psi,
                "flowline_length_km": flowline_length_km,
            },
            "decisiones_ingenieria": {
                "vlp_correlation": vlp,
                "ipr_model": ipr,
                "pvt": pvt or "sin datos en KB, usar defaults",
                "fuente_kb": bool(corr_kb) and bool(pvt_kb),
            },
            "pasos": self._build_steps(formation, fluid, vlp, ipr, pvt,
                                       lateral_length_m, separator_pressure_psi,
                                       flowline_length_km),
            "notas": [],
        }

        if not corr_kb:
            plan["notas"].append(f"Sin correlaciones en KB para '{formation}'. Usando defaults.")
        if not pvt:
            plan["notas"].append(f"Sin PVT en KB para '{key}_{fluid}'. Completar manualmente.")
        plan["notas"].append("PROSPER requiere template .Out pre-validado (blocker de tubing description).")

        return plan

    def _build_steps(self, formation, fluid, vlp, ipr, pvt,
                     lateral, sep_pres, fl_km) -> list:
        """Secuencia de pasos del modelo integrado."""
        fl_ft = round(fl_km * 3280.84)
        lateral_ft = round(lateral * 3.28084) if lateral else None
        return [
            {"paso": 1, "app": "KB", "accion": "Consultar correlaciones y PVT",
             "detalle": f"VLP={vlp}, IPR={ipr}"},
            {"paso": 2, "app": "PROSPER", "accion": "Cargar template .Out y ajustar parametros",
             "detalle": f"lateral={lateral_ft} ft, PVT de KB"},
            {"paso": 3, "app": "PROSPER", "accion": "Correr nodal analysis",
             "detalle": f"correlacion {vlp}"},
            {"paso": 4, "app": "MBAL", "accion": "Crear reservorio + VALIDATE",
             "detalle": "PVT consistente con PROSPER"},
            {"paso": 5, "app": "GAP", "accion": "Armar red well+flowline+separador",
             "detalle": f"flowline {fl_ft} ft, sep {sep_pres} psi"},
            {"paso": 6, "app": "GAP", "accion": "TRANSFERPROSPERIPR + VALIDATE + SOLVE",
             "detalle": "obtener caudales del separador"},
        ]

    def execute(self, plan: dict, prosper_template: str,
                out_dir: str) -> dict:
        """Ejecuta el plan contra PETEX. Requiere SmartExecutor."""
        if self.executor is None:
            return {"error": "Sin executor. Usar modo dry_run o pasar un SmartExecutor."}

        ex = self.executor
        results = {"ejecutado": [], "errores": [], "resultados": {}}

        # Chequear licencias primero
        # (el server real ya tiene check_licenses; aca asumimos que se llamo antes)

        try:
            # --- MBAL ---
            mbal_file = os.path.join(out_dir, "model_MBAL.mbi")
            pvt = plan["decisiones_ingenieria"]["pvt"]
            if isinstance(pvt, dict):
                ex.kill_petex()
                ok, _ = ex.do_cmd('MBAL.START("")')
                if ok:
                    ex.do_cmd("MBAL.NEWMODEL()")
                    ex.do_set("MBAL.MB.TANK.TYPE",
                              "OIL" if plan["intencion"]["fluid"] == "oil" else "GAS")
                    if "api" in pvt:
                        ex.do_set("MBAL.MB[0].PVT.INPUT.OILGRAV", pvt["api"])
                    if "gas_gravity" in pvt:
                        ex.do_set("MBAL.MB[0].PVT.INPUT.GASGRAV", pvt["gas_gravity"])
                    if "gor" in pvt:
                        ex.do_set("MBAL.MB[0].PVT.INPUT.SOLGOR", pvt["gor"])
                    if "reservoir_pres_psi" in pvt:
                        ex.do_set("MBAL.MB.TANK.PRESS", pvt["reservoir_pres_psi"])
                    ex.do_cmd("MBAL.MB.VALIDATE")
                    ex.do_cmd(f'MBAL.SaveFile("{mbal_file}")')
                    ex.do_cmd("MBAL.SHUTDOWN()")
                    results["ejecutado"].append("MBAL creado")
                    results["resultados"]["mbal_file"] = mbal_file
                else:
                    results["errores"].append("MBAL sin licencia - saltando (fallback)")

            # --- GAP ---
            gap_file = os.path.join(out_dir, "model_GAP.gap")
            fl_ft = plan["intencion"]["flowline_length_km"] * 3280.84
            sep_pres = plan["intencion"]["separator_pressure_psi"]
            ex.kill_petex()
            ok, _ = ex.do_cmd('GAP.START("")')
            if ok:
                ex.do_cmd("GAP.NEWFILE()")
                ex.do_set("GAP.MOD[0].SYSTYPE", "0")
                ex.do_set("GAP.MOD[0].OPTMETHOD", "0")
                ex.do_set("GAP.MOD[0].PVTMODEL", "0")
                ex.do_cmd('GAP.NEWITEM("WELL", "W1", "RIGHT", NULL, MOD[0])')
                ex.do_cmd('GAP.NEWITEM("SEP", "SEP1", "RIGHT", NULL, MOD[0])')
                ex.do_cmd('GAP.NEWITEM("PIPE", "FL1", "RIGHT", MOD[0].EQUIP[{W1}], MOD[0])')
                ex.do_cmd('GAP.LINKITEMS(MOD[0].EQUIP[{W1}], MOD[0].PIPE[{FL1}], "")')
                ex.do_cmd('GAP.LINKITEMS(MOD[0].PIPE[{FL1}], MOD[0].EQUIP[{SEP1}], "")')
                ex.do_set("GAP.MOD[0].WELL[{W1}].WellType", "3")
                ex.do_set("GAP.MOD[0].WELL[{W1}].File", prosper_template)
                ex.do_set("GAP.MOD[0].PIPE[{FL1}].Desc[0].Length", round(fl_ft))
                ex.do_set("GAP.MOD[0].PIPE[{FL1}].Desc[0].ID", 6)
                ex.do_set("GAP.MOD[0].PIPE[{FL1}].Desc[0].Roughness", 0.0006)
                ex.do_set("GAP.MOD[0].PIPE[{FL1}].Desc[0].TVD", 0)
                ex.do_set("GAP.MOD[0].SEP[{SEP1}].SolverPres[0]", sep_pres)
                if results["resultados"].get("mbal_file"):
                    ex.do_cmd('GAP.NEWITEM("TANK", "TANK1", "RIGHT", NULL, MOD[0])')
                    ex.do_set("GAP.MOD[0].TANK[{TANK1}].MBALFile", results["resultados"]["mbal_file"])
                    ex.do_cmd('GAP.LINKITEMS(MOD[0].TANK[{TANK1}], MOD[0].WELL[{W1}], "")')
                ex.do_cmd('GAP.TRANSFERPROSPERIPR(MOD[0].WELL[{W1}],0,0)')
                ex.do_cmd("GAP.VALIDATE(0)")
                ex.do_cmd(f'GAP.SAVEFILE("{gap_file}")')
                ex.do_cmd("GAP.RESETSOLVERINPUTS()")
                ok_solve, _ = ex.do_cmd("GAP.SOLVENETWORK(0, MOD[0], 0)")
                if ok_solve:
                    results["resultados"]["oil_rate"] = ex.do_get("GAP.MOD[0].SEP[{SEP1}].SolverResults[0].Qoil")
                    results["resultados"]["gas_rate"] = ex.do_get("GAP.MOD[0].SEP[{SEP1}].SolverResults[0].Qgas")
                ex.do_cmd(f'GAP.SAVEFILE("{gap_file}")')
                ex.do_cmd("GAP.SHUTDOWN()")
                results["ejecutado"].append("GAP creado y resuelto")
                results["resultados"]["gap_file"] = gap_file
            else:
                results["errores"].append("GAP sin licencia")

        except Exception as e:
            results["errores"].append(str(e))

        results["correcciones_aprendidas"] = ex.get_learned().get("aprendidas", 0)
        return results


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    orch = Orchestrator()  # dry-run (sin executor)
    plan = orch.plan(
        formation="Vaca Muerta",
        fluid="oil",
        target_rate_m3d=200,
        lateral_length_m=4000,
        separator_pressure_psi=200,
        flowline_length_km=3.0,
    )
    print(json.dumps(plan, indent=2, ensure_ascii=False))
