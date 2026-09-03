# MCP PETEX v2 - Workflows Validados (Actualizado)

## PROSPER: Crear Pozo desde Cero

```
Paso  Accion                        Comando/Variable                          Nota
----  ----------------------------  ----------------------------------------  ----
1     Kill zombies                  taskkill /F /IM prosper.exe               Esperar 4 seg
2     Start                         PROSPER.START("")
3     New file                      PROSPER.NEWFILE()
4     System Summary                SIN.SUM.WellType = 0                     Producer
                                    SIN.SUM.Fluid = 0                        Oil (1=Gas)
                                    SIN.SUM.FlowType = 0                     Tubing
                                    SIN.SUM.InflowType = 0                   Single branch
                                    SIN.SUM.LiftMethod = 0                   None
                                    SIN.SUM.Completion = 0                   Cased hole (1=Open)
                                    SIN.SUM.PVTmodel = 0                     Black oil
                                    SIN.SUM.PREDICT = 1                      P&T Offshore
5     PVT                           PVT.Input.Api/GrvGas/SolGOR/Wgr/Tres
                                    PVT.Input.H2S/CO2/N2/PbCorr
                                    ** NO Salinity (no existe) **
6     Deviation Survey              Devn.Data[i].Md/Tvd                      Auto-extends
7     Geothermal                    GEO.DATA[i].MD (NO TVD!)
                                    GEO.DATA[i].TMP (NO Temp!)
                                    GEO.HTC (NO Uval!)
8     Downhole Equipment            DOWN.DATA.ADD (DoSet "")                  Para crear filas
                                    DOWN.DATA[i].TYPE/LABEL/DEPTH
                                    DOWN.DATA[i].TID/TIR/TOD/TOR/CID/CIR
                                    DOWN.DATA[i].MULT = 1                    SIEMPRE
9     Surface Equipment             SURF.HTC / SURF.TMP                      Globales primero
                                    SURF.DATA[i].TYPE = 1 (Pipe)
                                    SURF.DATA[i].LABEL/LENGTH/TVD/ID/ROUGH
                                    SURF.DATA[i].MULT = 1 / HTC
10    *** GUI DONE ***              NO HAY COMANDO OPENSERVER                BLOCKER
11    IPR                           IPR.Single.IprModel = "Vogel"
                                    IPR.Single.Pres/Skin/Thickness
                                    IPR.Single.WellLen (NO HzLength!)
                                    ** NO IPR.Single.Temp (no existe) **
12    Save                          PROSPER.SAVEFILE("path")                  Con comillas!
13    Shutdown                      PROSPER.SHUTDOWN()
```

**Workaround paso 10**: Usar template .Out pre-validado y solo modificar parametros.

## PROSPER: Nodal Analysis (sobre modelo existente)

```
1     Open file            PROSPER.OPENFILE("path.Out")
2     Set correlation      ANL.SYS.TubingLabel = "PetroleumExperts2"
3     Set WHP              ANL.SYS.Pres = 200
4     Set WC               ANL.SYS.WC = 0           (oil wells)
5     Set GOR              ANL.SYS.GOR = 800         (oil wells)
      Set WGR              ANL.SYS.WGR = X           (gas wells)
6     CALC                 ANL.SYS.CALC              (DoCmd)
7     Read results         OUT.SYS.Results[0].Sol.OilRate
                           OUT.SYS.Results[0].Sol.Pres
```

## PROSPER: VLP para GAP

```
1     Set sensitivities    ANL.VLP.Sens[0].Val[i] = WHP values
                           ANL.VLP.Sens[1].Val[i] = WC values
                           ANL.VLP.Sens[2].Val[i] = GOR values
2     CALC VLP             ANL.VLP.CALC               (DoCmd)
3     Export               ANL.VLP.EXPORT(0,"file.tpd")
```

## MBAL: Crear Reservorio (100% automatizable)

```
1     Kill + Start         MBAL.START("")
2     New model            MBAL.NEWMODEL()
3     Tank type            MB.TANK.TYPE = "OIL"       (OIL/GAS/CON/WAT)
4     PVT                  MB[0].PVT.INPUT.OILGRAV
                           MB[0].PVT.INPUT.GASGRAV
                           MB[0].PVT.INPUT.SOLGOR
                           MB[0].PVT.INPUT.WATSAL
                           MB[0].PVT.INPUT.CO2/N2/H2S
                           MB[0].PVT.INPUT.TRES
5     Pressure             MB.TANK.PRESS = Pi
6     OOIP                 MB[0].TANK[0].OOIP = 45   (MMstb, si aplica)
7     VALIDATE             MBAL.MB.VALIDATE           *** SIN GUI! ***
8     PVT Calc             MB.PVT.INPUT.CALCULATE
9     Save                 MBAL.SaveFile("path.mbi")
10    Shutdown             MBAL.SHUTDOWN()
```

## MBAL: Prediction Step-by-Step

