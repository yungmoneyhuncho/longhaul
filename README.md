# longhaul

Use a local model the way you'd use ChatGPT or Claude. Just keep talking. It
handles the context so you don't have to think about it, and it remembers
across sessions.

An MCP server, zero dependencies (stdlib Python), works with LM Studio, Ollama,
llama.cpp, or any OpenAI-compatible endpoint. MIT.

The thing that makes hosted assistants feel effortless isn't the model, it's
everything around it. You never watch a token counter, never start a fresh chat
because the old one filled up, never re-explain what you're building. Run a
model locally and all of that becomes your job again. longhaul gives that part
back.

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

## "My model does 64K, I don't need this"

A bigger window buys you a longer sitting. It doesn't change the part that
actually annoys you, which is that managing context is still your job.

You still watch the counter. You still decide when to start over. You still
paste the same background into a fresh chat because the old one filled up. And
when you close the app, 64K of it goes away regardless.

If you're happy doing that, fair enough, this isn't for you. If you'd rather
just talk to the thing, that's what it's for.

One technical note while you're here: allocated context isn't usable context.
KV cache is reserved up front, prefill cost climbs as the window fills, and
recall from the middle of a long context is measurably worse than from the ends.
Running near the top of a 64K window is slower and dumber than running in the
first half of it.

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
  If you use LM Studio specifically, its plugin system does have such a hook
  (`predictionLoopHandler`), and `alexandreaxell/context-compactor` on the LM
  Studio Hub compacts automatically inside the chat window. longhaul's value
  there is the permanent, searchable memory across sessions, not the trigger.
- Compaction is lossy on purpose. Detail outside the block leaves the window.
  `recall` gets it back from disk, but the model has to think to ask.
- Keyword search misses paraphrases that share no words with the original.
- Summary quality is whatever your summarizer model's quality is.

## License

MIT
