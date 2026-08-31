"""Pluggable summarization backend.

Any OpenAI-compatible endpoint works: LM Studio's own server, Ollama, a local
llama.cpp server, OpenRouter, or a hosted provider. Configure with env vars:

    LONGHAUL_BASE_URL   default http://localhost:1234/v1   (LM Studio)
    LONGHAUL_MODEL      default auto-detected from /v1/models
    LONGHAUL_API_KEY    default "local"

Stdlib only - no requests, no openai package.
"""
from __future__ import annotations

import json
import os
import urllib.request

BASE_URL = os.environ.get("LONGHAUL_BASE_URL", "http://localhost:1234/v1").rstrip("/")
API_KEY = os.environ.get("LONGHAUL_API_KEY", "local")
MODEL = os.environ.get("LONGHAUL_MODEL", "")
TIMEOUT = int(os.environ.get("LONGHAUL_TIMEOUT", "900"))

# Some gateways sit behind bot protection that rejects urllib's default UA.
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "curl/8.9.1",
}

COMPACT_PROMPT = """You are compacting a conversation so it can continue in a
small context window. Rewrite the transcript into a dense STATE block that
preserves everything needed to keep working, and nothing else.

Output EXACTLY these sections, no preamble:

## STATE
One paragraph: what this conversation is about and where it stands.

## DECISIONS
Every decision made and constraint stated by the user. These are binding -
never drop one.

## ARTIFACTS
Files created or modified, exact paths, what each contains. Commands, versions,
and snippets that must survive verbatim.

## OPEN
What is unfinished, blocked, or awaiting the user.

## NEXT
The immediate next action.

Rules: preserve exact names, paths, numbers, versions. Drop pleasantries,
retries, and superseded attempts. Be terse. Under 500 words.

TRANSCRIPT:
"""


class SummarizerError(RuntimeError):
    pass


def _request(path: str, payload: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def detect_model() -> str:
    """Use the configured model, else the first one the endpoint reports."""
    if MODEL:
        return MODEL
    try:
        data = _request("/models").get("data") or []
        if data:
            return data[0].get("id", "")
    except Exception as e:  # noqa: BLE001
        raise SummarizerError(
            f"Cannot reach {BASE_URL}/models ({e}). Set LONGHAUL_BASE_URL to an "
            f"OpenAI-compatible endpoint.") from e
    raise SummarizerError(f"{BASE_URL} reported no models. Set LONGHAUL_MODEL.")


def summarize(transcript: str, max_tokens: int = 2500,
              prompt: str = COMPACT_PROMPT) -> str:
    """Stream a completion. Streaming matters: long inputs on slow local models
    otherwise die at proxy/idle timeouts partway through."""
    model = detect_model()
    payload = {
        "model": model,
        "stream": True,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt + transcript}],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(), headers=HEADERS)
    parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    ev = json.loads(chunk)
                except ValueError:
                    continue
                if ev.get("error"):
                    raise SummarizerError(str(ev["error"])[:300])
                for ch in ev.get("choices", []):
                    parts.append((ch.get("delta") or {}).get("content") or "")
    except SummarizerError:
        raise
    except Exception as e:  # noqa: BLE001
        if not parts:
            raise SummarizerError(f"Summarizer call failed: {e}") from e
    text = "".join(parts).strip()
    if not text:
        raise SummarizerError(
            "Summarizer returned nothing. The model may be reasoning-only or "
            "max_tokens too low.")
    return text
