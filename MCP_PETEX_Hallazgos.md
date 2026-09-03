# Hallazgos MCP PETEX - OpenServer Variable Mapping (Actualizado)
**Fecha**: 2026-08-27  
**Autor**: Gonzalo Vidal Bazterrica - UDS Pan Energy  
**Entorno**: IPM 13.5 (build 850), Python OpenServer (pip), Anaconda 3.13, Windows  
**Fuentes**: openserver.pdf (612p), prosper2.pdf (2206p), GAP.pdf (1252p), mbal.pdf (907p)

---

## 1. Resumen Ejecutivo

Se construyo un modelo integrado PROSPER-MBAL-GAP via MCP PETEX y OpenServer Python.
Se descubrieron 30+ discrepancias entre los nombres de variables del MCP original y los reales.
Se documento la solucion completa y se diseño un MCP v2 con RAG + Knowledge Base de ingenieria.

**Blocker principal**: PROSPER requiere un paso de validacion GUI ("Done" en Equipment Data)
que no tiene equivalente OpenServer. MBAL y GAP SI son 100% automatizables.

---

## 2. PROSPER - Variables Incorrectas y Correcciones

### 2.1 PVT (PROSPER.PVT.Input.*)
| Campo | MCP Original | Real | Status |
|-------|-------------|------|--------|
| API | Api | Api | OK |
| Gas Gravity | GrvGas | GrvGas | OK |
| Solution GOR | SolGOR | SolGOR | OK |
| Water Gravity | Wgr | Wgr | OK |
| Reservoir Temp | Tres | Tres | OK (Fahrenheit) |
| H2S | H2S | H2S | OK |
| CO2 | CO2 | CO2 | OK |
| N2 | N2 | N2 | OK |
| Pb Correlation | PbCorr | PbCorr | OK (0=Glaso, 1=Standing) |
| **Salinidad** | **Salinity** | **NO EXISTE** | ERROR |

### 2.2 Geothermal (PROSPER.SIN.EQP.GEO.*)
| Campo | MCP Original | Real (doc p275) | Status |
|-------|-------------|-----------------|--------|
| **Profundidad** | **Geo.Data[i].TVD** | **GEO.DATA[i].MD** | ERROR: Es MD no TVD |
| **Temperatura** | **Geo.Data[i].Temp** | **GEO.DATA[i].TMP** | ERROR: Es TMP no Temp |
| **U value** | **Geo.Uval** | **GEO.HTC** | ERROR: Es HTC |
| U per point | No generado | GEO.DATA[i].HTC | MISSING |
| Injected fluid temp | No generado | GEO.INJ | MISSING |
| Count | SET intentado | DATA.COUNT (READ-ONLY) | ERROR |

### 2.3 Deviation Survey (PROSPER.SIN.EQP.Devn.*)
| Campo | MCP Original | Real (doc p271) | Status |
|-------|-------------|-----------------|--------|
| MD | Data[i].Md | Data[i].Md | OK (auto-extends) |
| TVD | Data[i].Tvd | Data[i].Tvd | OK (auto-extends) |
| **Count** | **DEVN.DATA.COUNT (SET)** | **READ-ONLY** | ERROR |
| Raw data | No usado | RawMSD[i], RawTVD[i] (hasta 1000 pts) | Disponible |
| Filter | No usado | PROSPER.EQP.DEV.FIL.FILTER (DoCmd) | Disponible |

### 2.4 Downhole Equipment (PROSPER.SIN.EQP.DOWN.*)
| Campo | MCP Original | Real (doc p273) | Status |
|-------|-------------|-----------------|--------|
| **Count** | **SET intentado** | **READ-ONLY** | ERROR |
| **Agregar fila** | **No usado** | **DATA.ADD (DoSet "")** | CRITICO: Descubierto en sesion |
| Insert | No usado | DATA[i].INSERT (DoSet "") | Disponible |
| Delete | No usado | DATA[i].DELETE (DoSet "") | Disponible |
| Type | TYPE = "0" | TYPE: 0=Tubing, 1=XmasTree, 2=Casing, 3=SSSV, 4=Restriction | REVISAR mapping |
| MULT | No seteado | DATA[i].MULT = "1" | MISSING: OBLIGATORIO |
| COD | Seteado | DATA[i].COD | Opcional |
| COR | Seteado | DATA[i].COR | Opcional |

