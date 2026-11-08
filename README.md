# Rubik's Cube Race — safe OpenRouter + local Ollama benchmark

**November 8 assignment update:** See [ASSIGNMENT_FIXES.md](ASSIGNMENT_FIXES.md) for the neutral local prompt, state-seeded action ordering, winner-medal correction, and paired first-move A/B diagnostics. These improvements do not substitute solver moves in an independent benchmark. To use the new default behavior, add `OLLAMA_PROMPT_VARIANT=neutral` and `OLLAMA_ROTATE_ACTIONS=1` to `.env` and restart the backend.

FastAPI backend, JavaScript 3D interface, exact 3-turn scramble verification, and an independent-model benchmark. **The teacher's restricted OpenRouter key remains disabled by default.** Local Ollama requests go only to `http://localhost:11434` and never use that key.

## 2026-11-08 update: Clef Flash diagnosis and DeepSeek replacement

The **four local models** are now:

| UI competitor | Ollama tag | API |
| --- | --- | --- |
| Clef Flash (local) | `clef-flash` | `POST /v1/systemone` |
| Qwen (local) | `qwen3.5:2b` | `POST /api/chat` |
| Llama 3.2 (local) | `llama3.2:3b` | `POST /api/chat` |
| Gemma (local) | `gemma3:1b` | `POST /api/chat` |

DeepSeek was retired from the active competition. The unused `OLLAMA_MODEL_DEEPSEEK` line in an older `.env` is ignored; it cannot accidentally trigger a DeepSeek call. **Do not remove your other Ollama models or your saved experiment data.** The *hosted* comparison still lists Claude Opus, Jev, GPT-6 Luna Decisions and Cloudflare Clef exactly as before.

**Clef diagnosis:** saved runs in the uploaded archive show three independent 3-move Clef solves, followed by one failed run at a different seed that timed out after seven moves. This is not evidence that the Ollama endpoint stopped working. On the failed seed (`734383`, scramble `D' L2 D'`), the old optional sticker-count heuristic scored `D2` higher than the correct first move `D`, although `D2` did not reduce the cube's shortest distance. We changed the default observation to **exclude that potentially misleading heuristic** while keeping 54 facelets, readable six-face grids, move rules, recent history and repeat-state feedback. The observation is also more compact.

You can opt back into the old heuristic for a *separately labeled experiment* by setting `OLLAMA_STICKER_HINTS=1` in `.env`; **default is `0`**. Do not blend results from different prompt configurations without disclosure.

All four local models receive equivalent state and move instructions. In normal mode their moves are **never overridden**. The optional solver-guided demonstration is explicitly labeled and excluded from independent-model success statistics.

### Run from Windows (project on C:, model weights on D:)

1. Ensure Ollama is installed and running. The Ollama environment variable `OLLAMA_MODELS=D:\OllamaModels` controls storage; the Python project uses the localhost API and does not need the D: path.
2. Download the replacement model:

   ```powershell
   ollama pull llama3.2:3b
   ollama list
   ```

   See [Ollama Llama 3.2](https://ollama.com/library/llama3.2). The 3B default takes about 2.0 GB on disk. Older `deepseek-r1` weights can remain downloaded; the application won't select them.
3. Open `.env` at the project root; add or change these lines:

   ```ini
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL_CLEF=clef-flash
   OLLAMA_MODEL_QWEN=qwen3.5:2b
   OLLAMA_MODEL_LLAMA=llama3.2:3b
   OLLAMA_MODEL_GEMMA=gemma3:1b
   OLLAMA_STICKER_HINTS=0
   OLLAMA_DISABLE_THINKING=1
   ALLOW_LIVE_API=0
   ```

   Your old `OLLAMA_MODEL_DEEPSEEK` variable is unused. Do not paste your OpenRouter key into example files, screenshots or uploaded ZIPs.
4. Before starting a 20-move run, verify all installed tags and request/response formats:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.local_preflight --model llama_local --timeout 240
   .\.venv\Scripts\python.exe -m scripts.local_preflight --model clef_local --timeout 240
   ```

   This performs **one actual local decision per model** on the same verified 3-move-away cube, without OpenRouter calls, and reports move validity, response time, output diagnostics and whether the proposed move reduces the exact shortest distance. It does not claim the model will solve an entire puzzle.
5. Restart the FastAPI server:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
   ```

   Open `http://localhost:8000`, hard-refresh with **Ctrl+Shift+R**, select **Ollama**, **1 puzzle**, **Parallel off**, **solver guidance off**. You should see Clef Flash, Qwen, Llama 3.2 and Gemma.

### Reproducible Clef comparisons

For the saved Clef success seed:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_preflight --model clef_local --seed 383828 --timeout 240
```

For the recorded difficult seed:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_preflight --model clef_local --seed 734383 --timeout 240
```

This allows a controlled one-decision comparison. If the first move is bad, it can still be a genuine model error: **no prompt update guarantees that a 9B decision model will solve every Rubik's Cube**. Clef's previous saved solves cannot establish success on different seeds. To compare old vs new prompts fairly, reuse the same seed and report the prompt variant.

For low-memory systems, use `ollama ps` to inspect CPU/GPU model loading. Clef Flash 9B may take minutes per move. The default Ollama per-request timeout and trial clock are independent of the hosted API policy and can be set using `OLLAMA_REQUEST_TIMEOUT_S` and `OLLAMA_TIME_LIMIT_S`.

### Teacher's restrictions (hosted OpenRouter only)

- Exactly three moves as the **verified shortest** starting distance.
- Stop after 20 turns per decision model and at most five Claude calls.
- Persistent SQLite response cache and request reservations survive restarts; global cap 65 hosted requests, maximum 20 for each decision model, five for Claude.
- Identical cube state and move instructions within each provider's comparison.
- Record solve status, move count, latency, optimality gap, API attempts, cache hits, and API-reported cost where available.
- If the teacher's key is invalid/revoked, do not try hosted experiments. Local Ollama runs consume no hosted API allowance.

See source `backend/config.py`, `backend/ledger.py`, `backend/runner.py`, `backend/ollama.py`. Normal independent benchmarking never calls `backend/guidance.py`. Local distance diagnostics run *after* a move is chosen; shortest paths are never supplied to unassisted models.

### Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Offline tests run with fake local HTTP responses and the actual cube engine, so they **do not prove how the models on your D: drive will behave**. The authoring environment cannot access your installed Ollama models. Run `scripts.local_preflight` locally to confirm the replacement model and Clef on real weights.

### Security and saved state

Keep `.env`, `data/usage.sqlite3`, and `results/` from your existing installation. `.env.example` contains no key. **Never overwrite or delete the SQLite counter** if you use the teacher's restricted key. Published source ZIPs omit `.env`, virtual environments, caches, and saved results. If you shared a key in an earlier project archive, request key rotation from the owner.
