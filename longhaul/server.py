"""longhaul - MCP server that keeps local-model sessions alive indefinitely.

Tools:
  compact(conversation)  summarize the session, save it, return a STATE block
  recall(query)          search everything ever compacted or remembered
  remember(fact)         pin a fact permanently
  timeline()             what sessions exist and when they were last touched

Speaks MCP over stdio using only the standard library.
"""
from __future__ import annotations

import json
import os
import sys

try:  # installed as a package
    from longhaul.memory import Memory
    from longhaul.summarizer import SummarizerError, summarize
except ImportError:  # run directly from the repo
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from longhaul.memory import Memory
    from longhaul.summarizer import SummarizerError, summarize

SESSION = os.environ.get("LONGHAUL_SESSION", "default")
MEM = Memory(session=SESSION)


def log(msg: str) -> None:
    print(f"[longhaul] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- tools
def tool_compact(conversation: str) -> str:
    if len(conversation.strip()) < 200:
        return ("Nothing to compact yet. Pass the conversation so far as the "
                "`conversation` argument.")
    try:
        state = summarize(conversation)
    except SummarizerError as e:
        return (f"Compaction failed: {e}\n\n"
                f"The conversation was NOT saved. Fix the summarizer endpoint "
                f"and try again before the context fills.")
    prior = MEM.latest_compaction()
    MEM.add("compaction", state,
            {"chars_in": len(conversation),
             "supersedes": prior["ts"] if prior else None})
    return (state + "\n\n---\n_Saved to long-term memory. Continue from this "
            "block; earlier turns can be discarded. Use `recall` to retrieve "
            "anything older._")


def tool_recall(query: str, limit: int = 5) -> str:
    if not query.strip():
        last = MEM.latest_compaction()
        if not last:
            return "No memories yet. Nothing has been compacted or remembered."
        return f"Most recent compaction ({last['ts']}):\n\n{last['text']}"
    hits = MEM.search(query, limit=limit)
    if not hits:
        return (f"No memory matches '{query}'. Sessions on record: "
                + ", ".join(MEM.sessions() or ["none"]))
    out = [f"{len(hits)} memory match(es) for '{query}':"]
    for score, rec in hits:
        out.append(f"\n### {rec['ts']} — {rec['kind']} "
                   f"(session: {rec['session']}, relevance {score:.2f})\n"
                   f"{rec['text'][:2000]}")
    return "\n".join(out)


def tool_remember(fact: str) -> str:
    if not fact.strip():
        return "Nothing to remember - `fact` was empty."
    rec = MEM.add("fact", fact.strip())
    return f"Remembered permanently at {rec['ts']}. Retrieve it later with `recall`."


def tool_timeline() -> str:
    names = MEM.sessions()
    if not names:
        return "No sessions on record yet."
    lines = ["Sessions on record:"]
    for n in names:
        recs = Memory(MEM.home, n).all()
        comp = sum(1 for r in recs if r["kind"] == "compaction")
        facts = sum(1 for r in recs if r["kind"] == "fact")
        last = recs[-1]["ts"] if recs else "—"
        marker = "  <- current" if n == MEM.session else ""
        lines.append(f"  {n:<24} {comp} compaction(s), {facts} fact(s), "
                     f"last {last}{marker}")
    lines.append(f"\nStored under: {MEM.home}")
    return "\n".join(lines)


TOOLS = [
    {
        "name": "compact",
        "description": (
            "Compact the conversation when the context window is filling up "
            "(call around 70% full, before turns scroll away). Summarizes the "
            "session into a dense STATE block, saves it to permanent memory, "
            "and returns it. Continue from the returned block and treat "
            "earlier turns as discarded - nothing is lost, `recall` can "
            "retrieve it."),
        "inputSchema": {
            "type": "object",
            "properties": {"conversation": {
                "type": "string",
                "description": "The conversation so far, as text."}},
            "required": ["conversation"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Search everything ever compacted or remembered, across all past "
            "sessions. Use when the user refers to earlier work, asks what was "
            "decided, or mentions something not in the current window. Call "
            "with an empty query to get the most recent compaction."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Keywords, file path, or topic."},
                "limit": {"type": "integer",
                          "description": "Max results (default 5)."},
            },
        },
    },
    {
        "name": "remember",
        "description": (
            "Pin a fact to permanent memory immediately - a user preference, a "
            "decision, a path, a credential location. Survives every future "
            "compaction and session."),
        "inputSchema": {
            "type": "object",
            "properties": {"fact": {"type": "string",
                                    "description": "The fact to store."}},
            "required": ["fact"],
        },
    },
    {
        "name": "timeline",
        "description": "List all sessions on record with their memory counts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------- protocol
def reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


DISPATCH = {
    "compact": lambda a: tool_compact(a.get("conversation", "")),
    "recall": lambda a: tool_recall(a.get("query", ""), int(a.get("limit", 5))),
    "remember": lambda a: tool_remember(a.get("fact", "")),
    "timeline": lambda a: tool_timeline(),
}


def main() -> None:
    log(f"session={SESSION} memory={MEM.home}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            reply(mid, {"protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "longhaul", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(mid, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            log(f"call {name}")
            fn = DISPATCH.get(name)
            if fn is None:
                text = f"Unknown tool: {name}"
            else:
                try:
                    text = fn(args)
                except Exception as e:  # noqa: BLE001
                    text = f"Tool error: {e}"
            reply(mid, {"content": [{"type": "text", "text": text}]})
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif mid is not None:
            reply(mid, error={"code": -32601, "message": f"unknown: {method}"})


if __name__ == "__main__":
    main()