```
1     Open                 MBAL.OPENFILE("path.mbi")
2     Config prediction    MB[0].PREDINP.CALCTYPE = "RES_PRESS"
                           MB[0].PREDINP.START = "ENDHIST"
                           MB[0].PREDINP.END = "USER"
                           MB[0].PREDINP.USEREND = fecha
                           MB[0].PREDINP.STEPTYPE = "AUTO"
3     Start pred           MBAL.MB.STARTPRED
4     Loop                 MBAL.MB.NEXTSTEPPRED
                           Check: MBAL.MB.PREDFINISHED
                           Read: MBAL.MB.CURRENTPREDTIME
                           (opcional: cambiar constraints entre steps)
5     End pred             MBAL.MB.ENDPRED
6     Read results         MB[0].TRES[{Prediction}][{Prediction}][i].TIME
                           MB[0].TRES[{Prediction}][{Prediction}][i].OILRATE
```

## MBAL: Import VLP de PROSPER

```
MBAL.MB.IMPORTTPD(MBAL.MB.PREDWELL[0], "C:\path\file.tpd")
```

## GAP: Crear Red (patron correcto de doc p64)

```
1     Kill + Start         GAP.START("")
2     New file             GAP.NEWFILE()               (DoGAPFunc o DoCmd)
3     System config        MOD[0].SYSTYPE = 0          (Production)
                           MOD[0].OPTMETHOD = 0        (Max Oil)
                           MOD[0].PVTMODEL = 0         (Black Oil)
4     Create well          NEWITEM("WELL", "W1", "RIGHT", NULL, MOD[0])
5     Create separator     NEWITEM("SEP", "SEP1", "RIGHT", NULL, MOD[0])
6     Create pipeline      NEWITEM("PIPE", "FL1", "RIGHT", MOD[0].EQUIP[{W1}], MOD[0])
7     Link well-pipe       LINKITEMS(MOD[0].EQUIP[{W1}], MOD[0].PIPE[{FL1}], "")
8     Link pipe-sep        LINKITEMS(MOD[0].PIPE[{FL1}], MOD[0].EQUIP[{SEP1}], "")
9     Well config          WELL[{W1}].WellType = "OilProducerNoLift"
                           WELL[{W1}].PROSPERFile = "path.Out"
10    Sep constraints      SEP[{SEP1}].MAXPRES = 200
                           SEP[{SEP1}].MAXQLIQ = 50000
11    Pipe config          PIPE[{FL1}].Length = 9843
                           PIPE[{FL1}].Diameter = 6
12    Create tank          NEWITEM("TANK", "T1", "RIGHT", NULL, MOD[0])
13    Tank config          TANK[{T1}].MBALFile = "path.mbi"
14    Link tank-well       LINKITEMS(MOD[0].TANK[{T1}], MOD[0].WELL[{W1}], "")
15    Save                 GAP.SAVEFILE("path.gap")
```

## GAP: Solve Red

```
1     Reset                GAP.RESETSOLVERINPUTS()
2     Solve                GAP.SOLVENETWORK(0, MOD[0], 0)
3     Results              SEP[{SEP1}].SolverResults[0].Qoil
                           SEP[{SEP1}].SolverResults[0].Qgas
                           SEP[{SEP1}].SolverResults[0].Qwat
```

## GAP: Prediction Step-by-Step

```
1     Config               PREDINFO.START.DATESTR = "01/01/2026"
                           PREDINFO.END.DATESTR = "01/01/2046"
                           PREDINFO.STEPUNIT = 2        (MONTHS)
2     Init                 NumSteps = GAP.PREDINIT()
3     Loop                 For i = 0 to NumSteps-1:
                               GAP.PREDDOSTEP()
                               (leer/modificar datos entre steps)
4     End                  GAP.PREDEND()
5     Results              WELL[{W1}].PREDRES[i].Qoil
                           WELL[{W1}].PREDRES[{01/01/2030}].Qoil
```

## Operaciones con Arrays (todos los programas)

```
Agregar fila:    DoSet("APP.PATH.DATA.ADD", "")
Insertar fila:   DoSet("APP.PATH.DATA[i].INSERT", "")
Eliminar fila:   DoSet("APP.PATH.DATA[i].DELETE", "")
Leer count:      DoGet("APP.PATH.DATA.COUNT")       <- READ-ONLY, no SET
Wildcard all:    DoGet("APP.PATH.DATA[$].FIELD")
Last item:       DoGet("APP.PATH.DATA[_].FIELD")
Label access:    DoGet("APP.PATH.DATA[{label}].FIELD")
```

## Manejo de Licencias

```
- Max 1 PROSPER + 1 MBAL (comparten licencia en IPM 13.5)
- GAP tiene licencia separada
- Secuencia: PROSPER -> SHUTDOWN -> MBAL -> SHUTDOWN -> GAP
- Kill zombies: taskkill /F /IM prosper.exe (+ mbal.exe, gap.exe)
- Esperar 3-5 seg despues de kill antes de START
- Si "license not found": verificar procesos, esperar, reintentar
```

## Python OpenServer - Metodos disponibles

```python
from openserver import OpenServer

with OpenServer() as c:
    c.DoCmd("APP.COMMAND")          # Ejecutar comando
    c.DoSet("APP.VARIABLE", "val")  # Setear variable
    val = c.DoGet("APP.VARIABLE")   # Leer variable

# NO EXISTE: c.DoSlowCmd()  (solo VBA/COM)
# NO EXISTE: c.DoGAPFunc()  (usar DoCmd para GAP tambien)
```
