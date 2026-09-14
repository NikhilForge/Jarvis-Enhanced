"""Local document RAG: index the operator's folders so Jarvis can answer from files.

CPU-only embeddings (all-MiniLM-L6-v2, ~90 MB RAM) so the 6 GB card stays free
for Whisper + Llama. Chunks land in the same Chroma store as archival memory.
"""
import hashlib, os, time
from typing import List

from core.bus import BUS

TEXT_EXT = {".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml", ".log", ".ts", ".tsx"}


def _chunks(text: str, size: int = 900, overlap: int = 120) -> List[str]:
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


class DocRAG:
    def __init__(self, cfg: dict):
        r = cfg.get("rag", {})
        self.roots = r.get("roots", [])
        self.top_k = r.get("top_k", 5)
        self.max_mb = r.get("max_file_mb", 2)
        self.col = None
        self.embed = None
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            self.col = chromadb.PersistentClient(
                path=cfg["memory"]["db_path"]).get_or_create_collection("documents")
            self.embed = SentenceTransformer(r.get("embed_model", "all-MiniLM-L6-v2"), device="cpu")
        except Exception as e:
            BUS.emit("rag", f"document RAG disabled: {e}")

    def available(self) -> bool:
        return self.col is not None and self.embed is not None

    def index(self, roots: List[str] | None = None) -> int:
        if not self.available():
            return 0
        n, t0 = 0, time.time()
        for root in (roots or self.roots):
            root = os.path.expandvars(os.path.expanduser(root))
            for dirpath, _dirs, files in os.walk(root):
                if any(p in dirpath for p in (".git", "node_modules", "__pycache__", "venv")):
                    continue
                for f in files:
                    p = os.path.join(dirpath, f)
                    if os.path.splitext(f)[1].lower() not in TEXT_EXT:
                        continue
                    try:
                        if os.path.getsize(p) > self.max_mb * 1024 * 1024:
                            continue
                        text = open(p, encoding="utf-8", errors="ignore").read()
                    except OSError:
                        continue
                    for i, ch in enumerate(_chunks(text)):
                        cid = hashlib.sha1(f"{p}:{i}".encode()).hexdigest()
                        self.col.upsert(ids=[cid],
                                        documents=[ch],
                                        embeddings=[self.embed.encode(ch).tolist()],
                                        metadatas=[{"path": p, "chunk": i}])
                        n += 1
        BUS.emit("rag", f"indexed {n} chunks in {time.time() - t0:.1f}s")
        return n

    def search(self, query: str, k: int | None = None):
        if not self.available():
            return []
        res = self.col.query(query_embeddings=[self.embed.encode(query).tolist()],
                             n_results=k or self.top_k)
        hits = [{"text": d, "path": m.get("path", "?")}
                for d, m in zip(res["documents"][0], res["metadatas"][0])]
        BUS.emit("rag", f"doc_search('{query[:32]}') → {len(hits)} chunks")
        return hits
