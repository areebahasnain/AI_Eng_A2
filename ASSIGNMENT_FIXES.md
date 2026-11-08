# Assignment fixes and validation (November 8, 2026)

## What was wrong

The cube itself was not broken: `backend/runner.py` verifies **exactly three** as the starting shortest distance. Historical real Ollama runs showed that Clef sometimes solved the cube, but Qwen and Gemma frequently repeated the same face turns, and DeepSeek R1 returned empty output (already replaced by Llama 3.2 in the latest user ZIP).

Small local language models often choose a syntactically legal move without reliably planning the entire 3-turn sequence. No instruction can guarantee these weights will solve the cube. A 20-move upper bound on the cube's mathematical solution is not a guarantee that a model will find it.

Our prior experiments found a concrete *possible* contributor to the `U` repetition: the local chat system prompt included the exact output example `{"move": "U"}` and the move options always began with `U`. That doesn't prove causation, but it can be tested.

Another user-visible error: unsolved runs could receive a first-place medal because ranking used time and sticker counts even when **all** models failed.

## Changes in this project

1. **Neutral output instruction:** no specific example face turn in the default chat prompt or recovery instruction. Response is still validated against exactly 18 legal moves; no model answer is fabricated.
2. **Deterministically rotated action display:** move order is seeded by the current cube state and move history. All four local competitors get equivalent rules, the same 18 moves and the same action ordering for the same observation. The legal action space, cube engine, and correct solution do not change. This is a prompt-position-bias control, not a solver.
3. **Explicit multi-turn objective:** the shared guidance asks each model to consider consequences across turns and avoid inverse-move cycles. The backend continues to report visited states, but DOES NOT force an unassisted model's move.
4. **Honest medals:** only solved runs are awarded 1st/2nd/3rd place. A zero-move failure no longer wins.
5. **A/B diagnostic:** `scripts/compare_local_prompts.py` runs old vs neutral prompts on identical verified three-move scrambles. It measures legal and optimal **first** moves, not complete solves.
6. **Preserved hosted safety:** OpenRouter is still disabled by default. The existing persistent SQLite counter, 65-request overall target, 5-Claude cap, and cache are unchanged. The Ollama version continues to use Clef, Qwen, Llama 3.2, and Gemma.
7. **Existing honest solver-guided demo:** the opt-in assisted mode remains separate and clearly labelled; solver-supplied or overridden moves do not count as standalone-model success. Keep it OFF when assessing model reasoning.

## Run (Windows, project on C: and Ollama weights on D:)

Keep your existing `.env`, `data/usage.sqlite3`, `results/`, and `.venv` when installing the PATCH. Add these settings to `.env`:

```ini
OLLAMA_MODEL_CLEF=clef-flash
OLLAMA_MODEL_QWEN=qwen3.5:2b
OLLAMA_MODEL_LLAMA=llama3.2:3b
OLLAMA_MODEL_GEMMA=gemma3:1b
OLLAMA_STICKER_HINTS=0
OLLAMA_PROMPT_VARIANT=neutral
OLLAMA_ROTATE_ACTIONS=1
OLLAMA_STOP_ON_REPEAT_LOOP=0
ALLOW_LIVE_API=0
```

The model storage folder on D: is managed by Ollama using `OLLAMA_MODELS=D:\OllamaModels`. The Python app only connects to `http://localhost:11434`.

```powershell
cd "$env:USERPROFILE\Downloads\rubiks-cube-race"
ollama list
.\.venv\Scripts\python.exe -m scripts.compare_local_prompts --model gemma_local --puzzles 1 --dry-run
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open http://localhost:8000, hard refresh (`Ctrl+Shift+R`), select Ollama, choose 1 puzzle, Parallel OFF and solver guidance OFF. Use one fixed seed for honest comparisons.

For a real local A/B test (this will take actual **local** model time):

```powershell
.\.venv\Scripts\python.exe -m scripts.compare_local_prompts --model gemma_local --seed 483 --puzzles 2
.\.venv\Scripts\python.exe -m scripts.compare_local_prompts --model clef_local --seed 483 --puzzles 1 --timeout 300
```

Each A/B test invokes local Ollama. It never calls OpenRouter. Results are saved to `results/local-prompt-ab.json`. The same puzzle seed and equivalent move rules are used in both variants; note that the A/B changes both the output example and the action order. To isolate either factor, use `OLLAMA_PROMPT_VARIANT` and `OLLAMA_ROTATE_ACTIONS` separately.

## Testing and limitations

The included tests validate legal action sets, exact-three-move scrambles, A/B request generation, no leaked solution, no altered model moves in independent mode, UI medals, backend quotas, and mock API behavior. None of these simulate actual Clef/Qwen/Llama/Gemma reasoning ability. Their success rates must be measured using Ollama on the user's machine.

For a reliable solved *system* demonstration, the existing solver-guided checkbox may be selected, but every intervention is logged as assisted. Do not report it as an unassisted model success. If a model genuinely fails on a 3-move puzzle, show that failure honestly in the assignment analysis.

## Security

The downloaded source packages omit `.env`, the original uploaded ZIP (which contained a key), virtual environments, saved results, and `data/usage.sqlite3`. Do not commit secrets; ask the key owner to rotate a previously leaked key.
