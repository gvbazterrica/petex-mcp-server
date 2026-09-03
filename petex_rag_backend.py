"""
PETEX RAG Backend - Abstraccion
================================
Interfaz comun para el RAG que permite intercambiar el backend sin tocar el MCP:
  - LocalRAGBackend  : TF-IDF + coseno (petex_rag.py), 100% offline
  - BedrockRAGBackend: AWS Bedrock Knowledge Base (S3 + OpenSearch Serverless)

El MCP siempre llama backend.query() / backend.find_variable(); no le importa
si atras hay ChromaDB local o Bedrock en la nube. La migracion a AWS es cambiar
una linea de config, no reescribir codigo.

Config via variable de entorno:
  PETEX_RAG_BACKEND = "local" (default) | "bedrock"
  PETEX_BEDROCK_KB_ID = "<knowledge-base-id>"  (si bedrock)
  AWS_REGION = "us-east-1"

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


# ================================================================
# Interfaz comun
# ================================================================

class RAGBackend(ABC):
    @abstractmethod
    def query(self, question: str, top_k: int = 3,
              source_filter: Optional[str] = None) -> List[Dict]:
        """Devuelve [{score, source, page, text}]."""
        ...

    @abstractmethod
    def find_variable(self, description: str) -> Optional[str]:
        """Devuelve el nombre de variable OpenServer mas probable, o None."""
        ...


# ================================================================
# Backend LOCAL (TF-IDF, offline)
# ================================================================

class LocalRAGBackend(RAGBackend):
    """Usa petex_rag.PetexRAG (TF-IDF + coseno sobre indice local)."""

    def __init__(self):
        from petex_rag import PetexRAG
        self._rag = PetexRAG()
        if not self._rag.load_index():
            raise RuntimeError("Indice local no existe. Correr: python petex_rag.py build")

    def query(self, question, top_k=3, source_filter=None):
        return self._rag.query(question, top_k=top_k, source_filter=source_filter)

    def find_variable(self, description):
        return self._rag.find_variable(description)


# ================================================================
# Backend AWS BEDROCK (Knowledge Base)
# ================================================================

class BedrockRAGBackend(RAGBackend):
    """Usa Amazon Bedrock Knowledge Base (Retrieve API).
    Los PDFs viven en S3, indexados en OpenSearch Serverless, embeddings Titan.
    Requiere: pip install boto3, y una KB creada (ver deployment guide)."""

    def __init__(self, kb_id: str = None, region: str = None):
        import boto3
        self.kb_id = kb_id or os.environ.get("PETEX_BEDROCK_KB_ID")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        if not self.kb_id:
            raise ValueError("Falta PETEX_BEDROCK_KB_ID")
        self.client = boto3.client("bedrock-agent-runtime", region_name=self.region)

    def query(self, question, top_k=3, source_filter=None):
        resp = self.client.retrieve(
            knowledgeBaseId=self.kb_id,
            retrievalQuery={"text": question},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": top_k}
            },
        )
        results = []
        for r in resp.get("retrievalResults", []):
            src = r.get("location", {}).get("s3Location", {}).get("uri", "?")
            # Filtro por fuente (nombre de archivo)
            if source_filter and source_filter.lower() not in src.lower():
                continue
            results.append({
                "score": round(r.get("score", 0), 3),
                "source": src.rsplit("/", 1)[-1],
                "page": "-",
                "text": r.get("content", {}).get("text", ""),
            })
        return results

    def find_variable(self, description):
        import re
        results = self.query(f"{description} OpenServer variable", top_k=2)
        for r in results:
            m = re.findall(r"(?:PROSPER|GAP|MBAL)\.[\w\.\[\]{}]+", r["text"])
            for v in m:
                if len(v) > 12:
                    return v.rstrip(".")
        return None


# ================================================================
# Factory
# ================================================================

def get_rag_backend() -> Optional[RAGBackend]:
    """Devuelve el backend segun config. None si no se puede cargar."""
    backend = os.environ.get("PETEX_RAG_BACKEND", "local").lower()
    try:
        if backend == "bedrock":
            return BedrockRAGBackend()
        return LocalRAGBackend()
    except Exception as e:
        import logging
        logging.getLogger("petex").warning(f"RAG backend '{backend}' no disponible: {e}")
        return None


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    print("Backend configurado:", os.environ.get("PETEX_RAG_BACKEND", "local"))
    b = get_rag_backend()
    if b:
        print("Backend cargado:", type(b).__name__)
        r = b.query("geothermal temperature variable", top_k=2)
        for x in r:
            print(f"  [{x['source']}] {x['score']} - {x['text'][:80]}")
    else:
        print("No se pudo cargar backend")
