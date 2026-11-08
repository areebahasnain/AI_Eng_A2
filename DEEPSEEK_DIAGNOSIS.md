# DeepSeek-R1 1.5B — Diagnosis and Repair (2026-11-08)

## Confirmed from the supplied project data

The newest saved DeepSeek trial in `results/run-20261107-144949-bea8.json`
reported `ERROR`, `moves_used=0`, `turns=3`, `invalid_outputs=6`, and
`local_requests=6`. Its recovery attempts returned `done_reason=length`,
`eval_count=768`, approximately 2,300–2,700 characters of thinking, and an
empty final answer. This is why the cube never moved.

## Root-cause and scope

The previous local adapter set `format=json`, which can be challenging for a
small distilled reasoning model, then retried with `think=true` and 768 tokens.
Those tokens went to reasoning instead of a completed move. No network error or
invalid cube starting distance was involved in that last run.

Only the local DeepSeek adapter is changed:

1. Compact equivalent six-face cube observation with orientation, all legal
   moves, recent moves, anti-cycle feedback and the one-step sticker heuristic.
2. No forced JSON `format`. Accept a single legal final move in plain notation
   or exact `{"move":"..."}` JSON, never content from an unfinished think block.
3. First local `/api/chat` with `think=false`, no schema. If invalid or empty,
   exactly one local `/api/generate` attempt with more tokens, `think=false`.
4. Return a genuine error after both fail; do not substitute a solver move.
   Every local request, failure and latency is logged.

The hosted OpenRouter integration, quota ledger, solver-guided optional mode,
and the other three Ollama adapters are unchanged. The inference format change
means you should disclose model-specific prompting in benchmark methodology.

## On Windows, in your C: project

```powershell
cd 'C:\Users\HUAWEI\Downloads\rubiks-cube-race'
ollama list
.\.venv\Scripts\python.exe -m scripts.deepseek_smoke
.\.venv\Scripts\python.exe -m scripts.diagnose_local_models --model deepseek_local
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Both diagnostics use local Ollama only; they cannot spend your teacher's key.
If DeepSeek still returns no visible content on your own machine, the issue
could be the installed Ollama/model behavior rather than the Python parser.
Provide diagnostic counts/status only—do not disclose the key or raw thinking.

## Verification

114 offline tests passed with `pytest -q`, including simulated HTTP responses
for the empty-thinking failure, response parsing, bounded recovery and no
fabricated moves. **Live inference of your locally installed model has not been
run in this environment.**
