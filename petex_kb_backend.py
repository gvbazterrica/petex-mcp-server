"""
PETEX Engineering KB Backend - Abstraccion
===========================================
Knowledge base de ingenieria (correlaciones, PVT, reglas) con backend
intercambiable, igual que el RAG:
  - LocalKBBackend    : JSON en knowledge_base/ (offline, versionado en git)
  - DynamoDBKBBackend : Amazon DynamoDB (compartido entre equipos, editable via API)

El orquestador y las tools llaman kb.get(category, key); no les importa el backend.

Config:
  PETEX_KB_BACKEND = "local" (default) | "dynamodb"
  PETEX_KB_TABLE = "petex-engineering-kb"  (si dynamodb)
  AWS_REGION = "us-east-1"

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Optional

BASE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE, "knowledge_base")


class KBBackend(ABC):
    @abstractmethod
    def get(self, category: str, key: str) -> Optional[dict]:
        """Devuelve la entrada de KB (ej: category='correlations', key='vaca_muerta')."""
        ...

    @abstractmethod
    def put(self, category: str, key: str, data: dict) -> bool:
        """Agrega/actualiza una entrada (para que UDS cargue datos reales)."""
        ...

    @abstractmethod
    def list_keys(self, category: str) -> list:
        ...


# ================================================================
# Backend LOCAL (JSON en knowledge_base/)
# ================================================================

class LocalKBBackend(KBBackend):
    def get(self, category, key):
        path = os.path.join(KB_DIR, category)
        if not os.path.isdir(path):
            return None
        for fname in os.listdir(path):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(path, fname), encoding="utf-8") as f:
                        data = json.load(f)
                    if key in data:
                        return data[key]
                except Exception:
                    continue
        return None

    def put(self, category, key, data):
        path = os.path.join(KB_DIR, category)
        os.makedirs(path, exist_ok=True)
        fpath = os.path.join(path, f"{category}_uds.json")
        existing = {}
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                existing = json.load(f)
        existing[key] = data
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        return True

    def list_keys(self, category):
        path = os.path.join(KB_DIR, category)
        keys = []
        if not os.path.isdir(path):
            return keys
        for fname in os.listdir(path):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(path, fname), encoding="utf-8") as f:
                        data = json.load(f)
                    keys.extend(k for k in data if not k.startswith("_"))
                except Exception:
                    continue
        return sorted(set(keys))


# ================================================================
# Backend DYNAMODB (compartido)
# ================================================================

class DynamoDBKBBackend(KBBackend):
    """DynamoDB. Clave primaria: category (PK) + key (SK). Valor: JSON en atributo 'data'."""

    def __init__(self, table_name=None, region=None):
        import boto3
        self.table_name = table_name or os.environ.get("PETEX_KB_TABLE", "petex-engineering-kb")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.table = boto3.resource("dynamodb", region_name=self.region).Table(self.table_name)

    def get(self, category, key):
        resp = self.table.get_item(Key={"category": category, "key": key})
        item = resp.get("Item")
        return json.loads(item["data"]) if item else None

    def put(self, category, key, data):
        self.table.put_item(Item={
            "category": category, "key": key, "data": json.dumps(data),
        })
        return True

    def list_keys(self, category):
        from boto3.dynamodb.conditions import Key as DKey
        resp = self.table.query(KeyConditionExpression=DKey("category").eq(category))
        return sorted(i["key"] for i in resp.get("Items", []))


# ================================================================
# Factory
# ================================================================

def get_kb_backend() -> KBBackend:
    backend = os.environ.get("PETEX_KB_BACKEND", "local").lower()
    if backend == "dynamodb":
        try:
            return DynamoDBKBBackend()
        except Exception as e:
            import logging
            logging.getLogger("petex").warning(f"KB DynamoDB no disponible ({e}), usando local")
    return LocalKBBackend()


if __name__ == "__main__":
    kb = get_kb_backend()
    print("Backend:", type(kb).__name__)
    print("\nCorrelaciones disponibles:", kb.list_keys("correlations"))
    print("PVT disponibles:", kb.list_keys("pvt"))
    print("\nVaca Muerta correlaciones:")
    vm = kb.get("correlations", "vaca_muerta")
    if vm:
        print("  VLP:", vm.get("vlp_tubing", {}).get("recommended"))
        print("  IPR oil:", vm.get("ipr_model", {}).get("oil", {}).get("recommended"))
