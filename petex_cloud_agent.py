"""
PETEX Cloud Agent (Bridge nube -> licencia local)
==================================================
El puente que hace posible: chatbot en la nube + licencias PETEX on-premise.

PROBLEMA: las licencias PETEX (OpenServer) viven en la maquina/servidor local.
La nube no puede "entrar" a esa red por seguridad. SOLUCION: este agente corre
LOCAL (donde estan las licencias) y hace POLLING a una cola en la nube. La nube
nunca inicia conexion hacia adentro; el agente local siempre es el que sale
(HTTPS saliente), lo que pasa cualquier firewall corporativo.

FLUJO:
  1. El chatbot (nube) pone un "trabajo" en la cola (SQS): {tool, args}
  2. Este agente (local) lee la cola cada N segundos
  3. Ejecuta la tool del MCP local contra PROSPER/MBAL/GAP
  4. Sube el resultado a la nube (S3/DynamoDB)
  5. El chatbot le muestra el resultado al usuario

SEGURIDAD:
  - NUNCA abre puertos entrantes. Solo salidas HTTPS a AWS.
  - Los modelos (.Out con data sensible) no salen de la red salvo que se configure.
  - Se autentica con credenciales IAM (rol de solo su cola).

Config (env vars):
  PETEX_QUEUE_URL    = URL de la cola SQS
  PETEX_RESULT_TABLE = tabla DynamoDB para resultados
  PETEX_AGENT_ID     = identificador de este agente (ej: "server-vm-01")
  AWS_REGION         = us-east-1
  PETEX_POLL_SECONDS = 5 (intervalo de polling)

Modo local/demo (sin AWS): usa una cola en archivo JSON para probar el flujo.

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import json
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("petex-agent")

AGENT_ID = os.environ.get("PETEX_AGENT_ID", "local-agent")
POLL_SECONDS = int(os.environ.get("PETEX_POLL_SECONDS", "5"))
BASE = os.path.dirname(os.path.abspath(__file__))

# Cola local para demo (cuando no hay AWS configurado)
LOCAL_QUEUE = os.path.join(BASE, "_local_queue.json")
LOCAL_RESULTS = os.path.join(BASE, "_local_results.json")


# ================================================================
# Ejecutor de tools: mapea {tool, args} a las funciones del MCP
# ================================================================

def execute_job(job: dict) -> dict:
    """Ejecuta un trabajo llamando a la tool correspondiente del MCP server.
    job = {"id": ..., "tool": "scan_model", "args": {...}}
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("srv", os.path.join(BASE, "petex_mcp_server.py"))
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    tool_name = job.get("tool")
    args = job.get("args", {})

    tool_fn = getattr(srv, tool_name, None)
    if not tool_fn:
        return {"error": f"Tool '{tool_name}' no existe en el MCP"}

    try:
        result = tool_fn(**args)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ================================================================
# Backend de cola: AWS SQS o local (demo)
# ================================================================

class QueueBackend:
    def poll(self) -> list:
        """Devuelve trabajos pendientes."""
        raise NotImplementedError

    def ack(self, job) -> None:
        """Marca un trabajo como procesado."""
        raise NotImplementedError

    def put_result(self, job_id, result) -> None:
        raise NotImplementedError


class LocalQueueBackend(QueueBackend):
    """Demo: cola en archivo JSON. Util para probar el flujo sin AWS."""

    def poll(self):
        if not os.path.exists(LOCAL_QUEUE):
            return []
        with open(LOCAL_QUEUE, encoding="utf-8") as f:
            jobs = json.load(f)
        return [j for j in jobs if j.get("status") == "pending"]

    def ack(self, job):
        jobs = []
        if os.path.exists(LOCAL_QUEUE):
            with open(LOCAL_QUEUE, encoding="utf-8") as f:
                jobs = json.load(f)
        for j in jobs:
            if j["id"] == job["id"]:
                j["status"] = "done"
        with open(LOCAL_QUEUE, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)

    def put_result(self, job_id, result):
        results = []
        if os.path.exists(LOCAL_RESULTS):
            with open(LOCAL_RESULTS, encoding="utf-8") as f:
                results = json.load(f)
        results.append({"job_id": job_id, "result": result,
                        "timestamp": datetime.now().isoformat(timespec="seconds")})
        with open(LOCAL_RESULTS, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)


class SQSQueueBackend(QueueBackend):
    """Produccion: AWS SQS + DynamoDB. El agente hace polling saliente HTTPS."""

    def __init__(self):
        import boto3
        self.queue_url = os.environ["PETEX_QUEUE_URL"]
        self.table_name = os.environ.get("PETEX_RESULT_TABLE", "petex-results")
        region = os.environ.get("AWS_REGION", "us-east-1")
        self.sqs = boto3.client("sqs", region_name=region)
        self.table = boto3.resource("dynamodb", region_name=region).Table(self.table_name)
        self._receipts = {}

    def poll(self):
        resp = self.sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=POLL_SECONDS,  # long polling
        )
        jobs = []
        for m in resp.get("Messages", []):
            job = json.loads(m["Body"])
            self._receipts[job["id"]] = m["ReceiptHandle"]
            jobs.append(job)
        return jobs

    def ack(self, job):
        rh = self._receipts.pop(job["id"], None)
        if rh:
            self.sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=rh)

    def put_result(self, job_id, result):
        self.table.put_item(Item={
            "job_id": job_id,
            "result": json.dumps(result),
            "agent": AGENT_ID,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })


def get_queue_backend() -> QueueBackend:
    if os.environ.get("PETEX_QUEUE_URL"):
        try:
            return SQSQueueBackend()
        except Exception as e:
            log.warning(f"SQS no disponible ({e}), usando cola local demo")
    return LocalQueueBackend()


# ================================================================
# Loop principal del agente
# ================================================================

def run_agent():
    queue = get_queue_backend()
    log.info(f"Agente '{AGENT_ID}' iniciado. Backend: {type(queue).__name__}")
    log.info(f"Polling cada {POLL_SECONDS}s. Ctrl+C para detener.")

    while True:
        try:
            jobs = queue.poll()
            for job in jobs:
                log.info(f"Trabajo recibido: {job['id']} -> {job.get('tool')}")
                result = execute_job(job)
                queue.put_result(job["id"], result)
                queue.ack(job)
                status = "OK" if result.get("ok") else "ERROR"
                log.info(f"Trabajo {job['id']} completado [{status}]")
            if not jobs:
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log.info("Agente detenido por el usuario")
            break
        except Exception as e:
            log.error(f"Error en el loop: {e}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_agent()
