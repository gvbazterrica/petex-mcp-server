"""Report generator for PETEX MCP workflow results.

Produces professional HTML and PDF reports from integrated workflow outputs.
PDF generation uses weasyprint if available, falls back to pdfkit/wkhtmltopdf,
or as last resort uses the built-in HTML-to-PDF via browser printing hint.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ReportGenerator:
    """Generates HTML and PDF reports from workflow results."""

    def __init__(self, run_folder: str, well_name: str):
        self.run_folder = run_folder
        self.well_name = well_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    def generate(
        self,
        results: dict,
        reservoir_params: dict,
        well_params: dict,
        surface_params: dict,
        production_data: list,
        sources: Optional[list[dict]] = None,
        data_classification: Optional[list[dict]] = None,
    ) -> dict[str, str]:
        """Generate HTML and PDF reports.

        Args:
            results: Workflow execution results dict.
            reservoir_params: Reservoir parameters used.
            well_params: Well parameters used.
            surface_params: Surface network parameters.
            production_data: Production history data.
            sources: List of data sources consulted.
            data_classification: Parameter classification [A]/[E]/[C].

        Returns:
            Dict with 'html' and 'pdf' keys pointing to file paths.
        """
        html_content = self._build_html(
            results, reservoir_params, well_params, surface_params,
            production_data, sources, data_classification,
        )

        # Write HTML
        html_path = os.path.join(self.run_folder, f"{self.well_name}_reporte.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Generate PDF
        pdf_path = os.path.join(self.run_folder, f"{self.well_name}_reporte.pdf")
        self._html_to_pdf(html_content, pdf_path)

        return {"html": html_path, "pdf": pdf_path}

    def _html_to_pdf(self, html_content: str, pdf_path: str) -> bool:
        """Convert HTML to PDF using best available method."""
        # Method 1: weasyprint (pure Python, best quality)
        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(pdf_path)
            return True
        except ImportError:
            pass
        except Exception:
            pass

        # Method 2: pdfkit (requires wkhtmltopdf installed)
        try:
            import pdfkit
            pdfkit.from_string(html_content, pdf_path, options={
                "page-size": "A4",
                "margin-top": "15mm",
                "margin-bottom": "15mm",
                "margin-left": "15mm",
                "margin-right": "15mm",
                "encoding": "UTF-8",
                "no-outline": None,
            })
            return True
        except ImportError:
            pass
        except Exception:
            pass

        # Method 3: xhtml2pdf (pure Python fallback)
        try:
            from xhtml2pdf import pisa
            with open(pdf_path, "wb") as f:
                pisa.CreatePDF(html_content, dest=f)
            return True
        except ImportError:
            pass
        except Exception:
            pass

        # If no PDF library available, write a note
        note_path = pdf_path.replace(".pdf", "_PDF_INSTRUCCIONES.txt")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(
                f"Para generar el PDF, abrir el HTML en un navegador e imprimir a PDF:\n"
                f"  {pdf_path.replace('.pdf', '.html')}\n\n"
                f"O instalar weasyprint:\n"
                f"  pip install weasyprint\n"
                f"  python -c \"from weasyprint import HTML; "
                f"HTML('{pdf_path.replace('.pdf', '.html')}').write_pdf('{pdf_path}')\"\n"
            )
        return False

    def _build_html(
        self,
        results: dict,
        reservoir_params: dict,
        well_params: dict,
        surface_params: dict,
        production_data: list,
        sources: Optional[list[dict]],
        data_classification: Optional[list[dict]],
    ) -> str:
        """Build complete HTML report."""
        fluid = results.get("fluid_type", "oil")
        is_oil = fluid == "oil"
        status = results.get("status", {})
        files = results.get("files", {})
        calc_results = results.get("results", {})
        errors = results.get("errors", [])
        exec_mode = results.get("execution_mode", "script_only")
        duration = results.get("duration_seconds", 0)

        sections = [
            self._section_header(fluid, results),
            self._section_sources(sources),
            self._section_data_classification(data_classification),
            self._section_parameters(reservoir_params, well_params, surface_params, is_oil),
            self._section_production(production_data, is_oil),
            self._section_topology(results),
            self._section_results(calc_results, is_oil, exec_mode),
            self._section_files(files, status),
            self._section_execution(status, exec_mode, duration, errors),
            self._section_instructions(self.run_folder, self.well_name),
            self._section_footer(),
        ]

        return self._wrap_html("\n".join(sections))

    def _wrap_html(self, body: str) -> str:
        """Wrap body content in full HTML document with styles."""
        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{self.well_name} — Reporte Workflow Integrado PETEX</title>
<style>
@page {{ size: A4; margin: 15mm; }}
body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
       max-width: 1000px; margin: 2em auto; padding: 0 1.5em;
       color: #1a1a1a; line-height: 1.6; font-size: 14px; }}
h1 {{ color: #1a5276; border-bottom: 3px solid #1a5276; padding-bottom: .4em;
     font-size: 1.8em; margin-top: 0; }}
h2 {{ color: #2471a3; margin-top: 2em; font-size: 1.3em;
     border-bottom: 1px solid #d5dbdb; padding-bottom: .2em; }}
h3 {{ color: #1a5276; margin-top: 1.2em; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.9em; }}
th, td {{ border: 1px solid #bdc3c7; padding: 6px 10px; text-align: left; }}
th {{ background: #2471a3; color: #fff; font-weight: 600; }}
tr:nth-child(even) {{ background: #f8f9fa; }}
tr:hover {{ background: #eaf2f8; }}
.tag-a {{ background: #27ae60; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: .75em; }}
.tag-e {{ background: #f39c12; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: .75em; }}
.tag-c {{ background: #8e44ad; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: .75em; }}
.status-ok {{ color: #27ae60; font-weight: bold; }}
.status-err {{ color: #e74c3c; font-weight: bold; }}
.status-pending {{ color: #f39c12; font-weight: bold; }}
code {{ background: #ecf0f1; padding: 2px 5px; border-radius: 3px; font-size: .85em; }}
pre {{ background: #2c3e50; color: #ecf0f1; padding: 1em; border-radius: 6px;
       overflow-x: auto; font-size: .85em; line-height: 1.4; }}
.topo {{ font-family: 'Cascadia Code', 'Fira Code', monospace;
         background: #1b2631; color: #aed6f1; padding: 1.2em;
         border-radius: 8px; white-space: pre; line-height: 1.5; }}
.metric-box {{ display: inline-block; background: #eaf2f8; border: 1px solid #aed6f1;
              border-radius: 6px; padding: 8px 14px; margin: 4px; text-align: center; }}
.metric-value {{ font-size: 1.4em; font-weight: bold; color: #1a5276; }}
.metric-label {{ font-size: .8em; color: #5d6d7e; }}
.note {{ background: #fef9e7; border-left: 4px solid #f39c12; padding: .8em; margin: 1em 0; }}
hr {{ border: none; border-top: 1px solid #d5dbdb; margin: 2em 0; }}
@media print {{
  body {{ font-size: 11px; margin: 0; padding: 0; }}
  h1 {{ font-size: 1.5em; }}
  .no-print {{ display: none; }}
  table {{ page-break-inside: avoid; }}
}}
</style>
</head>
<body>
{body}
</body>
</html>"""

    def _section_header(self, fluid: str, results: dict) -> str:
        icon = "🛢️" if fluid == "oil" else "🔥"
        run_folder = results.get("run_folder", self.run_folder)
        return f"""<h1>{icon} {self.well_name} — Modelo Integrado PETEX</h1>
<p><strong>Fluido:</strong> {fluid.upper()} |
<strong>Fecha:</strong> {self.timestamp} |
<strong>Carpeta:</strong> <code>{Path(run_folder).name}</code></p>"""

    def _section_sources(self, sources: Optional[list[dict]]) -> str:
        if not sources:
            return ""
        rows = ""
        for i, src in enumerate(sources, 1):
            rows += f"<tr><td>{i}</td><td>{src.get('source', 'N/A')}</td><td>{src.get('data', 'N/A')}</td></tr>\n"
        return f"""<h2>1. Fuentes Consultadas</h2>
<table>
<tr><th>#</th><th>Fuente</th><th>Dato extraído</th></tr>
{rows}</table>"""

    def _section_data_classification(self, data_class: Optional[list[dict]]) -> str:
        if not data_class:
            return ""
        rows = ""
        count_a = count_e = count_c = 0
        for item in data_class:
            tag = item.get("type", "E")
            tag_class = {"A": "tag-a", "E": "tag-e", "C": "tag-c"}.get(tag, "tag-e")
            if tag == "A": count_a += 1
            elif tag == "E": count_e += 1
            else: count_c += 1
            rows += (
                f"<tr><td>{item.get('parameter', '')}</td>"
                f"<td>{item.get('value', '')}</td>"
                f"<td>{item.get('unit', '')}</td>"
                f"<td><span class=\"{tag_class}\">{tag}</span></td>"
                f"<td>{item.get('source', '')}</td></tr>\n"
            )
        return f"""<h2>2. Datos Reales vs Estimados</h2>
<table>
<tr><th>Parámetro</th><th>Valor</th><th>Unidad</th><th>Tipo</th><th>Fuente</th></tr>
{rows}</table>
<p><strong>Conteo:</strong> {count_a} <span class="tag-a">A</span> reales,
{count_e} <span class="tag-e">E</span> estimados,
{count_c} <span class="tag-c">C</span> calculados</p>"""

    def _section_parameters(self, rp: dict, wp: dict, sp: dict, is_oil: bool) -> str:
        """Key parameters summary."""
        rows = ""
        all_params = [("Reservorio", rp), ("Pozo", wp), ("Superficie", sp)]
        for section, params in all_params:
            for k, v in params.items():
                rows += f"<tr><td>{section}</td><td>{k}</td><td>{v}</td></tr>\n"
        return f"""<h2>3. Parámetros del Modelo</h2>
<table>
<tr><th>Sección</th><th>Parámetro</th><th>Valor</th></tr>
{rows}</table>"""

    def _section_production(self, production_data: list, is_oil: bool) -> str:
        if not production_data:
            return ""
        if is_oil:
            header = "<tr><th>Mes</th><th>Oil (m³)</th><th>Gas (Mm³)</th><th>Water (m³)</th><th>Días</th></tr>"
        else:
            header = "<tr><th>Mes</th><th>Gas (Mm³)</th><th>Cond (m³)</th><th>Water (m³)</th><th>Días</th></tr>"

        rows = ""
        for row in production_data:
            cells = "".join(f"<td>{v}</td>" for v in row)
            rows += f"<tr>{cells}</tr>\n"

        return f"""<h2>4. Producción Histórica</h2>
<table>
{header}
{rows}</table>
<p><strong>Total:</strong> {len(production_data)} meses de datos</p>"""

    def _section_topology(self, results: dict) -> str:
        """Network topology diagram."""
        wells = results.get("wells", [])
        well_name = self.well_name
        if not wells:
            return f"""<h2>5. Topología de Red</h2>
<div class="topo">
{well_name} ──[Flowline]──> MANIFOLD ──[Trunk]──> SEPARATOR
</div>"""
        lines = []
        for i, w in enumerate(wells):
            connector = "├" if i < len(wells) - 1 else "└"
            lines.append(f"{w} ──[FL]──{connector}")
        topo = "\n".join(lines) + f"── MANIFOLD ──[TRK]── SEP"
        return f"""<h2>5. Topología de Red</h2>
<div class="topo">{topo}</div>"""

    def _section_results(self, calc_results: dict, is_oil: bool, exec_mode: str) -> str:
        if not calc_results:
            note = "Requiere ejecución COM con licencia PETEX" if exec_mode == "script_only" else "Sin resultados"
            return f"""<h2>6. Resultados de Cálculo</h2>
<div class="note">⚠️ {note}</div>"""

        boxes = ""
        for key, value in calc_results.items():
            label = key.replace("_", " ").title()
            boxes += f'<div class="metric-box"><div class="metric-value">{value}</div><div class="metric-label">{label}</div></div>\n'
        return f"""<h2>6. Resultados de Cálculo</h2>
{boxes}"""

    def _section_files(self, files: dict, status: dict) -> str:
        if not files:
            return ""
        rows = ""
        for app, path in files.items():
            app_status = status.get(app, "ok")
            status_class = "status-ok" if app_status == "ok" else "status-pending"
            icon = "✅" if app_status == "ok" else "⏳"
            rows += f"<tr><td>{app.upper()}</td><td><code>{Path(path).name}</code></td><td class=\"{status_class}\">{icon} {app_status}</td></tr>\n"
        return f"""<h2>7. Archivos Generados</h2>
<table>
<tr><th>App</th><th>Archivo</th><th>Estado</th></tr>
{rows}</table>"""

    def _section_execution(self, status: dict, exec_mode: str, duration: float, errors: list) -> str:
        mode_label = {
            "script_only": "📝 Script generado (sin ejecución COM)",
            "live": "🚀 Ejecutado via OpenServer COM",
            "no_license": "⚠️ Sin licencia PETEX disponible",
        }.get(exec_mode, exec_mode)

        rows = ""
        for app, st in status.items():
            icon = {"ok": "✅", "script_only": "📝", "no_license": "⚠️", "error": "❌", "pending": "⏳"}.get(st, "❓")
            rows += f"<tr><td>{app.upper()}</td><td>{icon} {st}</td></tr>\n"

        err_html = ""
        if errors:
            err_items = "".join(f"<li>{e}</li>" for e in errors)
            err_html = f'<div class="note">⚠️ Errores:<ul>{err_items}</ul></div>'

        return f"""<h2>8. Estado de Ejecución</h2>
<p><strong>Modo:</strong> {mode_label}<br>
<strong>Duración:</strong> {duration:.1f} segundos</p>
<table>
<tr><th>Aplicación</th><th>Estado</th></tr>
{rows}</table>
{err_html}"""

    def _section_instructions(self, run_folder: str, well_name: str) -> str:
        script_name = f"{well_name}_workflow.py"
        return f"""<h2>9. Instrucciones de Ejecución</h2>
<p>Para ejecutar en una máquina con licencia PETEX IPM:</p>
<pre><code>cd {run_folder}
python {script_name}</code></pre>
<p><strong>Requisitos:</strong></p>
<ul>
<li>PETEX IPM instalado (PROSPER + MBAL + GAP)</li>
<li>Licencia OpenServer activa (COM <code>PX32.OpenServer.1</code>)</li>
<li>Python 3.11+ con <code>pywin32</code></li>
<li>El script detecta licencia automáticamente (timeout 6s)</li>
</ul>"""

    def _section_footer(self) -> str:
        return f"""<hr>
<p style="color:#888;font-size:.8em">
Generado por PETEX MCP Server — {self.timestamp}
</p>"""