**Doc p273**: "ALL input variables needed in downhole equipment MUST be specified.
If roughness is left to default and not specified, the section will NOT be validated."

Patron correcto (del manual de PROSPER):
```
[0] X-mas Tree: TYPE=1, DEPTH=0, sin diametros, MULT=1
[1] Tubing:     TYPE=0, DEPTH=TD, TID/TIR/TOD/TOR/CID/CIR, MULT=1
[2] Casing:     TYPE=2, DEPTH=shoe, CID/CIR, MULT=1
```

### 2.5 Surface Equipment (PROSPER.SIN.EQP.SURF.*)
| Campo | MCP Original | Real (doc p272) | Status |
|-------|-------------|-----------------|--------|
| **Global HTC** | **No generado** | **SURF.HTC** | MISSING |
| **Ambient Temp** | **No generado** | **SURF.TMP** | MISSING |
| TYPE | TYPE=0 (None) | TYPE: 0=None, 1=Pipe, 2=Choke, 3=Fittings | ERROR |
| TVD | No generado | DATA[i].TVD | MISSING |
| TEMP | No generado | DATA[i].TEMP (fluid temp) | MISSING |
| MULT | No generado | DATA[i].MULT | MISSING: OBLIGATORIO |
| HTC per item | No generado | DATA[i].HTC | MISSING |

### 2.6 IPR (PROSPER.SIN.IPR.Single.*)
| Campo | MCP Original | Real | Status |
|-------|-------------|------|--------|
| Model | IprModel | IprModel | OK ("Vogel", "Darcy", "C and n") |
| Pressure | Pres | Pres | OK |
| Skin | Skin | Skin | OK |
| Thickness | Thickness | Thickness | OK |
| **Horizontal Length** | **HzLength** | **WellLen** | ERROR |
| **Perm Ratio** | **HzPermRatio** | **NO EXISTE** | ERROR |
| **IPR Temp** | **Temp** | **NO EXISTE** (usa PVT.Input.Tres) | ERROR |
| Drainage | No usado | Drainage | Disponible |
| WBR | No usado | WBR | Disponible |

### 2.7 System Analysis (PROSPER.ANL.SYS.*)
| Campo | MCP Original | Real (doc p290) | Status |
|-------|-------------|-----------------|--------|
| First Node Pres | Pres | Pres | OK |
| Tubing corr | ANL.VLP.TubingLabel | **ANL.SYS.TubingLabel** | VERIFICAR: ambos existen |
| Pipeline corr | No generado | ANL.SYS.PipeLabel | MISSING |
| **Water Cut** | **No generado** | **ANL.SYS.WC** | MISSING |
| **GOR** | **No generado** | **ANL.SYS.GOR** | MISSING |
| WGR | No generado | ANL.SYS.WGR (gas wells) | MISSING |
| CGR | No generado | ANL.SYS.CGR (gas wells) | MISSING |
| **Temp** | **ANL.SYS.Temp** | **NO EXISTE** | ERROR |
| **Node Position** | **ANL.SYS.NodePosition** | **NO EXISTE** | ERROR |
| CALC | ANL.SYS.CALC | ANL.SYS.CALC (DoCmd) | OK |

---

## 3. MBAL - Variables Verificadas (doc p156-210)

### 3.1 Comandos clave
| Comando | Funcion |
|---------|---------|
| MBAL.START("") | Iniciar |
| MBAL.SHUTDOWN() | Cerrar |
| MBAL.NEWMODEL() | Nuevo modelo |
| MBAL.OPENFILE("path") | Abrir |
| MBAL.SaveFile("path") | Guardar |
| **MBAL.MB.VALIDATE** | **Validar todos los objetos (SIN GUI)** |
| MBAL.MB.RunSimulation | History match |
| MBAL.MB.LINKITEMS(obj1, obj2) | Vincular tank-well |
| MBAL.MB.PVT.INPUT.CALCULATE | Calcular PVT |
| MBAL.MB.STARTPRED / NEXTSTEPPRED / ENDPRED | Prediccion step-by-step |
| MBAL.MB.IMPORTTPD(well, "file.tpd") | Importar VLP de PROSPER |

