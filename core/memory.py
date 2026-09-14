"""MemGPT-style tiers: core blocks (in context), recall log (chronological), archival (vectors)."""
import json, os, sqlite3, time
from core.bus import BUS

DEFAULT_CORE = {
    "persona": "I am JARVIS-6, a concise, local-only assistant running on the operator's laptop.",
    "user": "The operator is Kunal. Preferences unknown so far.",
}


class Memory:
    def __init__(self, cfg: dict):
        m = cfg["memory"]
        self.core_path = m["core_blocks_path"]
        self.top_k = m["archival_top_k"]
        os.makedirs(os.path.dirname(self.core_path) or ".", exist_ok=True)
        os.makedirs(m["db_path"], exist_ok=True)
        self.core = json.load(open(self.core_path)) if os.path.exists(self.core_path) else dict(DEFAULT_CORE)
        self.db = sqlite3.connect(m["recall_path"], check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS recall(ts REAL, role TEXT, text TEXT)")
        self.db.commit()
        try:
            import chromadb
            self.chroma = chromadb.PersistentClient(path=m["db_path"]).get_or_create_collection("archival")
        except Exception as e:  # archival is optional
            BUS.emit("mem", f"archival disabled: {e}")
            self.chroma = None

    # --- core memory (self-editable by the model) ---
    def core_memory_replace(self, block: str, value: str):
        self.core[block] = value
        self._save(); BUS.emit("mem", f"core_memory_replace({block})")
        return "ok"

    def core_memory_append(self, block: str, value: str):
        self.core[block] = (self.core.get(block, "") + " " + value).strip()
        self._save(); BUS.emit("mem", f"core_memory_append({block})")
        return "ok"

    def _save(self):
        json.dump(self.core, open(self.core_path, "w"), indent=2)

    def block_text(self) -> str:
        return "\n".join(f"<{k}>{v}</{k}>" for k, v in self.core.items())

    # --- recall ---
    def log(self, role: str, text: str):
        self.db.execute("INSERT INTO recall VALUES(?,?,?)", (time.time(), role, text))
        self.db.commit()

    def recall_memory_search(self, query: str, limit: int = 5):
        rows = self.db.execute(
            "SELECT role, text FROM recall WHERE text LIKE ? ORDER BY ts DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        BUS.emit("mem", f"recall_memory_search('{query}') → {len(rows)} hits")
        return [{"role": r, "text": t} for r, t in rows]

    # --- archival ---
    def archival_insert(self, text: str):
        if not self.chroma:
            return "archival unavailable"
        self.chroma.add(documents=[text], ids=[str(time.time_ns())])
        BUS.emit("mem", "archival_insert(1 chunk)")
        return "ok"

    def archival_search(self, query: str):
        if not self.chroma:
            return []
        res = self.chroma.query(query_texts=[query], n_results=self.top_k)
        docs = (res.get("documents") or [[]])[0]
        BUS.emit("mem", f"archival_search('{query}') → {len(docs)} chunks")
        return docs
