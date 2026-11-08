# Ollama timeout fix — Rubik’s Cube Race

Your UI can display **0 moves** even while inference is running: moves only count after
Ollama returns a valid single-turn JSON answer. `ReadTimeout` means the Ollama
HTTP server did not return a complete response in time. It is **not** a C:/D:
file path issue.

## Before running

1. In PowerShell: `ollama list` and `ollama ps`. Verify that all four model tags
   **exactly match** the names in `.env` (for example `qwen3.5:2b` is not
   the same tag as `qwen3.5:latest`).
2. Leave the OpenRouter API key and hosted-model IDs untouched. Set
   `ALLOW_LIVE_API=0` to prevent accidental paid runs.
3. In the existing `.env` add or update:

```ini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_CLEF=clef-flash
OLLAMA_MODEL_QWEN=qwen3.5:2b
OLLAMA_MODEL_DEEPSEEK=deepseek-r1:1.5b
OLLAMA_MODEL_GEMMA=gemma3:1b
OLLAMA_REQUEST_TIMEOUT_S=300
OLLAMA_TIME_LIMIT_S=1200
OLLAMA_MAX_TOKENS=128
OLLAMA_DISABLE_THINKING=1
ALLOW_LIVE_API=0
```

The `OLLAMA_MODEL_*` values above are examples; **use tags from your `ollama list`**.
`OLLAMA_DISABLE_THINKING=1` reduces slow reasoning generation for local LLMs;
set it to `0` when you wish to measure the full reasoning setting (slower,
with potentially different answer quality). The assignment requires reporting
actual observed quality and latency, not estimating them.

4. Restart FastAPI after edits. Choose **Ollama**, **1 puzzle**, **Parallel off**.
   First check only **Gemma (local)**. Then try the other models individually.
5. To diagnose one model independent of the project, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_ollama.ps1 -Model gemma3:1b
```

This script only talks to `localhost:11434`; it does not use OpenRouter or
spend the teacher-provided key.

## How this patch behaves

* Defaults to sequential benchmarking, avoiding contention for local model RAM/VRAM.
* Uses a separate 300-second Ollama read timeout and 1200-second per-model
  trial time budget, **without modifying OpenRouter call caps or timeout**.
* Caps local chat responses to 128 output tokens, and disables local LLM
  thinking by default; this can be changed using `.env` variables above.
* Reports an actionable error if the local model times out or is not installed.

> This fixes preventable timeouts but cannot make hardware run a model that
> exceeds available memory. The 9B Clef Flash model can be particularly demanding.

Do not distribute `.env` or stored usage data. No key is included in this patch.
