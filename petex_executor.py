"""
PETEX Smart Executor
====================
Wrapper de OpenServer con auto-correccion y aprendizaje.

Flujo de do_set():
  1. Resolver la variable contra el corrections cache
     - readonly -> no setear, avisar
     - skip -> variable no existe, no setear
     - ok -> usar la variable corregida
     - unknown -> usar tal cual
  2. Ejecutar DoSet
  3. Si falla con "Variable name was not found":
     - Consultar el RAG por el nombre correcto
     - Reintentar con la sugerencia
     - Si funciona, APRENDER la correccion (persistir)

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import time
import subprocess
from typing import Optional, Tuple, Any

from petex_corrections import CorrectionsCache


class SmartExecutor:
    def __init__(self, rag=None):
        self.cache = CorrectionsCache()
        self.rag = rag
        self.log = []          # historial de operaciones
        self.errors = []       # errores no resueltos
        self._os = None

    # ---------- Conexion ----------

    def connect(self):
        from openserver import OpenServer
        if self._os is None:
            self._os = OpenServer()
            self._os.__enter__()
        return self._os

    def close(self):
        if self._os is not None:
            try:
                self._os.__exit__(None, None, None)
            except Exception:
                pass
            self._os = None

    @property
    def os(self):
        return self.connect()

    def kill_petex(self):
        self.close()
        for app in ["prosper", "mbal", "gap"]:
            subprocess.run(["taskkill", "/F", "/IM", f"{app}.exe"],
                           capture_output=True, timeout=10)
        time.sleep(3)

    # ---------- Ejecucion con auto-correccion ----------

    def do_set(self, variable: str, value: str) -> Tuple[bool, str]:
        """DoSet con resolucion de cache + retry via RAG + aprendizaje."""
        action, resolved = self.cache.resolve(variable)

        if action == "readonly":
            msg = f"{variable} es READ-ONLY (usar .ADD para agregar filas)"
            self.log.append(("SKIP-RO", variable, msg))
            return False, msg

        if action == "skip":
            msg = f"{variable} no existe en PETEX (cache)"
            self.log.append(("SKIP", variable, msg))
            return False, msg

        target = resolved  # "ok" o "unknown" -> usar target

        # Intentar setear
        try:
            self.os.DoSet(target, str(value))
            note = "corregido" if action == "ok" else "directo"
            self.log.append(("SET", target, note))
            return True, target
        except Exception as e:
            err = str(e)
            # Solo intentar RAG si es error de variable no encontrada
            if "not found" in err.lower() and self.rag is not None:
                suggestion = self.rag.find_variable(f"{variable} OpenServer variable")
                if suggestion and suggestion != target:
                    try:
                        self.os.DoSet(suggestion, str(value))
                        # APRENDER
                        self.cache.learn(variable, suggestion, source="RAG")
                        self.log.append(("LEARN", f"{variable} -> {suggestion}", "aprendido via RAG"))
                        return True, f"{suggestion} (aprendido)"
                    except Exception:
                        pass
            self.errors.append({"var": target, "value": value, "err": err})
            return False, err

    def do_get(self, variable: str) -> Any:
        action, resolved = self.cache.resolve(variable)
        if action == "skip":
            return None
        target = resolved if action in ("ok", "unknown", "readonly") else variable
        try:
            return self.os.DoGet(target)
        except Exception:
            return None

    def do_cmd(self, command: str) -> Tuple[bool, str]:
        try:
            self.os.DoCmd(command)
            self.log.append(("CMD", command, "ok"))
            return True, "OK"
        except Exception as e:
            err = str(e)
            self.errors.append({"cmd": command, "err": err})
            return False, err

    def add_row(self, array_path: str) -> bool:
        """Agregar fila a array (DOWN.DATA, SURF.DATA, etc)."""
        try:
            self.os.DoSet(f"{array_path}.ADD", "")
            return True
        except Exception:
            return False

    # ---------- Reporting ----------

    def get_learned(self) -> dict:
        return self.cache.summary()

    def get_session_log(self) -> list:
        return self.log


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")

    # Test del executor SIN openserver (solo la logica de cache/resolucion)
    from petex_rag import PetexRAG
    rag = PetexRAG()
    rag.load_index()

    ex = SmartExecutor(rag=rag)

    print("Corrections cargadas:", ex.cache.summary()["total_correcciones"])
    print("\nSimulacion de resolucion (sin ejecutar OpenServer):")
    for v in [
        "PROSPER.SIN.EQP.Geo.Data[0].TVD",   # -> corrige a MD
        "PROSPER.PVT.Input.Salinity",          # -> skip
        "PROSPER.SIN.EQP.DOWN.DATA.COUNT",     # -> readonly
        "GAP.MOD[0].SEP[0].MAXPRES",           # -> corrige a SolverPres
    ]:
        action, resolved = ex.cache.resolve(v)
        print(f"  {v}")
        print(f"    accion={action}, resuelto={resolved}")

    print("\nRAG find_variable para una variable desconocida:")
    print("  'aquifer permeability MBAL' ->", rag.find_variable("aquifer permeability MBAL tank"))
