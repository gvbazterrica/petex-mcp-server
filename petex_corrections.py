"""
PETEX Corrections Cache
=======================
Gestiona las correcciones de variables OpenServer:
- Semilla: correcciones verificadas (corrections_seed.json, read-only)
- Aprendidas: correcciones que el MCP descubre via RAG (corrections_learned.json)

Soporta patrones con [i] para indices numericos genericos.
null = la variable no existe (no reintentar).

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import re
import json
from datetime import datetime
from typing import Optional, Dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_PATH = os.path.join(BASE_DIR, "corrections_seed.json")
LEARNED_PATH = os.path.join(BASE_DIR, "corrections_learned.json")


class CorrectionsCache:
    def __init__(self):
        self.corrections: Dict[str, Optional[str]] = {}
        self.read_only = set()
        self.learned: Dict[str, dict] = {}   # var -> {corrected, source, timestamp}
        self._load()

    def _load(self):
        # Semilla (verificada)
        if os.path.exists(SEED_PATH):
            with open(SEED_PATH, encoding="utf-8") as f:
                seed = json.load(f)
            self.corrections.update(seed.get("corrections", {}))
            self.read_only = set(seed.get("read_only", []))
        # Aprendidas (crecen solas)
        if os.path.exists(LEARNED_PATH):
            with open(LEARNED_PATH, encoding="utf-8") as f:
                self.learned = json.load(f)
            for var, info in self.learned.items():
                self.corrections[var] = info.get("corrected")

    def _index_to_pattern(self, variable: str) -> str:
        """Convierte indices numericos a patron [i]. Ej: DATA[3].MD -> DATA[i].MD"""
        return re.sub(r"\[\d+\]", "[i]", variable)

    def _pattern_to_index(self, pattern: str, original: str) -> str:
        """Reaplica los indices del original al pattern corregido."""
        indices = re.findall(r"\[(\d+)\]", original)
        result = pattern
        for idx in indices:
            result = result.replace("[i]", f"[{idx}]", 1)
        return result

    def resolve(self, variable: str) -> tuple:
        """Resuelve una variable.
        Retorna (accion, valor):
          ("ok", variable_corregida)   -> usar esta variable
          ("skip", None)               -> variable no existe, no setear
          ("readonly", None)           -> es read-only
          ("unknown", variable)        -> sin correccion conocida, usar tal cual
        """
        # Read-only
        pattern = self._index_to_pattern(variable)
        if variable in self.read_only or pattern in self.read_only:
            return ("readonly", None)

        # Correccion exacta
        if variable in self.corrections:
            corr = self.corrections[variable]
            return ("skip", None) if corr is None else ("ok", corr)

        # Correccion por patron
        if pattern in self.corrections:
            corr = self.corrections[pattern]
            if corr is None:
                return ("skip", None)
            return ("ok", self._pattern_to_index(corr, variable))

        return ("unknown", variable)

    def learn(self, wrong_var: str, correct_var: Optional[str], source: str = "RAG"):
        """Registra una correccion aprendida y la persiste."""
        pattern = self._index_to_pattern(wrong_var)
        correct_pattern = self._index_to_pattern(correct_var) if correct_var else None
        self.learned[pattern] = {
            "corrected": correct_pattern,
            "source": source,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.corrections[pattern] = correct_pattern
        self._save_learned()

    def _save_learned(self):
        with open(LEARNED_PATH, "w", encoding="utf-8") as f:
            json.dump(self.learned, f, indent=2, ensure_ascii=False)

    def summary(self) -> dict:
        return {
            "total_correcciones": len(self.corrections),
            "verificadas_semilla": len(self.corrections) - len(self.learned),
            "aprendidas": len(self.learned),
            "read_only": len(self.read_only),
            "aprendidas_detalle": self.learned,
        }


if __name__ == "__main__":
    c = CorrectionsCache()
    print("Corrections cache cargado:")
    print(json.dumps(c.summary(), indent=2, ensure_ascii=False))
    print("\nPruebas de resolve:")
    for v in [
        "PROSPER.SIN.EQP.Geo.Data[2].TVD",
        "PROSPER.PVT.Input.Salinity",
        "PROSPER.SIN.EQP.DOWN.DATA.COUNT",
        "GAP.MOD[0].SEP[0].MAXPRES",
        "PROSPER.SIN.IPR.Single.Pres",
    ]:
        print(f"  {v} -> {c.resolve(v)}")
