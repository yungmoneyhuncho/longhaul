"""Persistent memory store. Append-only JSONL plus a human-readable mirror.

Nothing is ever deleted or overwritten - a compaction that scrolls out of the
model's window still exists on disk and is searchable forever.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

DEFAULT_HOME = Path(os.environ.get(
    "LONGHAUL_HOME", Path.home() / ".longhaul"))

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "have", "has",
    "was", "were", "are", "you", "your", "our", "not", "but", "all", "can",
    "will", "how", "what", "when", "where", "which", "who", "why", "its",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_.\-/]{3,}", text.lower())
            if w not in _STOP}


class Memory:
    def __init__(self, home: Path | None = None, session: str = "default"):
        self.home = Path(home or DEFAULT_HOME)
        self.session = re.sub(r"[^A-Za-z0-9_.-]", "_", session) or "default"
        self.dir = self.home / "sessions" / self.session
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.dir / "memory.jsonl"
        self.md = self.dir / "MEMORY.md"

    # ---------- write ----------
    def add(self, kind: str, text: str, meta: dict | None = None) -> dict:
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "epoch": int(time.time()),
            "kind": kind,               # compaction | fact | note
            "session": self.session,
            "text": text,
            "meta": meta or {},
        }
        with self.jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with self.md.open("a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n## {rec['ts']} — {kind}\n\n{text}\n")
        return rec

    # ---------- read ----------
    def all(self, limit: int | None = None) -> list[dict]:
        if not self.jsonl.exists():
            return []
        out = []
        with self.jsonl.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out[-limit:] if limit else out

    def sessions(self) -> list[str]:
        root = self.home / "sessions"
        if not root.is_dir():
            return []
        return sorted(p.name for p in root.iterdir() if p.is_dir())

    def all_sessions_records(self) -> list[dict]:
        recs: list[dict] = []
        for name in self.sessions():
            recs.extend(Memory(self.home, name).all())
        return recs

    def search(self, query: str, limit: int = 5,
               across_sessions: bool = True) -> list[tuple[float, dict]]:
        """Token-overlap search. No embeddings, no dependencies, no network."""
        q = _tokens(query)
        if not q:
            return []
        pool = self.all_sessions_records() if across_sessions else self.all()
        scored: list[tuple[float, dict]] = []
        for rec in pool:
            t = _tokens(rec.get("text", ""))
            if not t:
                continue
            overlap = len(q & t)
            if not overlap:
                continue
            # favour matches that cover more of the query, mild recency nudge
            score = overlap / len(q) + 0.15 * (overlap / (len(t) ** 0.5 + 1))
            scored.append((score, rec))
        scored.sort(key=lambda x: (-x[0], -x[1].get("epoch", 0)))
        return scored[:limit]

    def latest_compaction(self) -> dict | None:
        for rec in reversed(self.all()):
            if rec.get("kind") == "compaction":
                return rec
        return None
