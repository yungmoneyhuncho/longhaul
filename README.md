# longhaul

**Your local model forgets everything when you close the app.** longhaul is an
MCP server that gives it persistent memory across sessions, plus context
compaction so long sessions don't hit the wall.

Reopen tomorrow, next week, or next month and the model still knows what you
decided, which files you touched, and what was left unfinished.

> **Does this matter if my model has a 64K window?** Less, for compaction — and
> that is an honest answer. But window size does not survive a restart, and 64K
> allocated is not 64K useful: KV cache is reserved up front, prefill cost grows
> with fill, and recall from the middle of a long context degrades. longhaul is
> aimed at persistence first, compaction second.

- **Zero dependencies.** Python 3.9+ standard library only.
- **Works with any OpenAI-compatible endpoint** — LM Studio, Ollama,
  llama.cpp server, OpenRouter, or a hosted API.
- **Your data stays yours.** Memory is plain JSONL and Markdown on your disk.
- MIT licensed.

## The problem

Two separate problems, and most tools only address the first.

**Within a session:** a full window leaves two bad options — stop, or roll the
window and silently discard what you decided an hour ago.

**Between sessions:** nothing survives. Close LM Studio and the entire
conversation is gone, however large the window was. Every new session starts
from zero.

## How it differs from the usual "AI memory" project

Most are RAG over chat history: embed every message, auto-inject the top-k
similar chunks into each turn. That fills your window with fuzzy fragments you
did not ask for, and relevance is a similarity score.

longhaul inverts that:

| | typical RAG memory | longhaul |
|---|---|---|
| What is stored | raw message embeddings | a fixed schema written at compaction time |
| What enters context | auto-injected top-k chunks | nothing, unless the model calls `recall` |
| Retrieval | vector similarity | keyword overlap over plain JSONL |
| Dependencies | embedding model, vector DB | none — stdlib only |
| Summarizer | usually the local model | any endpoint, including a much larger one |

The schema is the point. `DECISIONS` are treated as binding and never dropped;
`ARTIFACTS` keeps exact paths and versions verbatim. A similarity score cannot
promise either.

## How it works

```
  conversation fills up  ──►  compact()  ──►  STATE block replaces the transcript
                                  │
                                  └──►  saved forever to ~/.longhaul
                                              │
  "what did we decide about auth?"  ──►  recall()  ──►  pulled back from disk
```

Compaction produces a structured block, not a vague summary:

```markdown
## STATE      what this is about, where it stands
## DECISIONS  every constraint the user set — binding, never dropped
## ARTIFACTS  exact file paths, versions, commands
## OPEN       unfinished or blocked
## NEXT       the immediate next action
```

Older turns leave the model's window, but never leave your disk. `recall`
searches every compaction and pinned fact across every session you have ever
run.

## Tools

| Tool | What it does |
|---|---|
| `compact(conversation)` | Summarize, save permanently, return a STATE block |
| `recall(query)` | Search all past sessions for anything ever saved |
| `remember(fact)` | Pin a fact forever (preferences, paths, decisions) |
| `timeline()` | List sessions and their memory counts |

## Install

```bash
git clone https://github.com/yungmoneyhuncho/longhaul.git
cd longhaul
```

No `pip install` required — it runs on the standard library.

### LM Studio

Add to `~/.lmstudio/mcp.json`:

```json
{
  "mcpServers": {
    "longhaul": {
      "command": "python",
      "args": ["/absolute/path/to/longhaul/longhaul/server.py"],
      "env": {
        "LONGHAUL_BASE_URL": "http://localhost:1234/v1",
        "LONGHAUL_SESSION": "main"
      }
    }
  }
}
```

Restart LM Studio and enable **longhaul** under Integrations. Then paste
[examples/system-prompt.md](examples/system-prompt.md) into your System Prompt
so the model calls `compact` on its own.

### Claude Desktop, Cursor, or any MCP client

Same block, in that client's MCP config. See [examples/](examples/).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LONGHAUL_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible endpoint used to summarize |
| `LONGHAUL_MODEL` | first model the endpoint reports | Model that does the summarizing |
| `LONGHAUL_API_KEY` | `local` | Sent as a bearer token |
| `LONGHAUL_SESSION` | `default` | Name this session; separate memory per name |
| `LONGHAUL_HOME` | `~/.longhaul` | Where memory is stored |
| `LONGHAUL_TIMEOUT` | `900` | Seconds to wait for a summary |

### Use a bigger model to do the summarizing

The summarizer does not have to be the model you are chatting with, and this is
the trick that makes small models viable. Point `LONGHAUL_BASE_URL` at a
large-context endpoint and your 4B gets compactions written by a model that read
the whole transcript at once:

```json
"env": {
  "LONGHAUL_BASE_URL": "https://your-gateway/v1",
  "LONGHAUL_MODEL": "some-long-context-model",
  "LONGHAUL_API_KEY": "sk-..."
}
```

Self-summarizing also works — just point it at your own local server.

## Memory format

```
~/.longhaul/sessions/<name>/
├── memory.jsonl    append-only records, one JSON object per line
└── MEMORY.md       the same content, readable and greppable
```

Nothing is ever deleted or rewritten. Delete a session by deleting its folder.

Search is token overlap — no embeddings, no vector database, no network call.
It is fast, dependency-free, and good enough for finding "what did we decide
about the database" in a year of sessions.

## Limits, honestly

- The model must **call** `compact`. Small models sometimes need the system
  prompt to be blunt about it; the bundled prompt is written that way.
- Compaction is lossy by design. Detail outside the STATE block leaves the
  window — `recall` gets it back from disk, but the model has to think to ask.
- Keyword search will miss a paraphrase that shares no words with the original.
- Summary quality is the summarizer model's quality. A weak summarizer makes
  weak compactions.

## License

MIT
