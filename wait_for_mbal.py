"""
Espera hasta que MBAL tenga licencia libre, chequeando cada 10 min.
Cuando se libera, corre el modelo integrado completo automaticamente.

Uso: python wait_for_mbal.py
Dejar corriendo en una terminal. Ctrl+C para cancelar.
"""
import os
import time
import subprocess
from datetime import datetime
from openserver import OpenServer

base = r"C:\Users\xgvb02\Desktop\Ds\MCP\test dario petex"
prosper_file = os.path.join(base, "APO-135(h).Out")
mbal_file = os.path.join(base, "APO135_MBAL.mbi")
gap_file = os.path.join(base, "APO135_GAP.gap")

CHECK_INTERVAL = 600  # 10 minutos en segundos


def kill_all():
    for app in ["prosper", "mbal", "gap"]:
        subprocess.run(["taskkill", "/F", "/IM", f"{app}.exe"],
                       capture_output=True, timeout=10)
    time.sleep(3)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def check_mbal_license():
    """Retorna True si MBAL tiene licencia libre."""
    kill_all()
    try:
        with OpenServer() as c:
            c.DoCmd('MBAL.START("")')
            c.DoCmd("MBAL.SHUTDOWN()")
        return True
    except Exception as e:
        if "license" in str(e).lower():
            return False
        # Otro error - reportar pero tratar como no disponible
        log(f"  Error inesperado: {e}")
        return False


def build_mbal():
    """Crear el modelo MBAL."""
    log("Creando MBAL...")
    kill_all()
    with OpenServer() as c:
        c.DoCmd('MBAL.START("")')
        c.DoCmd("MBAL.NEWMODEL()")
        c.DoSet("MBAL.MB.TANK.TYPE", "OIL")
        c.DoSet("MBAL.MB[0].PVT.INPUT.OILGRAV", "55")
        c.DoSet("MBAL.MB[0].PVT.INPUT.GASGRAV", "0.568")
        c.DoSet("MBAL.MB[0].PVT.INPUT.SOLGOR", "0")
        c.DoSet("MBAL.MB[0].PVT.INPUT.CO2", "0.44")
        c.DoSet("MBAL.MB[0].PVT.INPUT.N2", "0.24")
        c.DoSet("MBAL.MB.TANK.PRESS", "7441")
        c.DoSet("MBAL.MB[0].PVT.INPUT.TRES", "219")
        c.DoCmd("MBAL.MB.VALIDATE")
        c.DoCmd(f'MBAL.SaveFile("{mbal_file}")')
        c.DoCmd("MBAL.SHUTDOWN()")
    log(f"  MBAL guardado: {mbal_file}")


def build_gap():
    """Crear la red GAP con well + separator + pipeline + tank."""
    log("Creando GAP...")
    kill_all()
    with OpenServer() as c:
        c.DoCmd('GAP.START("")')
        c.DoCmd("GAP.NEWFILE()")
        c.DoSet("GAP.MOD[0].SYSTYPE", "0")
        c.DoSet("GAP.MOD[0].OPTMETHOD", "0")
        c.DoSet("GAP.MOD[0].PVTMODEL", "0")

        c.DoCmd('GAP.NEWITEM("WELL", "APO135", "RIGHT", NULL, MOD[0])')
        c.DoCmd('GAP.NEWITEM("SEP", "SEP1", "RIGHT", NULL, MOD[0])')
        c.DoCmd('GAP.NEWITEM("PIPE", "FL1", "RIGHT", MOD[0].EQUIP[{APO135}], MOD[0])')
        c.DoCmd('GAP.LINKITEMS(MOD[0].EQUIP[{APO135}], MOD[0].PIPE[{FL1}], "")')
        c.DoCmd('GAP.LINKITEMS(MOD[0].PIPE[{FL1}], MOD[0].EQUIP[{SEP1}], "")')

        c.DoSet("GAP.MOD[0].WELL[{APO135}].WellType", "3")
        c.DoSet("GAP.MOD[0].WELL[{APO135}].File", prosper_file)

        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].Length", "9843")
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].ID", "6")
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].Roughness", "0.0006")
        c.DoSet("GAP.MOD[0].PIPE[{FL1}].Desc[0].TVD", "0")

        c.DoSet("GAP.MOD[0].SEP[{SEP1}].SolverPres[0]", "200")

        # Tank MBAL
        c.DoCmd('GAP.NEWITEM("TANK", "TANK1", "RIGHT", NULL, MOD[0])')
        c.DoSet("GAP.MOD[0].TANK[{TANK1}].MBALFile", mbal_file)
        c.DoCmd('GAP.LINKITEMS(MOD[0].TANK[{TANK1}], MOD[0].WELL[{APO135}], "")')

        # Transferir IPR de PROSPER
        try:
            c.DoCmd('GAP.TRANSFERPROSPERIPR(MOD[0].WELL[{APO135}],0,0)')
            log("  IPR transferido de PROSPER")
        except Exception as e:
            log(f"  TRANSFERPROSPERIPR: {e}")

        c.DoCmd("GAP.VALIDATE(0)")
        c.DoCmd(f'GAP.SAVEFILE("{gap_file}")')

        # Solve
        log("  Resolviendo red...")
        try:
            c.DoCmd("GAP.RESETSOLVERINPUTS()")
            c.DoCmd("GAP.SOLVENETWORK(0, MOD[0], 0)")
            oil = c.DoGet("GAP.MOD[0].SEP[{SEP1}].SolverResults[0].Qoil")
            gas = c.DoGet("GAP.MOD[0].SEP[{SEP1}].SolverResults[0].Qgas")
            log(f"  RESULTADO: Oil={oil} STB/d, Gas={gas} MSCF/d")
        except Exception as e:
            log(f"  Solve: {e}")

        c.DoCmd(f'GAP.SAVEFILE("{gap_file}")')
        c.DoCmd("GAP.SHUTDOWN()")
    log(f"  GAP guardado: {gap_file}")


def main():
    log("=" * 50)
    log("Esperando licencia de MBAL (chequeo cada 10 min)")
    log("=" * 50)

    attempt = 0
    while True:
        attempt += 1
        log(f"Intento {attempt}: verificando licencia MBAL...")
        if check_mbal_license():
            log(">>> LICENCIA MBAL DISPONIBLE! Ejecutando modelo completo <<<")
            try:
                build_mbal()
                build_gap()
                log("=" * 50)
                log("MODELO COMPLETO EXITOSO")
                log(f"  PROSPER: {prosper_file}")
                log(f"  MBAL:    {mbal_file}")
                log(f"  GAP:     {gap_file}")
                log("=" * 50)
            except Exception as e:
                log(f"ERROR durante ejecucion: {e}")
            break
        else:
            log(f"  MBAL ocupada. Reintentando en 10 min...")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Cancelado por el usuario")
