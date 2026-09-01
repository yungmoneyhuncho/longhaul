# longhaul

Persistent memory for local LLMs, as an MCP server. Your model keeps what it
learned after you close the app, and long sessions stop hitting the wall.

Zero dependencies (stdlib Python), works with LM Studio, Ollama, llama.cpp, or
any OpenAI-compatible endpoint. MIT.

## What it actually does

Four tools over MCP:

`compact(conversation)` takes the transcript, sends it to whatever endpoint you
configured, and gets back a fixed block:

```
## STATE      what this is about and where it stands
## DECISIONS  constraints the user set (treated as binding, never dropped)
## ARTIFACTS  file paths, versions, commands, kept verbatim
## OPEN       unfinished or blocked
## NEXT       the immediate next action
```

That block gets appended to `~/.longhaul/sessions/<name>/memory.jsonl` (plus a
markdown copy you can read) and handed back to the model, which continues from
it instead of the raw history.

`recall(query)` searches every record ever written, across all sessions.
`remember(fact)` pins something permanently. `timeline()` lists your sessions.

No embeddings, no vector database, no background process.

## Why not just use a bigger context window

If your model does 64K and your work fits in one sitting, compaction won't do
much for you. That's a real answer, not a dodge.

The window doesn't survive a restart though. Close the app and it's all gone,
whatever size it was. That's the part longhaul is for. Compaction is the
secondary benefit, mostly useful on 8K-32K setups or very long sessions.

Worth knowing too: allocated context isn't the same as usable context. KV cache
gets reserved up front, prefill cost climbs as the window fills, and recall from
the middle of a long context is measurably worse than from the ends.

## How it differs from other "AI memory" projects

Most of them do RAG over your chat history: embed every message, then
auto-inject the top-k similar chunks into each turn. Your window fills with
fuzzy fragments you didn't ask for, and relevance is whatever the similarity
score says.

This works the other way around:

| | typical RAG memory | longhaul |
|---|---|---|
| stored | message embeddings | fixed schema, written at compaction time |
| enters context | auto-injected each turn | only when the model calls `recall` |
| retrieval | vector similarity | keyword overlap over plain JSONL |
| deps | embedding model + vector DB | none |
| summarizer | usually the local model | any endpoint, including a bigger one |

The schema does real work here. DECISIONS are never dropped and ARTIFACTS keeps
paths and versions exactly as written. A similarity score can't guarantee either.

## Install

```bash
git clone https://github.com/yungmoneyhuncho/longhaul.git
```

That's it, there's nothing to pip install.

### LM Studio

In `~/.lmstudio/mcp.json`:

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

Restart LM Studio, enable longhaul under Integrations, and paste
[examples/system-prompt.md](examples/system-prompt.md) into your system prompt
so the model knows to call the tools on its own.

Same config shape works for Claude Desktop, Cursor, or any MCP client, just in
that client's config file.

## Config

| Variable | Default | What it does |
|---|---|---|
| `LONGHAUL_BASE_URL` | `http://localhost:1234/v1` | endpoint that writes the summaries |
| `LONGHAUL_MODEL` | first model the endpoint reports | which model summarizes |
| `LONGHAUL_API_KEY` | `local` | bearer token |
| `LONGHAUL_SESSION` | `default` | session name, separate memory per name |
| `LONGHAUL_HOME` | `~/.longhaul` | where memory lives |
| `LONGHAUL_TIMEOUT` | `900` | seconds to wait for a summary |

### Summarizing with a different model

The model writing your summaries doesn't have to be the one you're chatting
with. Point `LONGHAUL_BASE_URL` somewhere with a big context window and your 4B
gets compactions written by a model that read the whole transcript in one go:

```json
"env": {
  "LONGHAUL_BASE_URL": "https://your-endpoint/v1",
  "LONGHAUL_MODEL": "some-long-context-model",
  "LONGHAUL_API_KEY": "sk-..."
}
```

Pointing it at your own local server works fine too.

## Where your data goes

```
~/.longhaul/sessions/<name>/
├── memory.jsonl    one JSON object per line, append only
└── MEMORY.md       same thing, readable and greppable
```

Nothing is deleted or rewritten. Delete a session by deleting the folder. The
only thing that leaves your machine is the transcript going to whichever
summarizer endpoint you configured, so if that's localhost, nothing leaves.

Search is keyword overlap. Worse than embeddings at catching a paraphrase, fine
for finding "what did we decide about the database" in a year of sessions, and
it means there's nothing to install or corrupt.

## Known limits

- The model has to call `compact`. MCP has no hook that fires on its own, so
  this depends on the system prompt. Small models sometimes need it stated
  bluntly. Keep your client's rolling-window setting on as a backstop.
- Compaction is lossy on purpose. Detail outside the block leaves the window.
  `recall` gets it back from disk, but the model has to think to ask.
- Keyword search misses paraphrases that share no words with the original.
- Summary quality is whatever your summarizer model's quality is.

## License

MIT