### 3.2 Tank (MBAL.MB[0].TANK[{label}].*)
OOIP, OGIP, POR, CONWAT, PRESS, TEMP, ROCKCOMP, WATCOMP, PERM, PAYZONE, TYPE (OIL/GAS/CON/WAT)

### 3.3 PVT (MBAL.MB[0].PVT.INPUT.*)
OILGRAV, GASGRAV, SOLGOR, WATSAL, H2S, CO2, N2, TRES, PBUB

### 3.4 Production History (MBAL.MB[0].TANK[{label}].PRODHIST[i].*)
TIME, PRESS, CUMOIL, CUMGAS, CUMWAT, CUMGASINJ, CUMWATINJ, RECOFF

### 3.5 Prediction (MBAL.MB[0].PREDINP.*)
CALCTYPE (RES_PRESS/MANPRESS/PROD/DCQ), START, USERSTART, END, USEREND, STEPTYPE, USERSTEP

**MBAL es 100% automatizable via OpenServer** gracias a MBAL.MB.VALIDATE.

---

## 4. GAP - Variables Verificadas (doc p44-135)

### 4.1 Comandos clave
| Comando | Funcion | Nota |
|---------|---------|------|
| GAP.START("") | Iniciar | |
| GAP.SHUTDOWN() | Cerrar | |
| GAP.NEWFILE() | Nuevo (DoGAPFunc) | |
| GAP.OPENFILE("path") | Abrir (DoGAPFunc) | |
| GAP.SAVEFILE("path") | Guardar | |
| GAP.SOLVENETWORK(opt, model, pot) | Resolver red | DoGAPFunc, retorna valor |
| GAP.PREDINIT() | Init prediccion | Retorna num steps |
| GAP.PREDDOSTEP(opt, pot) | Paso prediccion | |
| GAP.PREDEND() | Fin prediccion | |
| GAP.NEWITEM("type","label","pos",parent,model) | Crear elemento | DoGAPFunc |
| GAP.LINKITEMS(from, to, "") | Conectar elementos | DoGAPFunc |

### 4.2 Crear red (patron correcto)
```
' Crear elementos
DoGAPFunc("GAP.NEWITEM(""WELL"", ""W1"", ""RIGHT"", NULL, MOD[0])")
DoGAPFunc("GAP.NEWITEM(""SEP"",  ""S1"", ""RIGHT"", NULL, MOD[0])")
DoGAPFunc("GAP.NEWITEM(""PIPE"", ""P1"", ""RIGHT"", MOD[0].EQUIP[{W1}], MOD[0])")

' Conectar
DoGAPFunc("GAP.LINKITEMS(MOD[0].EQUIP[{W1}], MOD[0].PIPE[{P1}], """")")
DoGAPFunc("GAP.LINKITEMS(MOD[0].PIPE[{P1}], MOD[0].EQUIP[{S1}], """")")

' Tank
DoGAPFunc("GAP.NEWITEM(""TANK"", ""T1"", ""RIGHT"", NULL, MOD[0])")
DoGAPFunc("GAP.LINKITEMS(MOD[0].TANK[{T1}], MOD[0].WELL[{W1}], """")")
```

### 4.3 Well types (literal constants recomendadas)
OilProducerNoLift, OilProducerGL, OilProducerESP, GasProducer

### 4.4 Solver Results (GAP.MOD[0].SEP[{label}].SolverResults[0].*)
Qoil, Qgas, Qwat, WHP, BHP

