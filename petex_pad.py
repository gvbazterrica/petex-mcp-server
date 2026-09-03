"""
PETEX Multi-Well Pad Orchestrator
==================================
Orquesta un PAD completo: varios pozos que comparten una red de superficie
(un separador comun, un manifold). Extiende el orquestador de un pozo a N pozos.

Incluye el motor de planificacion (planner) que arma y EXPLICA la secuencia
antes de ejecutar, consultando:
  - KB de ingenieria (correlaciones/PVT por formacion)
  - Feedback loop (parametros que ya funcionaron)

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))


class PadPlanner:
    """Arma el plan de un pad multi-pozo, razonando decisiones."""

    def __init__(self, kb_backend=None, feedback=None):
        self.kb = kb_backend
        self.fb = feedback

    def plan_pad(self, pad_name: str, wells: list,
                 separator_pressure_psi: float = 200,
                 manifold: bool = True) -> dict:
        """Arma el plan de un pad.
        wells: lista de dicts, cada uno con {name, formation, fluid, template,
               lateral_length_m, flowline_length_km, params(opcional)}
        """
        plan = {
            "pad": pad_name,
            "num_pozos": len(wells),
            "topologia": "manifold comun -> separador" if manifold else "pozos independientes",
            "separator_pressure_psi": separator_pressure_psi,
            "pozos": [],
            "pasos_globales": [],
            "razonamiento": [],
        }

        # Razonar cada pozo
        for w in wells:
            well_plan = self._plan_well(w)
            plan["pozos"].append(well_plan)

        # Secuencia global de ejecucion
        plan["pasos_globales"] = [
            {"paso": 1, "accion": "Crear/clonar template PROSPER de cada pozo y ajustar params"},
            {"paso": 2, "accion": "Correr nodal de cada pozo para validar caudales"},
            {"paso": 3, "accion": "Generar VLP de cada pozo para GAP"},
            {"paso": 4, "accion": "Crear MBAL (reservorio(s)) segun corresponda"},
            {"paso": 5, "accion": f"Armar red GAP: {len(wells)} pozos -> manifold -> separador {separator_pressure_psi} psi"},
            {"paso": 6, "accion": "Conectar tanks MBAL, TRANSFERPROSPERIPR por pozo"},
            {"paso": 7, "accion": "VALIDATE + SOLVENETWORK -> caudal total del pad"},
        ]

        return plan

    def _plan_well(self, w: dict) -> dict:
        formation = w.get("formation", "desconocida")
        fluid = w.get("fluid", "oil")
        wp = {
            "name": w["name"],
            "formation": formation,
            "fluid": fluid,
        }

        # Decision de correlaciones desde la KB
        if self.kb:
            corr = self.kb.get("correlations", formation.lower().replace(" ", "_"))
            if corr:
                wp["vlp"] = corr.get("vlp_tubing", {}).get("recommended", "PetroleumExperts2")
                wp["ipr"] = corr.get("ipr_model", {}).get(fluid, {}).get("recommended", "Vogel")

        # Recomendacion desde casos exitosos previos (feedback)
        if self.fb:
            rec = self.fb.recommend_params(formation, fluid)
            if rec:
                wp["params_recomendados"] = rec["parametros_recomendados"]
                wp["caudal_esperado"] = rec["caudal_oil_observado"]
                wp["_nota"] = f"Basado en {rec['basado_en_casos']} casos exitosos previos"

        # Params explicitos del usuario tienen prioridad
        if "params" in w:
            wp["params_usuario"] = w["params"]

        return wp


def explain_plan(plan: dict) -> str:
    """Genera una explicacion en lenguaje natural del plan (para el usuario)."""
    lines = [
        f"PLAN DEL PAD '{plan['pad']}' ({plan['num_pozos']} pozos)",
        f"Topologia: {plan['topologia']}",
        f"Separador: {plan['separator_pressure_psi']} psi",
        "",
        "Pozos:",
    ]
    for wp in plan["pozos"]:
        line = f"  - {wp['name']} ({wp['formation']} / {wp['fluid']})"
        if "vlp" in wp:
            line += f": VLP={wp['vlp']}, IPR={wp['ipr']}"
        lines.append(line)
        if "_nota" in wp:
            lines.append(f"      {wp['_nota']}")
    lines.append("")
    lines.append("Secuencia:")
    for step in plan["pasos_globales"]:
        lines.append(f"  {step['paso']}. {step['accion']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    from petex_kb_backend import get_kb_backend
    from petex_feedback import FeedbackLoop

    planner = PadPlanner(kb_backend=get_kb_backend(), feedback=FeedbackLoop())
    plan = planner.plan_pad(
        pad_name="LomaCampana-Pad7",
        wells=[
            {"name": "LC7-H1", "formation": "vaca_muerta", "fluid": "oil", "lateral_length_m": 4000},
            {"name": "LC7-H2", "formation": "vaca_muerta", "fluid": "oil", "lateral_length_m": 3500},
            {"name": "LC7-H3", "formation": "vaca_muerta", "fluid": "gas_condensate", "lateral_length_m": 4200},
        ],
        separator_pressure_psi=200,
    )
    print(explain_plan(plan))
