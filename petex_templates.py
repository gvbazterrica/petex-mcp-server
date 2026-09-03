"""
PETEX Templates Manager
=======================
Workaround del blocker de PROSPER (tubing description).

PROSPER requiere generar la "tubing description" desde la GUI (boton Done en
Equipment Data), lo que no tiene comando OpenServer. La solucion: mantener
plantillas .Out YA VALIDADAS (creadas una vez a mano con licencia) que el MCP
CLONA y solo modifica parametros (PVT, IPR, presion, skin...). Como el equipment
ya esta validado en la plantilla, el modelo clonado corre sin intervencion manual.

Flujo:
  1. clone_template(tipo, destino) -> copia el .Out validado
  2. apply_parameters(destino, params) -> ajusta valores via SmartExecutor (auto-correccion)
  3. el .Out resultante esta listo para nodal / VLP / GAP

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import json
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(BASE, "templates_registry.json")


class TemplateManager:
    def __init__(self):
        with open(REGISTRY, encoding="utf-8") as f:
            self.registry = json.load(f)
        self.templates = self.registry["templates"]

    def list_templates(self) -> dict:
        """Lista las plantillas disponibles y si estan validadas."""
        return {
            name: {
                "descripcion": t["descripcion"],
                "fluid": t["fluid"],
                "trajectory": t["trajectory"],
                "validado": t.get("validado", False),
                "parametros": list(t["parametros_ajustables"].keys()),
            }
            for name, t in self.templates.items()
        }

    def get_template(self, name: str) -> dict:
        return self.templates.get(name)

    def clone(self, template_name: str, dest_path: str) -> tuple:
        """Copia el .Out de la plantilla al destino. Retorna (ok, msg)."""
        t = self.templates.get(template_name)
        if not t:
            return False, f"Template '{template_name}' no existe"
        src = os.path.join(BASE, t["file"])
        if not os.path.exists(src):
            return False, (f"Plantilla {t['file']} no encontrada. "
                           f"Crear primero (ver TEMPLATES_README.md).")
        try:
            shutil.copy2(src, dest_path)
            return True, dest_path
        except Exception as e:
            return False, str(e)

    def apply_parameters(self, executor, template_name: str,
                         dest_path: str, params: dict) -> dict:
        """Aplica parametros al .Out clonado via el SmartExecutor.
        params: dict con claves del 'parametros_ajustables' del template.
        executor: SmartExecutor con conexion OpenServer.
        """
        t = self.templates.get(template_name)
        if not t:
            return {"error": f"Template '{template_name}' no existe"}

        mapping = t["parametros_ajustables"]
        result = {"aplicados": [], "ignorados": [], "errores": []}

        executor.kill_petex()
        ok, msg = executor.do_cmd('PROSPER.START("")')
        if not ok:
            return {"error": f"No se pudo iniciar PROSPER: {msg}"}
        executor.do_cmd(f'PROSPER.OPENFILE("{dest_path}")')

        for key, value in params.items():
            var = mapping.get(key)
            if not var:
                result["ignorados"].append(f"{key} (no ajustable en este template)")
                continue
            ok, res = executor.do_set(var, str(value))
            if ok:
                result["aplicados"].append(f"{key} = {value}")
            else:
                result["errores"].append(f"{key}: {res}")

        executor.do_cmd(f'PROSPER.SAVEFILE("{dest_path}")')
        executor.do_cmd("PROSPER.SHUTDOWN()")
        result["archivo"] = dest_path
        return result

    def create_from_template(self, executor, template_name: str,
                             dest_path: str, params: dict) -> dict:
        """Flujo completo: clonar + aplicar parametros."""
        ok, msg = self.clone(template_name, dest_path)
        if not ok:
            return {"error": msg}
        return self.apply_parameters(executor, template_name, dest_path, params)


if __name__ == "__main__":
    tm = TemplateManager()
    print("Plantillas registradas:\n")
    print(json.dumps(tm.list_templates(), indent=2, ensure_ascii=False))