### 4.5 DoGAPFunc vs DoCmd
GAP usa DoGAPFunc para: NEWFILE, OPENFILE, NEWITEM, LINKITEMS, SOLVENETWORK, PREDINIT, PREDDOSTEP, PREDEND.
DoGAPFunc retorna valores. En Python OpenServer verificar si existe como metodo separado.

---

## 5. Problemas de Arquitectura del MCP Original

### 5.1 DoSlowCmd no existe en Python
El MCP genera DoSlowCmd() que no existe en `pip install openserver`. Solo DoCmd, DoSet, DoGet.

### 5.2 PROSPER Tubing Description - BLOCKER
PROSPER necesita una "tubing description" interna generada al hacer "Done" en Equipment Data GUI.
No hay comando OpenServer equivalente. Probamos 25+ variantes (CALCDESC, DONE, VALIDATE, etc.), ninguna funciona.
**Workaround**: Usar templates .Out pre-validados o GUI manual.

### 5.3 Arrays: ADD, no sobreescribir
Para agregar filas a DOWN/SURF/etc usar: `DoSet("PROSPER.SIN.EQP.DOWN.DATA.ADD", "")`
No se puede escribir directamente en un index que no existe (excepto Devn que auto-extends).

### 5.4 Paths con espacios
SAVEFILE/OPENFILE requieren comillas: `PROSPER.SAVEFILE("C:\path con espacios\file.Out")`

### 5.5 Licencias - DOS tipos de error distintos (VERIFICADO EN VIVO)
Max 1 PROSPER + 1 MBAL activo. Kill zombies antes de START. Esperar 3-5 seg despues de kill.

**Hay DOS errores de licencia distintos que el MCP debe distinguir:**

| Mensaje | Significado | Accion |
|---------|-------------|--------|
| "could not locate a free license" | La app (PROSPER/MBAL/GAP) no tiene licencia libre | Reintentar, otra app puede estar libre |
| "No OpenServer license available" | El pool de OpenServer (interfaz) esta agotado a nivel red | Ningun cliente puede conectar. Esperar/liberar sesiones |

El segundo es mas grave: significa que NINGUNA app puede usarse via OpenServer,
sin importar si PROSPER/MBAL/GAP tienen licencia de app. Es un limite del pool
de licencias OpenServer flotantes de la red.

**Observado**: las licencias fluctuan minuto a minuto. En una misma sesion vimos:
- PROSPER libre, MBAL+GAP ocupadas
- Las 3 ocupadas
- OpenServer completamente agotado (ni PROSPER conecta)

El MCP debe: (1) distinguir ambos errores, (2) reintentar con backoff,
(3) hacer fallback (ej: si MBAL no esta, seguir PROSPER->GAP sin tank),
(4) las tools que NO usan licencia (recomendaciones, lookup) siempre funcionan.

### 5.6 Conexion OpenServer persistente (bug corregido en MCP v2)
Cada tool NO debe crear su propia conexion OpenServer. Si prosper_open abre el
modelo y luego prosper_run_nodal crea una conexion nueva, PROSPER ya no tiene
el archivo abierto. Solucion: conexion OpenServer unica y persistente en el
server, que se cierra solo antes de kill_petex y se reconecta cuando hace falta.

---

## 6. Recomendaciones para el MCP v2

1. Corregir variables Geothermal: MD/TMP/HTC (no TVD/Temp/Uval)
2. Corregir IPR: WellLen (no HzLength), eliminar HzPermRatio y Temp
3. Eliminar PVT.Input.Salinity (no existe)
4. Eliminar ANL.SYS.Temp y NodePosition (no existen)
5. Agregar ANL.SYS.WC, GOR, PipeLabel
6. Usar DATA.ADD para crear filas en arrays
7. Setear MULT=1 en TODOS los registros de equipment
8. Reemplazar DoSlowCmd por DoCmd
9. Usar comillas en paths de SAVEFILE/OPENFILE
10. Usar MBAL.MB.VALIDATE para validar MBAL sin GUI
11. Usar DoGAPFunc (no DoCmd) para GAP NEWITEM/LINKITEMS/SOLVE
12. Implementar templates .Out pre-validados como workaround del blocker PROSPER
