"""
PETEX RAG - Retrieval sobre documentacion tecnica
==================================================
Indexa los manuales PETEX (PROSPER, MBAL, GAP, OpenServer) + docs .md
y permite consultas semanticas para encontrar variables/comandos.

Enfoque: TF-IDF + similitud coseno (sklearn). Sin dependencias pesadas,
100% offline, sin descargar modelos. Ideal para documentacion tecnica
donde las queries comparten vocabulario con la doc.

Uso:
    from petex_rag import PetexRAG
    rag = PetexRAG()
    rag.build_index()          # una vez, persiste en disco
    rag.load_index()           # cargar el indice ya construido
    results = rag.query("geothermal temperature variable", top_k=3)

Autor: Gonzalo Vidal Bazterrica - UDS Pan Energy
"""

import os
import re
import pickle
from typing import List, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "petex_rag_index.pkl")

# Fuentes a indexar: (archivo, etiqueta, tipo)
SOURCES = [
    ("openserver.pdf", "OpenServer", "pdf"),
    ("prosper2.pdf", "PROSPER", "pdf"),
    ("GAP.pdf", "GAP", "pdf"),
    ("mbal.pdf", "MBAL", "pdf"),
    ("MCP_PETEX_Hallazgos.md", "Hallazgos", "md"),
    ("mcp_petex_variables.md", "Variables-PROSPER", "md"),
    ("mcp_petex_mbal_variables.md", "Variables-MBAL", "md"),
    ("mcp_petex_gap_variables.md", "Variables-GAP", "md"),
    ("mcp_petex_workflows.md", "Workflows", "md"),
]


class PetexRAG:
    def __init__(self, base_dir: str = BASE_DIR):
        self.base_dir = base_dir
        self.chunks: List[Dict] = []      # [{text, source, page}]
        self.vectorizer = None
        self.matrix = None

    # ---------- Indexado ----------

    def _extract_pdf_chunks(self, path: str, source: str) -> List[Dict]:
        """Extrae chunks de un PDF. Un chunk por pagina (con overlap opcional)."""
        from PyPDF2 import PdfReader
        chunks = []
        try:
            reader = PdfReader(path)
        except Exception as e:
            print(f"  [WARN] No se pudo leer {path}: {e}")
            return chunks
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
            except Exception:
                continue
            if not text or len(text.strip()) < 40:
                continue
            # Limpiar texto
            text = re.sub(r"\s+", " ", text).strip()
            chunks.append({"text": text[:3000], "source": source, "page": i + 1})
        return chunks

    def _extract_md_chunks(self, path: str, source: str) -> List[Dict]:
        """Extrae chunks de un .md por seccion (## headers)."""
        chunks = []
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  [WARN] No se pudo leer {path}: {e}")
            return chunks
        # Partir por headers de seccion
        sections = re.split(r"\n(?=#{1,3}\s)", content)
        for i, sec in enumerate(sections):
            sec = sec.strip()
            if len(sec) < 40:
                continue
            # Si la seccion es muy larga, partir en trozos
            if len(sec) > 2500:
                for j in range(0, len(sec), 2000):
                    chunks.append({"text": sec[j:j+2500], "source": source, "page": f"sec{i}.{j//2000}"})
            else:
                chunks.append({"text": sec, "source": source, "page": f"sec{i}"})
        return chunks

    def build_index(self, verbose: bool = True):
        """Indexa todas las fuentes y persiste en disco."""
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.chunks = []
        for fname, source, ftype in SOURCES:
            path = os.path.join(self.base_dir, fname)
            if not os.path.exists(path):
                if verbose:
                    print(f"  [SKIP] {fname} no existe")
                continue
            if verbose:
                print(f"  Indexando {fname} ({source})...")
            if ftype == "pdf":
                new_chunks = self._extract_pdf_chunks(path, source)
            else:
                new_chunks = self._extract_md_chunks(path, source)
            self.chunks.extend(new_chunks)
            if verbose:
                print(f"    -> {len(new_chunks)} chunks")

        if not self.chunks:
            raise RuntimeError("No se indexo ningun chunk. Verificar rutas.")

        # Vectorizar con TF-IDF
        texts = [c["text"] for c in self.chunks]
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),       # unigrams + bigrams (captura "GEO.DATA", "well type")
            max_features=50000,
            token_pattern=r"(?u)\b\w[\w\.\[\]]+\b",  # incluye puntos y corchetes (variables OpenServer)
        )
        self.matrix = self.vectorizer.fit_transform(texts)

        # Persistir
        with open(INDEX_PATH, "wb") as f:
            pickle.dump({
                "chunks": self.chunks,
                "vectorizer": self.vectorizer,
                "matrix": self.matrix,
            }, f)

        if verbose:
            print(f"\n  Indice construido: {len(self.chunks)} chunks, "
                  f"{self.matrix.shape[1]} features")
            print(f"  Guardado en: {INDEX_PATH}")

    # ---------- Query ----------

    def load_index(self) -> bool:
        """Carga el indice desde disco. Retorna True si existe."""
        if not os.path.exists(INDEX_PATH):
            return False
        with open(INDEX_PATH, "rb") as f:
            data = pickle.load(f)
        self.chunks = data["chunks"]
        self.vectorizer = data["vectorizer"]
        self.matrix = data["matrix"]
        return True

    def query(self, question: str, top_k: int = 3,
              source_filter: Optional[str] = None) -> List[Dict]:
        """Busca los chunks mas relevantes para la pregunta.

        Args:
            question: consulta en lenguaje natural o keywords
            top_k: cuantos resultados devolver
            source_filter: filtrar por fuente (ej "PROSPER", "GAP")
        """
        from sklearn.metrics.pairwise import cosine_similarity

        if self.matrix is None:
            if not self.load_index():
                raise RuntimeError("Indice no construido. Correr build_index() primero.")

        q_vec = self.vectorizer.transform([question])
        sims = cosine_similarity(q_vec, self.matrix)[0]

        # Ordenar por similitud
        ranked = sorted(range(len(sims)), key=lambda i: -sims[i])

        results = []
        for idx in ranked:
            if sims[idx] <= 0:
                break
            chunk = self.chunks[idx]
            if source_filter and source_filter.lower() not in chunk["source"].lower():
                continue
            results.append({
                "score": round(float(sims[idx]), 3),
                "source": chunk["source"],
                "page": chunk["page"],
                "text": chunk["text"],
            })
            if len(results) >= top_k:
                break
        return results

    def find_variable(self, description: str) -> Optional[str]:
        """Busca un nombre de variable OpenServer dada una descripcion.
        Extrae patrones tipo PROSPER.*/GAP.*/MBAL.* del mejor resultado."""
        results = self.query(description, top_k=2)
        for r in results:
            # Buscar variables OpenServer en el texto
            matches = re.findall(r"(?:PROSPER|GAP|MBAL)\.[\w\.\[\]{}]+", r["text"])
            if matches:
                # Devolver el mas frecuente / primero razonable
                for m in matches:
                    if len(m) > 12:
                        return m.rstrip(".")
        return None


if __name__ == "__main__":
    import sys
    rag = PetexRAG()

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        print("Construyendo indice RAG...")
        rag.build_index()
    else:
        # Modo query interactivo o test
        if not rag.load_index():
            print("Indice no existe. Corriendo build primero...")
            rag.build_index()
        query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "geothermal gradient temperature variable"
        print(f"\nQuery: {query}\n" + "=" * 50)
        for r in rag.query(query, top_k=3):
            print(f"\n[{r['source']} p{r['page']}] score={r['score']}")
            print(r["text"][:400])
