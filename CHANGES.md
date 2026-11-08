# What's changed — assignment-safe version

**To replace your existing project**, use the **full updated ZIP**, and copy your private `.env` into the extracted folder. If you already have a `data/usage.sqlite3` counter file, KEEP that exact file and do not overwrite/delete it. Do not submit `.env` or `data/`.

## New files
- `backend/ledger.py` — persistent SQLite OpenRouter response cache, actual HTTP attempt log, and atomic 20/20/20/5 and 65 total request caps.
- `backend/ollama.py` — real local Clef Flash System One and Qwen/DeepSeek/Gemma chat adapters.
- `tests/conftest.py`, `tests/test_ledger.py`, `tests/test_ollama.py` — safe offline API/quota regression tests.

## Updated files
- `backend/config.py` — exact three-move suites, forced zero retries, safe mock defaults, strict `MAX_MOVES<=20`, per-provider settings.
- `backend/runner.py` — 3-move BFS verification, Claude <=5 turns, 20-turn decision model limit, per-turn cache/live metrics, no automatic key preflight request.
- `backend/adapters.py` — budget reservation before every real POST, persistent cache and attempt-cost logging.
- `backend/main.py` — opt-in live API gate, selectable hosted/local/mock backends, `/api/usage`, CSV fields.
- `backend/stats.py` — separate inference/cache latency, cost and call counts in summary; cached lookups excluded from inference-speed comparisons.
- `backend/verify_models.py` — no network or API key use by default.
- `frontend/index.html`, `frontend/app.js`, `frontend/style.css` — provider selector, 3-move protocol, usage budget bar, local-mode banner, explicit live-run confirmation, updated metrics/status.
- `.env.example`, `.gitignore`, `README.md` — teacher's rules, safe setup, persistent database kept out of Git.
- `tests/test_runner.py`, `tests/test_adapters.py`, `tests/test_api.py` — existing tests aligned to the stricter protocol.

No OpenRouter credentials, downloaded Ollama models, or live API results are included. No actual paid calls were made during preparation/testing.
