# MCP PETEX v2 - Variables Verificadas IPM 13.5
**Referencia rapida para hardcodear en el Knowledge Base del MCP**

## PVT (PROSPER.PVT.Input.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| API Gravity | Api | |
| Gas Gravity | GrvGas | |
| Solution GOR | SolGOR | |
| Water Gravity | Wgr | |
| Reservoir Temp | Tres | Fahrenheit |
| H2S | H2S | Mole % |
| CO2 | CO2 | Mole % |
| N2 | N2 | Mole % |
| Pb Correlation | PbCorr | 0=Glaso, 1=Standing |
| Salinidad | **NO EXISTE** | |

## Geothermal (PROSPER.SIN.EQP.GEO.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Depth | DATA[i].MD | Measured Depth, NO TVD |
| Temperature | DATA[i].TMP | NO Temp |
| U value global | HTC | NO Uval |
| U value per point | DATA[i].HTC | Opcional |
| Count | DATA.COUNT | READ-ONLY |

## Deviation (PROSPER.SIN.EQP.Devn.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| MD | Data[i].Md | Auto-extends |
| TVD | Data[i].Tvd | Auto-extends |
| Count | DATA.COUNT | READ-ONLY |
| Filter | PROSPER.EQP.DEV.FIL.FILTER | DoCmd |
| Transfer | PROSPER.EQP.DEV.FIL.TRANS | DoCmd |
| Raw MD | RawMSD[i] | Hasta 1000 pts |
| Raw TVD | RawTVD[i] | Hasta 1000 pts |

## Downhole Equipment (PROSPER.SIN.EQP.DOWN.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Count | DATA.COUNT | READ-ONLY |
| **Add row** | **DATA.ADD** | DoSet con "" |
| Insert row | DATA[i].INSERT | DoSet con "" |
| Delete row | DATA[i].DELETE | DoSet con "" |
| Type | DATA[i].TYPE | 0=Tubing, 1=XmasTree |
| Depth | DATA[i].DEPTH | Measured Depth ft |
| Tubing ID | DATA[i].TID | Inches, OBLIGATORIO |
| Tubing roughness | DATA[i].TIR | OBLIGATORIO |
| Tubing OD | DATA[i].TOD | Inches, OBLIGATORIO |
| Tubing OD rough | DATA[i].TOR | OBLIGATORIO |
| Casing ID | DATA[i].CID | Inches, OBLIGATORIO |
| Casing roughness | DATA[i].CIR | OBLIGATORIO |
| Casing OD | DATA[i].COD | |
| Casing OD rough | DATA[i].COR | |
| Rate Multiplier | DATA[i].MULT | OBLIGATORIO siempre |

**CRITICO**: TODOS los campos deben setearse. Si falta alguno, CALC falla.

## Surface Equipment (PROSPER.SIN.EQP.SURF.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Global HTC | HTC | |
| Ambient Temp | TMP | |
| Count | DATA.COUNT | READ-ONLY |
| Type | DATA[i].TYPE | 0=None, 1=Pipe, 2=Choke, 3=Fittings |
| Label | DATA[i].LABEL | |
| Length | DATA[i].LENGTH | Ft |
| TVD | DATA[i].TVD | |
| Pipe ID | DATA[i].ID | Inches |
| Roughness | DATA[i].ROUGH | |
| Multiplier | DATA[i].MULT | |
| HTC per item | DATA[i].HTC | |

## IPR Single Branch (PROSPER.SIN.IPR.Single.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Model | IprModel | "Vogel", "Darcy", "C and n" |
| Pressure | Pres | Psi |
| Skin | Skin | |
| Thickness | Thickness | Ft |
| Well Length | WellLen | Ft (NO HzLength) |
| Drainage | Drainage | |
| Wellbore Radius | WBR | |
| Water Cut | WC | |
| CGR | CGR | Gas wells |
| Test Rate | Qtest | |
| AOF | AOF | Read after calc |
| HzPermRatio | **NO EXISTE** | |
| IPR Temp | **NO EXISTE** | Usa PVT.Input.Tres |

## System Analysis (PROSPER.ANL.SYS.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| First Node Pres | Pres | WHP en psi |
| Tubing corr | TubingLabel | "PetroleumExperts2" |
| Pipeline corr | PipeLabel | |
| Water Cut | WC | |
| Total GOR | GOR | Oil wells |
| WGR | WGR | Gas wells |
| CGR | CGR | Gas wells |
| CALC | CALC | DoCmd |
| Done flag | DONE | Read-only |

## System Summary (PROSPER.SIN.SUM.*)
| Campo | Variable | Valores |
|-------|----------|---------|
| Well Type | WellType | 0=Producer, 1=Injector, 2=WaterInj |
| Fluid | Fluid | 0=Oil, 1=Gas |
| Flow Type | FlowType | 0=Tubing, 1=Annular, 2=Both |
| Inflow | InflowType | 0=Single, 1=Multilateral |
| Lift | LiftMethod | 0=None, 1=GL, 2=ESP, 3=HSP, 4=PCP |
| Completion | Completion | 0=CasedHole, 1=OpenHole |
| PVT | PVTmodel | 0=BlackOil, 1=EOS |
| Predict | PREDICT | 0=PressOnly, 1=P&T Offshore, 2=P&T OnLand |
| Temp Model | TEMPMODEL | 0=RoughApprox, 1=EnthalpyBal, 2=ImprovedApprox |

## Comandos Generales
| Accion | Comando | Notas |
|--------|---------|-------|
| Start | PROSPER.START("") | |
| Shutdown | PROSPER.SHUTDOWN() | Sin parentesis tambien |
| New file | PROSPER.NEWFILE() | |
| Open file | PROSPER.OPENFILE("path") | Comillas obligatorias |
| Save file | PROSPER.SAVEFILE("path") | Comillas obligatorias |
| Units off | PROSPER.DOUNITCONV = 0 | Usa field units |

## Errores Conocidos
| Error | Causa | Solucion |
|-------|-------|----------|
| Variable name was not found | Nombre incorrecto | Consultar RAG |
| SURFACE EQUIPMENT or TUBING description | Falta validacion interna | GUI Done requerido |
| Invalid TUBING ANNULUS details | Equipment incompleto | Completar DOWN data |
| Program start command has failed | App ya abierta | Kill process primero |
| Licensing not found | Licencia ocupada | Cerrar otras instancias |
| DoSlowCmd not found | Python OS no tiene DoSlowCmd | Usar DoCmd |
