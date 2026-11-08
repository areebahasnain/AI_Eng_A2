# Local Ollama diagnosis (November 2026)

The November 8 screenshot shows **two independent failure classes**:

- DeepSeek R1 1.5B: `InvalidOutput`, 0 moves. Model responses may contain no final `message.content`, especially with thinking-only completions, or output that isn't a single legal move.
- Gemma 3 1B: about 19 minutes into a trial with 0 moves. This requires distinguishing loading, contention, CPU inference, read timeout, and output parsing. The screenshot alone cannot establish which applies.

## Changes in this patch

1. DeepSeek's bounded fallback uses **`/api/chat` + native JSON-schema string enum of the 18 legal moves**, instead of `/api/generate` with `think:false`. Some Ollama releases have been reported to emit raw reasoning text on the latter route.
2. Both DeepSeek requests have `think:false`, capped output, no unbounded retry, and retain model-chosen moves only. They never copy from `message.thinking`, guess a move, or call the reference solver to decide an action.
3. Local API runs are forced to **serial mode at the backend**. Running multiple models in parallel on limited RAM/VRAM can cause queuing and heavy model swapping. This does **not** change the teacher's OpenRouter settings.
4. The browser no longer truncates the entire error message to 38 characters; you can hover it to see the complete diagnostic.
5. `python -m scripts.ollama_probe --model deepseek_local --full` makes one simple local request and one full cube decision, printing only model-generated response snippets and nonsecret statistics. Run it with `--model gemma_local` to isolate Gemma.

## Apply without deleting your `.env` or saved usage history

Extract the patch ZIP **inside** `C:\Users\HUAWEI\Downloads\rubiks-cube-race`.

Stop all active benchmarks and the FastAPI process, then in the project `.env` set for a short diagnostic:

```ini
OLLAMA_MODEL_DEEPSEEK=deepseek-r1:1.5b
OLLAMA_MODEL_GEMMA=gemma3:1b
OLLAMA_REQUEST_TIMEOUT_S=60
OLLAMA_TIME_LIMIT_S=300
ALLOW_LIVE_API=0
```

Check exact installed tags with `ollama list`. Use a fresh PowerShell terminal:

```powershell
ollama ps
.\.venv\Scripts\python.exe -m scripts.ollama_probe --model deepseek_local --timeout 60 --full
.\.venv\Scripts\python.exe -m scripts.ollama_probe --model gemma_local --timeout 60
```

If the **simple** prompt fails, the issue is below the benchmark layer: Ollama version, model installation, memory, server or compatibility. If it succeeds and the full cube prompt fails, investigate prompt length, `done_reason` (especially `length`), `eval_count`, and parsing.

Start with only one selected model and one puzzle; the patch forces local runs to be serial even when a stale frontend requests parallel. The model must still independently generate a legal move and solve the cube. A valid move is not proof that it can solve a 3-move cube.

## Offline verification limitations

Automated tests mock Ollama HTTP; they cannot establish that your local GPU/CPU will generate the same responses. The first **live** local model test must be performed on your computer. Do not share the project's `.env` or a ZIP containing it.
