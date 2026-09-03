"""
Consolida petex_catalog_raw.json en petex_catalog.json estructurado:
- Filtra variables de INPUT del modelo (lo que define el modelo, no resultados)
- Marca arrays (variables con [i]) y su .COUNT asociado
- Agrupa por seccion para el escaner
"""
import json
import re

RAW = r"C:\Users\xgvb02\Desktop\Ds\MCP\test dario petex\petex_catalog_raw.json"
OUT = r"C:\Users\xgvb02\Desktop\Ds\MCP\test dario petex\petex_catalog.json"

raw = json.load(open(RAW, encoding="utf-8"))

# Prefijos de INPUT del modelo (lo que compone el modelo guardado)
INPUT_PREFIXES = {
    "PROSPER": ("PROSPER.SIN.", "PROSPER.PVT.Input", "PROSPER.PVT.CORREL"),
    "MBAL": ("MBAL.MB.", "MBAL.MB[",),
    "GAP": ("GAP.MOD[", "GAP.MOD."),
}
# Excluir resultados y calculos
EXCLUDE = ("OUT.", ".OUT", "Results", "PREDRES", "SolverResults", "SolverStatus")


def is_input(app, var):
    if any(x in var for x in EXCLUDE):
        return False
    return any(var.startswith(p) for p in INPUT_PREFIXES[app])


catalog = {}
for app in raw:
    vars_in = [v for v in raw[app] if is_input(app, v)]

    arrays = {}      # base_path -> [campos]
    scalars = []

    # Campo valido: solo letras/numeros (los que tienen texto pegado del PDF se descartan)
    FIELD_OK = re.compile(r"^[A-Za-z][\w]{0,20}$")

    for v in vars_in:
        # Descartar entradas con ruido del PDF (dos variables pegadas)
        # Se detecta por tener texto tipo "LabelPROSPER" o palabras largas mayus/minus mezcladas
        if re.search(r"[a-z][A-Z]{2,}", v.split("[i]")[0].split(".")[-1] or ""):
            pass  # puede ser valido, no descartar por esto solo
        if "[i]" in v:
            base = v.rsplit("[i]", 1)[0] + "[i]"
            field = v[len(base):].lstrip(".")
            # Validar que TODO el base este limpio (cada segmento es un identificador valido)
            base_segments = re.split(r"[.\[\]]", base)
            base_ok = all(FIELD_OK.match(s) or s == "i" or s == "" for s in base_segments)
            if not base_ok:
                continue  # ruido del PDF, descartar
            arrays.setdefault(base, set())
            if field and FIELD_OK.match(field):
                arrays[base].add(field)
        else:
            segments = re.split(r"[.\[\]]", v)
            if all(FIELD_OK.match(s) or s == "i" or s == "" for s in segments):
                scalars.append(v)

    catalog[app] = {
        "scalars": sorted(scalars),
        "arrays": {k: sorted(v) for k, v in sorted(arrays.items())},
    }

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=1, ensure_ascii=False)

# Resumen
for app in catalog:
    ns = len(catalog[app]["scalars"])
    na = len(catalog[app]["arrays"])
    print(f"{app}: {ns} escalares, {na} arrays")

print("\nArrays de PROSPER (colecciones a recorrer):")
for base in list(catalog["PROSPER"]["arrays"])[:25]:
    fields = catalog["PROSPER"]["arrays"][base]
    print(f"  {base}  ->  {len(fields)} campos")
