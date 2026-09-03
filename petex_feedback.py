"""
PETEX Feedback Loop
===================
Cierra el ciclo de aprendizaje del agente. Cuando un modelo se corre con exito,
se registra: parametros usados, correlaciones elegidas y resultados obtenidos.

Con el tiempo, el agente consulta estos casos historicos para:
  - Recomendar parametros que YA funcionaron para una formacion similar
  - Detectar rangos realistas de caudal por tipo de pozo
  - Evitar configuraciones que dieron error

Backend intercambiable (local JSON / DynamoDB via petex_kb_backend).

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import json
from datetime import datetime
from typing import Optional

BASE = os.path.dirname(os.path.abspath(__file__))
CASES_PATH = os.path.join(BASE, "successful_cases.json")


class FeedbackLoop:
    def __init__(self):
        self.cases = self._load()

    def _load(self):
        if os.path.exists(CASES_PATH):
            with open(CASES_PATH, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save(self):
        with open(CASES_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cases, f, indent=2, ensure_ascii=False)

    def record_success(self, formation: str, fluid: str, params: dict,
                       results: dict, model_files: dict = None) -> dict:
        """Registra un caso exitoso.
        params: los parametros que se usaron (PVT, IPR, correlaciones)
        results: los resultados obtenidos (oil_rate, gas_rate, nodal, etc)
        model_files: rutas de los .Out/.mbi/.gap generados
        """
        case = {
            "id": len(self.cases) + 1,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "formation": formation,
            "fluid": fluid,
            "params": params,
            "results": results,
            "model_files": model_files or {},
        }
        self.cases.append(case)
        self._save()
        return {"registrado": True, "case_id": case["id"], "total_casos": len(self.cases)}

    def find_similar(self, formation: str, fluid: str = None) -> list:
        """Busca casos exitosos previos de una formacion/fluido."""
        matches = []
        for c in self.cases:
            if c["formation"].lower() == formation.lower():
                if fluid is None or c["fluid"].lower() == fluid.lower():
                    matches.append(c)
        return matches

    def recommend_params(self, formation: str, fluid: str = "oil") -> Optional[dict]:
        """Recomienda parametros basados en casos exitosos previos.
        Devuelve el promedio de los que funcionaron, o None si no hay casos."""
        similar = self.find_similar(formation, fluid)
        if not similar:
            return None

        # Promediar parametros numericos de los casos exitosos
        agg = {}
        counts = {}
        for c in similar:
            for k, v in c.get("params", {}).items():
                try:
                    fv = float(v)
                    agg[k] = agg.get(k, 0) + fv
                    counts[k] = counts.get(k, 0) + 1
                except (TypeError, ValueError):
                    # no numerico: tomar el ultimo
                    agg[k] = v
                    counts[k] = 1

        recommended = {}
        for k, total in agg.items():
            if isinstance(total, (int, float)) and counts[k] > 0 and k in counts:
                recommended[k] = round(total / counts[k], 3) if isinstance(total, float) else total
            else:
                recommended[k] = total

        # Rango de caudales observados
        rates = [c["results"].get("oil_rate") for c in similar if c.get("results", {}).get("oil_rate")]
        rates_num = []
        for r in rates:
            try:
                rates_num.append(float(r))
            except (TypeError, ValueError):
                pass

        return {
            "basado_en_casos": len(similar),
            "parametros_recomendados": recommended,
            "caudal_oil_observado": {
                "min": min(rates_num) if rates_num else None,
                "max": max(rates_num) if rates_num else None,
                "promedio": round(sum(rates_num)/len(rates_num), 1) if rates_num else None,
            },
        }

    def stats(self) -> dict:
        by_formation = {}
        for c in self.cases:
            key = f"{c['formation']}/{c['fluid']}"
            by_formation[key] = by_formation.get(key, 0) + 1
        return {"total_casos": len(self.cases), "por_formacion": by_formation}


if __name__ == "__main__":
    fb = FeedbackLoop()
    # Demo: registrar un caso exitoso
    fb.record_success(
        formation="Vaca Muerta", fluid="oil",
        params={"api": 35, "gor": 800, "reservoir_pressure": 5500,
                "vlp_correlation": "PetroleumExperts2", "ipr_model": "Vogel"},
        results={"oil_rate": 1250, "nodal_pressure": 200},
        model_files={"prosper": "pozo1.Out"},
    )
    fb.record_success(
        formation="Vaca Muerta", fluid="oil",
        params={"api": 36, "gor": 850, "reservoir_pressure": 5600,
                "vlp_correlation": "PetroleumExperts2", "ipr_model": "Vogel"},
        results={"oil_rate": 1310},
    )
    print("Stats:", json.dumps(fb.stats(), indent=2, ensure_ascii=False))
    print("\nRecomendacion VM oil (basada en casos exitosos):")
    print(json.dumps(fb.recommend_params("Vaca Muerta", "oil"), indent=2, ensure_ascii=False))
