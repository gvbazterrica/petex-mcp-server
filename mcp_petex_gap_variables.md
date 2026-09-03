# MCP PETEX v2 - Variables GAP Verificadas (manual + PROBADO EN VIVO)

## *** VERIFICADO EN VIVO 2026-08-27 (IPM 13.5) ***
Red creada, conectada, validada y guardada exitosamente. Hallazgos:
- **NEWITEM y LINKITEMS funcionan via DoCmd** (NO se necesita DoGAPFunc en Python)
- **WellType = "3"** (numero, NO el string "OilProducerNoLift")
- **WELL[{w}].File** para el path PROSPER (NO PROSPERFile)
- **PIPE usa tabla Desc[i]**: Desc[0].Length, Desc[0].ID, Desc[0].Roughness, Desc[0].TVD, Desc[0].Type
- **SEP[{s}].SolverPres[0]** para la presion (NO MAXPRES)
- **GAP.VALIDATE(0)** valida la red OK
- Para SOLVE: el well necesita VLP importado primero (TRANSFERPROSPERIPR + VLPIMPORT)
  sino da "No valid combination of separator, injection manifold, source or sink detected"

### Secuencia verificada que funciona:
```python
c.DoCmd('GAP.START("")')
c.DoCmd("GAP.NEWFILE()")
c.DoSet("GAP.MOD[0].SYSTYPE", "0")
c.DoSet("GAP.MOD[0].OPTMETHOD", "0")
c.DoSet("GAP.MOD[0].PVTMODEL", "0")
c.DoCmd('GAP.NEWITEM("WELL", "W1", "RIGHT", NULL, MOD[0])')
c.DoCmd('GAP.NEWITEM("SEP", "SEP1", "RIGHT", NULL, MOD[0])')
c.DoCmd('GAP.NEWITEM("PIPE", "FL1", "RIGHT", MOD[0].EQUIP[{W1}], MOD[0])')
c.DoCmd('GAP.LINKITEMS(MOD[0].EQUIP[{W1}], MOD[0].PIPE[{FL1}], "")')
c.DoCmd('GAP.LINKITEMS(MOD[0].PIPE[{FL1}], MOD[0].EQUIP[{SEP1}], "")')
c.DoSet("GAP.MOD[0].WELL[{W1}].WellType", "3")
c.DoSet("GAP.MOD[0].WELL[{W1}].File", "path.Out")
c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].Length", "9843")
c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].ID", "6")
c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].Roughness", "0.0006")
c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].TVD", "0")
c.DoSet("GAP.MOD[0].SEP[{SEP1}].SolverPres[0]", "200")
c.DoCmd("GAP.VALIDATE(0)")
c.DoCmd('GAP.SAVEFILE("path.gap")')
# Para solve necesita: TRANSFERPROSPERIPR + VLPIMPORT primero
```

---

# Referencia completa del manual (OpenServer pag 44-135)

## Comandos GAP
| Comando | Descripcion |
|---------|-------------|
| GAP.START("") | Iniciar GAP |
| GAP.SHUTDOWN() | Cerrar GAP |
| GAP.NEWFILE() | Nuevo modelo (via DoGAPFunc) |
| GAP.OPENFILE("path") | Abrir archivo (via DoGAPFunc) |
| GAP.SAVEFILE("path") | Guardar |
| GAP.SOLVENETWORK(opt, model, pot) | Resolver red |
| GAP.PREDINIT() | Iniciar prediccion (retorna num steps) |
| GAP.PREDDOSTEP(opt, pot) | Ejecutar un paso de prediccion |
| GAP.PREDEND() | Finalizar prediccion |
| GAP.PREDRESTART() | Restart prediccion |
| GAP.RESETSOLVERINPUTS() | Reset inputs del solver |
| GAP.PURGEALLRESULTS(model) | Purgar resultados |

### SOLVENETWORK argumentos
- opt: -1=usar settings del archivo, 0=sin optimizacion, 1=optimizar con constraints, 2=solo pot constraints
- model: MOD[0] (produccion), MOD[1] (water inj), etc.
- pot: 0=sin potencial, 1=con potencial

### Prediction step-by-step
```
NumSteps = DoGAPFunc("GAP.PREDINIT()")
For i = 0 To NumSteps - 1
    DoGAPFunc("GAP.PREDDOSTEP()")
    ' Leer/modificar datos entre steps
Next i
DoGAPFunc("GAP.PREDEND()")
```

## System Config (GAP.MOD[0].*)
| Campo | Variable | Valores |
|-------|----------|---------|
| System type | SYSTYPE | 0=Production, 1=WaterInj, 2=GasInj |
| Optimization | OPTMETHOD | 0=MaxOil, 1=MaxGas, 2=MaxRevenue |
| PVT model | PVTMODEL | 0=BlackOil, 1=Compositional |
| Prediction flag | PREDICTION | 0=off, 1=on |
| Prediction method | PREDMETHOD | 0=SolverOnly, 1=P&T |
| Network validation | EnableNetworkValidation | 0=off (faster), 1=on (default) |
| Use keywords | OpenServerUseKeywords | 0=numeric, 1=literal (default) |

