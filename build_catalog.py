"""
Extrae el catalogo COMPLETO de variables OpenServer del manual.
Maneja el problema de variables cortadas por saltos de linea en el PDF.
"""
import re
import json
from PyPDF2 import PdfReader

PDF = r"C:\Users\xgvb02\Desktop\Ds\MCP\test dario petex\openserver.pdf"
OUT = r"C:\Users\xgvb02\Desktop\Ds\MCP\test dario petex\petex_catalog_raw.json"

# Variable puede tener saltos de linea: PROSPER.SIN.EQP.DOWN\nDATA[i].TID
# Estrategia: unir todo el texto, colapsar espacios/saltos, luego regex tolerante
VAR_RE = re.compile(
    r"\b(PROSPER|MBAL|GAP)\s*\.\s*"           # app + punto
    r"(?:[A-Za-z][\w]*\s*(?:\[[^\]]*\])?\s*\.?\s*){2,}"  # cadena de .SECCION[idx]
)

reader = PdfReader(PDF)
total = len(reader.pages)

raw_vars = {"PROSPER": set(), "MBAL": set(), "GAP": set()}

for i in range(total):
    try:
        text = reader.pages[i].extract_text()
    except Exception:
        continue
    if not text:
        continue
    # Colapsar saltos de linea y espacios multiples (une variables cortadas)
    joined = re.sub(r"\s+", " ", text)
    for m in VAR_RE.finditer(joined):
        var = re.sub(r"\s+", "", m.group(0)).rstrip(".")
        app = m.group(1)
        # Cortar en el punto donde empieza texto descriptivo pegado:
        # un campo valido es alfanumerico; si aparece un patron minuscula->MAYUS
        # que no sea parte de la ruta, cortamos. Estrategia simple: cortar el
        # segmento final si contiene una transicion tipo "LABELLabel" o "TmpTemperature".
        # Partimos por segmentos y validamos cada uno.
        segs = re.split(r"(\.|\[[^\]]*\])", var)
        clean = []
        for s in segs:
            if s in (".",) or s.startswith("["):
                clean.append(s)
                continue
            if not s:
                continue
            # Un segmento valido: identificador corto. Si es largo con transicion
            # de mayus/minus repetida, cortar en la primera palabra.
            mm = re.match(r"^[A-Z]{2,}|^[A-Za-z][a-z]*|^[A-Za-z]\w{0,15}$", s)
            if len(s) > 16:
                # cortar en la primera "palabra" plausible
                w = re.match(r"^[A-Za-z][a-z0-9]*|^[A-Z0-9]+", s)
                clean.append(w.group(0) if w else s[:16])
                break
            clean.append(s)
        var = "".join(clean).rstrip(".")
        norm = re.sub(r"\[\d+\]", "[i]", var)
        norm = re.sub(r"\[[a-z_]\]", "[i]", norm)
        norm = re.sub(r"\[\$\]", "[i]", norm)
        if 12 < len(norm) < 70 and norm.count(".") >= 2:
            raw_vars[app].add(norm)

catalog = {app: sorted(raw_vars[app]) for app in raw_vars}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=1, ensure_ascii=False)

for app in catalog:
    print(f"{app}: {len(catalog[app])} variables")
