"""
PETEX Model Scanner - EXHAUSTIVO (hibrido)
===========================================
Escanea un modelo con cobertura completa combinando:
  - Catalogo AUTO (petex_catalog.json): descubre QUE secciones/arrays existen
    en el modelo (multilateral, gas lift, drilling, todos los nodos GAP, etc).
  - Campos CURADOS (catalog_fields_curated.json): nombres exactos verificados
    de los campos de cada array (sin ruido del PDF).

Robusto: variables que dan error/FNA se descartan. Arrays por COUNT con probe.

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(BASE, "petex_catalog.json")
CURATED = os.path.join(BASE, "catalog_fields_curated.json")

FNA_PREFIXES = ("3.4e+35", "1e+37", "1e+038")


def _get(c, var):
    try:
        v = c.DoGet(var)
        if v is None:
            return None
        s = str(v).strip()
        if s == "" or any(s.startswith(p) for p in FNA_PREFIXES):
            return None
        return v
    except Exception:
        return None


def _count(c, collection):
    """Lee el COUNT de una coleccion probando convenciones."""
    for cv in (f"{collection}.COUNT", f"{collection}.DATA.COUNT"):
        v = _get(c, cv)
        try:
            return int(float(v))
        except (TypeError, ValueError):
            continue
    return -1  # desconocido


class FullScanner:
    def __init__(self):
        with open(CATALOG, encoding="utf-8") as f:
            self.auto = json.load(f)
        with open(CURATED, encoding="utf-8") as f:
            self.curated = json.load(f)

    def _scan_array(self, c, base, fields):
        """Escanea un array recorriendo por COUNT o probe.
        Para GAP: MOD[i] es siempre MOD[0] (modelo produccion); el ultimo [i]
        es el indice del nodo a recorrer."""
        # GAP: fijar el MOD[i] a MOD[0]
        if base.startswith("GAP.MOD[i]"):
            base = base.replace("GAP.MOD[i]", "GAP.MOD[0]", 1)
        collection = base.rsplit("[i]", 1)[0]
        n = _count(c, collection)

        rows = []
        if n < 0:
            # probe: recorrer indices hasta que falle
            i = 0
            while i < 200:
                inst = base.replace("[i]", f"[{i}]", 1)
                probe_field = fields[0] if fields else None
                test = _get(c, f"{inst}.{probe_field}") if probe_field else _get(c, inst)
                if test is None:
                    break
                row = self._read_row(c, inst, fields)
                if row:
                    rows.append(row)
                i += 1
        else:
            for i in range(n):
                inst = base.replace("[i]", f"[{i}]", 1)
                row = self._read_row(c, inst, fields)
                if row:
                    rows.append(row)
        return rows

    def _read_row(self, c, inst, fields):
        row = {}
        if fields:
            for fld in fields:
                v = _get(c, f"{inst}.{fld}")
                if v is not None:
                    row[fld] = v
        else:
            v = _get(c, inst)
            if v is not None:
                row["value"] = v
        return row

    def scan(self, c, app: str) -> dict:
        app = app.upper()
        result = {"app": app, "scalars": {}, "arrays": {}, "stats": {}}

        # --- Escalares del catalogo auto (limpiando .COUNT y ruido) ---
        found_s = 0
        for var in self.auto.get(app, {}).get("scalars", []):
            if var.upper().endswith(".COUNT"):
                continue
            # descartar ruido: ultimo segmento muy largo
            last = var.rsplit(".", 1)[-1]
            if len(last) > 20:
                continue
            v = _get(c, var)
            if v is not None:
                result["scalars"][var.split(".", 1)[-1]] = v
                found_s += 1

        # --- Arrays: usar los CURADOS (nombres exactos) ---
        found_a = 0
        curated_arrays = self.curated.get(app, {})
        for base, fields in curated_arrays.items():
            rows = self._scan_array(c, base, fields)
            if rows:
                result["arrays"][base.split(".", 1)[-1]] = {"count": len(rows), "data": rows}
                found_a += 1

        result["stats"] = {
            "scalars_con_valor": found_s,
            "arrays_con_datos": found_a,
            "arrays_curados": len(curated_arrays),
        }
        return result


if __name__ == "__main__":
    fs = FullScanner()
    print("Cobertura del escaner exhaustivo (hibrido):\n")
    for app in ["PROSPER", "MBAL", "GAP"]:
        na = len(fs.curated.get(app, {}))
        ns = len([s for s in fs.auto.get(app, {}).get("scalars", [])
                  if not s.upper().endswith(".COUNT") and len(s.rsplit(".",1)[-1]) <= 20])
        print(f"{app}: {ns} escalares + {na} arrays curados")
        for arr in fs.curated.get(app, {}):
            print(f"    {arr.split('.',1)[-1]}  ({len(fs.curated[app][arr])} campos)")
