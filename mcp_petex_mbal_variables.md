# MCP PETEX v2 - Variables MBAL Verificadas (OpenServer manual pag 156-210)

## Comandos MBAL
| Comando | Descripcion |
|---------|-------------|
| MBAL.START("") | Iniciar MBAL |
| MBAL.SHUTDOWN() | Cerrar MBAL |
| MBAL.NEWMODEL() | Nuevo modelo |
| MBAL.OPENFILE("path") | Abrir archivo |
| MBAL.SaveFile("path") | Guardar archivo |
| MBAL.MB.VALIDATE | **Validar todos los objetos** (equivalente al Done de PROSPER) |
| MBAL.MB.RunSimulation | Correr history match simulation |
| MBAL.MB.LINKITEMS(obj1, obj2) | Vincular objetos (tank-well, tank-tank) |
| MBAL.MB.BREAKLINK(obj1, obj2) | Desvincular objetos |
| MBAL.MB.PVT.INPUT.CALCULATE | Calcular propiedades PVT |
| MBAL.MB.PVT.INPUT.MATCHCURRENT | Match PVT correlacion actual |
| MBAL.MB.PVT.INPUT.MATCHALL | Match todas las correlaciones PVT |
| MBAL.MB.ALLOCTANKPRESSRATE(tank) | Calcular presion y rate del tank desde wells |
| MBAL.MB.REGRESSTANKHIST(tank) | Regresion history match |
| MBAL.MB.IMPORTTPD(well, "file.tpd") | Importar VLP de PROSPER |
| MBAL.MB.STARTPRED | Iniciar prediccion step-by-step |
| MBAL.MB.NEXTSTEPPRED | Siguiente paso de prediccion |
| MBAL.MB.ENDPRED | Finalizar prediccion |
| MBAL.MB.PREDFINISHED | Flag: prediccion terminada (0/1) |
| MBAL.MB.CURRENTPREDTIME | Tiempo actual de prediccion |
| MBAL.MB.CALCWELLS | Calcular performance de wells en paso actual |

## Tank Data (MBAL.MB[0].TANK[i].* o MBAL.MB[0].TANK[{label}].*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Type | TYPE | OIL, GAS, CON, WAT |
| OOIP | OOIP | MMstb |
| OGIP | OGIP | Bscf |
| Porosity | POR | Fraccion |
| Connate water | CONWAT | Fraccion |
| Pressure | PRESS | Psi |
| Temperature | TEMP | |
| Rock compressibility | ROCKCOMP | |
| Water compressibility | WATCOMP | |
| Permeability | PERM | |
| Drainage radius | DRAINRAD | |
| Pay zone | PAYZONE | Ft |
| Initial GOR | INITGOR | |
| Initial CGR | INITCGR | |
| Production used GOR | PRODUSEGOR | |

## Tank Production History (MBAL.MB[0].TANK[{label}].PRODHIST[i].*)
| Campo | Variable |
|-------|----------|
| Time | TIME |
| Pressure | PRESS |
| Cum oil | CUMOIL |
| Cum gas | CUMGAS |
| Cum water | CUMWAT |
| Cum gas inj | CUMGASINJ |
| Cum water inj | CUMWATINJ |
| Record on/off | RECOFF | 0=enabled, 1=disabled |

## PVT Input (MBAL.MB[0].PVT.INPUT.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Oil gravity | OILGRAV | API |
| Gas gravity | GASGRAV | |
| Solution GOR | SOLGOR | |
| Water salinity | WATSAL | ppm |
| H2S | H2S | Mole % |
| CO2 | CO2 | Mole % |
| N2 | N2 | Mole % |
| Temperature | TRES | Fahrenheit |
| Bubble point | PBUB | Psi |

## Aquifer (MBAL.MB[0].TANK[{label}].AQUIFER.*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Model | MODEL | NONE, FETKOVICH, CARTER_TRACY, POT, HURST_VAN |
| Encroachment angle | ENCRANG | Grados |
| Outer radius | RADIUS | |
| Thickness | THICK | |
| Permeability | PERM | |
| Porosity | POR | |
| Total compressibility | TOTCOMP | |
| Initial pressure | INITPRESS | |

## Prediction Setup (MBAL.MB[0].PREDINP.*)
| Campo | Variable | Valores |
|-------|----------|---------|
| Calc type | CALCTYPE | RES_PRESS, MANPRESS, PROD, DCQ |
| Start type | START | STARTPROD, ENDHIST, USER |
| User start | USERSTART | Fecha o numero |
| End type | END | AUTO, ENDHIST, USER |
| User end | USEREND | |
| Step type | STEPTYPE | AUTO, USER |
| User step | USERSTEP | |
| Water injection | WATINJ | YES, NO |
| Gas injection | GASINJ | YES, NO |
| Use rel perm | RELPERM | YES, NO |

## Prediction Wells (MBAL.MB[0].PREDWELL[i].*)
| Campo | Variable | Notas |
|-------|----------|-------|
| Name | NAME | |
| Type | TYPE | ANY, CONPROD, ESPPROD, GASCAP, GASINJ, GASLIFT, GASPROD, OILPROD, WATINJ, WATPROD |
| Disabled | DISABLED | 0=enabled, 1=disabled |

## Prediction Results (MBAL.MB[0].TRES[{stream}][{well}][i].*)
| Campo | Variable |
|-------|----------|
| Time | TIME |
| Oil rate | OILRATE |
| Gas rate | GASRATE |
| Water rate | WATRATE |
| Pressure | PRESS |
| Count | COUNT |

## Dato clave: MBAL.MB.VALIDATE
A diferencia de PROSPER (que no tiene un comando equivalente al "Done"),
**MBAL SI tiene VALIDATE** que valida todos los objetos sin necesidad de GUI.
Esto significa que para MBAL, el workflow via OpenServer es 100% automatizable.