## Prediction Config (GAP.MOD[0].PREDINFO.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Start date | START | Numeric (days from 01/01/1900) |
| Start date string | START.DATESTR | DD/MM/YYYY format |
| End date | END | Numeric |
| End date string | END.DATESTR | DD/MM/YYYY |
| Step unit | STEPUNIT | 0=DAYS, 1=WEEKS, 2=MONTHS, 3=YEARS |
| Optimize mode | PredictionOptimiseMode | OptOff, OptAllCnst, OptPotCnst, OptWithRules |

## Equipment Lists (GAP.MOD[0].*)
| Lista | Descripcion | Acceso |
|-------|-------------|--------|
| WELL[i] o WELL[{label}] | Pozos | Index numerico o label |
| PIPE[i] o PIPE[{label}] | Pipelines | |
| TANK[i] o TANK[{label}] | Tanks/reservorios | |
| SEP[i] o SEP[{label}] | Separadores | |
| PUMP[i] o PUMP[{label}] | Bombas | |
| COMP[i] o COMP[{label}] | Compresores | |
| JOINT[i] o JOINT[{label}] | Junctions | |
| EQUIP[i] o EQUIP[{label}] | Todos los equipos | |

## Well (GAP.MOD[0].WELL[{label}].*)
| Campo | Variable | Valores/Notas |
|-------|----------|---------------|
| Well type | WellType | OilProducerNoLift(3), OilProducerGL(1), OilProducerESP(2), GasProducer(4) |
| PROSPER file | PROSPERFile | Path al .Out |
| Mask flag | MASKFLAG | 0=activo, 1=masked |
| Label | Label | Nombre del well |
| Solver results | SolverResults[0].Qoil | STB/d |
| | SolverResults[0].Qgas | MSCF/d |
| | SolverResults[0].Qwat | STB/d |
| | SolverResults[0].WHP | Psi |
| | SolverResults[0].BHP | Psi |
| Prediction results | PREDRES[{date}].Qoil | Por fecha o index |

## Well Constraints (GAP.MOD[0].WELL[{label}].*)
| Campo | Variable |
|-------|----------|
| Max oil rate | MAXOILRATE |
| Max gas rate | MAXGASRATE |
| Max water rate | MAXWATRATE |
| Max liquid rate | MAXLIQRATE |
| Min WHP | MINWHP |
| Max WHP | MAXWHP |
| Min BHP | MINBHP |

## Pipe (GAP.MOD[0].PIPE[{label}].*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Length | Length | Ft |
| Diameter | Diameter | Inches |
| Roughness | Roughness | |
| Elevation | Elevation | Ft (delta height) |
| Surface temp | TMPSUR | Ambient temp |
| From label | FROMLABEL | Source node |
| To label | TOLABEL | Destination node |
| Correlation | CORRNAME | Flow correlation |
| Solver results | SolverResults[0].* | Same fields as well |

## Separator (GAP.MOD[0].SEP[{label}].*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Max liquid rate | MAXQLIQ | STB/d |
| Max oil rate | MAXQOIL | |
| Max gas rate | MAXQGAS | MSCF/d |
| Max water rate | MAXQWAT | |
| Max pressure | MAXPRES | Psi (separator pressure) |
| Min pressure | MINPRES | |
| Solver results | SolverResults[0].Qoil | Produccion total del separator |

## Tank (GAP.MOD[0].TANK[{label}].*)
| Campo | Variable | Notas |
|-------|----------|-------|
| MBAL file | MBALFile | Path al .mbi |
| Pressure | PRESS | Current pressure |
| Type | TYPE | Read-only |

## Conexiones
La forma de conectar elementos segun el manual:

```
' Crear elementos
DoGAPFunc("GAP.NEWITEM(""WELL"", ""W1"", ""RIGHT"", NULL, MOD[0])")
DoGAPFunc("GAP.NEWITEM(""SEP"", ""SEP1"", ""RIGHT"", NULL, MOD[0])")
DoGAPFunc("GAP.NEWITEM(""PIPE"", ""FL1"", ""RIGHT"", MOD[0].EQUIP[{W1}], MOD[0])")

' Conectar
DoGAPFunc("GAP.LINKITEMS(MOD[0].EQUIP[{W1}], MOD[0].PIPE[{FL1}], """")")
DoGAPFunc("GAP.LINKITEMS(MOD[0].PIPE[{FL1}], MOD[0].EQUIP[{SEP1}], """")")

' Tank
DoGAPFunc("GAP.NEWITEM(""TANK"", ""T1"", ""RIGHT"", NULL, MOD[0])")
DoGAPFunc("GAP.LINKITEMS(MOD[0].TANK[{T1}], MOD[0].WELL[{W1}], """")")
```

Alternativa simplificada (si funciona en la version):
```
DoSet("GAP.MOD[0].PIPE[{FL1}].FROMLABEL", "W1")
DoSet("GAP.MOD[0].PIPE[{FL1}].TOLABEL", "SEP1")
```

## Dato clave: DoGAPFunc vs DoCmd
En GAP muchos comandos usan **DoGAPFunc** en vez de DoCmd:
- NEWITEM, LINKITEMS, SOLVENETWORK, PREDINIT, PREDDOSTEP, PREDEND
- DoGAPFunc retorna un valor (ej: NumSteps de PREDINIT)
- En Python OpenServer, verificar si existe como metodo separado o es DoCmd
