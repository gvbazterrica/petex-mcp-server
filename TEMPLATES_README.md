# Plantillas .Out pre-validadas - Como crearlas

## Por que existen

PROSPER tiene un blocker para automatizacion: la "tubing description" (el perfil
interno de tuberia) se genera cuando el usuario hace click en **Done** en la
pantalla de Equipment Data de la GUI. Ese paso NO tiene comando OpenServer en
IPM 13.5. Sin el, cualquier calculo (nodal, VLP) falla con:

    "You must enter either SURFACE EQUIPMENT or TUBING description (or both)"

## La solucion: plantillas

En vez de construir cada pozo desde cero via OpenServer (que choca con el blocker),
mantenemos **plantillas .Out ya validadas**. Se crean UNA sola vez a mano con
licencia, y despues el MCP las clona y solo cambia parametros (PVT, IPR, presion,
skin, largo lateral...). Como el equipment ya esta validado en la plantilla, el
modelo clonado corre sin intervencion manual.

## Como crear una plantilla base (paso manual, una vez)

Para cada tipo de pozo del registro (`templates_registry.json`):

1. Abrir PROSPER con licencia
2. Crear el modelo completo del tipo de pozo:
   - System Summary (producer, oil/gas, tubing, lift method, completion)
   - PVT (valores tipicos del area)
   - Deviation Survey (vertical / horizontal segun el tipo)
   - Equipment Data (downhole: X-mas Tree + Tubing + Casing con todos los diametros)
   - Geothermal gradient
   - IPR (Vogel / Darcy / C and n)
   - VLP correlation (PetroleumExperts2)
3. **CLAVE**: entrar a System > Equipment Data y hacer **Done** (genera la tubing description)
4. Verificar que un nodal analysis corre sin error
5. Guardar como el nombre indicado en el registro, dentro de la carpeta `templates/`:
   - `templates/horizontal_oil_vm.Out`
   - `templates/vertical_oil_conv.Out`
   - `templates/horizontal_gas_vm.Out`
6. Marcar `"validado": true` en `templates_registry.json`

## Como el MCP las usa

```python
from petex_templates import TemplateManager
tm = TemplateManager()

# Clonar + aplicar parametros en un solo paso
tm.create_from_template(
    executor,                       # SmartExecutor con conexion
    "horizontal_oil_vm",            # tipo de pozo
    "C:/modelos/pozo_nuevo.Out",    # destino
    {                               # parametros a ajustar
        "reservoir_pressure": 5500,
        "api": 35,
        "gor": 800,
        "lateral_length_ft": 13123,
        "vlp_correlation": "PetroleumExperts2",
    }
)
# Resultado: pozo_nuevo.Out validado y listo para nodal/VLP/GAP
```

O desde el MCP en lenguaje natural:

    "Crea un pozo horizontal de Vaca Muerta con presion 5500 y GOR 800"
    -> create_from_template

## Ventaja

Con las plantillas validadas, el orquestador `build_integrated_model` funciona
end-to-end SIN el paso manual del Done, porque parte de un equipment ya validado.
Es el ultimo eslabon para automatizacion completa de PROSPER.

## Nota

Las plantillas .Out son binarios y NO se suben a git por defecto (ver .gitignore).
Cada instalacion de UDS debe generar las suyas con sus datos de campo, o
compartirlas por un storage comun (S3, red interna).
