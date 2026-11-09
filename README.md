# Rubik’s Cube Race — AI Engineering Assignment 02

> **Read the full assignment report first:** **[REPORT.md — Methodology, Results, All 70 Moves and Conclusions](REPORT.md)**  
> **Watch the recorded demo:** **[Cube Benchmark Highlights (MP4)](demo/Cube_Benchmark_Highlights.mp4)**  
> **Review raw evidence:** [Trial-level CSV](results/trials-20261108-162041-6b63.csv) · [Per-move CSV](results/moves-20261108-162041-6b63.csv)

## Team members

| Member | Roll number |
|---|---|
| **Emman Abrar** | **23K-0051** |
| **Areeba Hasnain** | **23K-0059** |
| **Hamza Sheikh** | **23K-0060** |

## Demonstration video

[![Rubik's Cube Race benchmark video preview](docs/demo-preview.jpg)](demo/Cube_Benchmark_Highlights.mp4)

**[▶ Watch / download the complete demo](demo/Cube_Benchmark_Highlights.mp4)** · MP4 (H.264 video, AAC audio) · approximately **3 min 19 sec** · **20.3 MB**. The video showcases the competition interface, cube animations, local model decisions, and benchmark statistics. It is edited highlight footage; rely on exported metrics rather than onscreen replay time for quantitative comparisons.

## 1. What this project does

Rubik's Cube Race is a **reproducible, browser-based AI decision benchmark** for a standard 3×3 Rubik's Cube. Several language and decision models independently receive the *same* scrambled cube and choose one legal face turn at a time. The backend applies each proposed move to a real cube state, displays the resulting state in a 3D CSS interface, and measures decision latency and solving quality.

The project was built for **AI Engineering — Assignment 02**, focused on **speed versus quality**: Is a fast decision model more useful than a frontier language model when correctness also matters?

This is an **actual interactive cube simulator**, not four prerecorded animations. In the normal benchmark the algorithm never silently substitutes a correct move for a model's proposal. The benchmark can therefore record failures honestly.

### At a glance

- **Input:** 54 facelets describing six 3×3 faces, representing a cube with a **verified shortest solution length of exactly three face turns**.
- **Actions:** 18 legal moves: `U U' U2 R R' R2 F F' F2 D D' D2 L L' L2 B B' B2`.
- **Comparison:** All selected models receive the same initial puzzle, rules, and move limit within a run.
- **Outcome:** `SOLVED`, `RAN_OUT_OF_MOVES`, `OUT_OF_TIME`, or a recorded error/call-limit state, as appropriate.
- **Measured:** time per accepted move, total trial time, solved/attempted, move count, shortest-path optimality gap on solved puzzles, invalid output count, request counts, cache hits, provider-reported cost and per-move distance changes.
- **Modes:** local **Ollama**, restricted **OpenRouter**, and explicit **mock** simulation, with results identified by mode.
- **Stack:** Python, FastAPI, Uvicorn, HTTPX, HTML, CSS, vanilla JavaScript, SQLite, Ollama and OpenRouter.

## 2. Recorded experiment — November 8, 2026

**[Complete analysis and all 70 recorded moves → REPORT.md](REPORT.md)**

The included real local experiment used **one primary puzzle**, seed **`188575`**, scramble **`R2 F2 D2`**, with **exact optimal solution length 3**. All models acted **without solver-guided overrides**. Each competitor could make at most **20 moves** and had an Ollama-specific **20-minute time limit**.

| Local model | Exact Ollama ID | Outcome | Moves | Total time | Mean live local latency | Solved |
|---|---|---|---:|---:|---:|---|
| Clef Flash | `clef-flash` | Out of time | 10 | 20m 00s | 112.43 s | No |
| Qwen 3.5 2B | `qwen3.5:2b` | Ran out of moves | 20 | 4m 49s | 14.35 s | No |
| Llama 3.2 3B | `llama3.2:3b` | Ran out of moves | 20 | 3m 41s | 11.02 s | No |
| Gemma 3 1B | `gemma3:1b` | Ran out of moves | 20 | 2m 08s | 6.41 s | No |

**Observed success:** 0/1 for each model (**0%**). Gemma was the fastest; **no model won on solution correctness**. Clef reached a state two moves from solved at its final recorded move but did not finish. The other models repeatedly chose legal but counterproductive moves.

**Request and cost accounting:** 70 local Ollama model calls, **0 OpenRouter calls**, **0 reported cache hits**, and **$0 known billed API cost** in these exports. Local electricity/hardware cost was not measured. These results do **not** establish typical model performance: just one starting state was tested.

See the [trial CSV](results/trials-20261108-162041-6b63.csv), [move CSV](results/moves-20261108-162041-6b63.csv), and [five assignment questions with answers](REPORT.md#6-answers-to-the-five-assignment-questions).

## 3. How the system works

```text
Browser (HTML/CSS/JavaScript)
  ├── chooses suite, seed, models, mode, run options
  ├── displays four animated cube cards and per-turn status
  └── shows/export results and statistics
            │ HTTP + Server-Sent Events (SSE)
            ▼
FastAPI backend
  ├── runner.py: shared puzzle state, per-model turns, timing and rules
  ├── cube.py: 54-facelet cube engine and legal transformations
  ├── solver.py: shortest-path reference for three-turn starts
  ├── contract.py: shared input observation, move vocabulary and rules
  ├── progress.py: bounded post-move distance diagnostics
  ├── stats.py: summary statistics and CSV exports
  ├── ollama.py: local System One / chat model adapters
  ├── adapters.py: hosted decision/chat model adapters
  ├── ledger.py: hosted request quotas, caching and cost ledger (SQLite)
  └── guidance.py: OPTIONAL explicitly assisted demo, separate from benchmark
            │
       ┌────┴────┐
       ▼         ▼
   Local      OpenRouter
  Ollama      (opt-in, restricted)
```

### Cube representation and moves

Each cube state is represented by the 54 stickers of six faces **U, R, F, D, L, B**. A valid action is a clockwise 90-degree face turn, its inverse (`'`), or a half turn (`2`). The model receives both the machine-readable facelet string and a labeled six-face 3×3 display, plus action definitions and recent move history. The cube engine applies the chosen transformation exactly.

The scramble generator is **not merely “three random moves”**: it verifies that the resulting state has a **shortest path of three moves** before the benchmark starts. The exact solver is a reference/oracle for validation and scoring, *not* a source of answers in independent-model mode.

### Fairness and reproducibility

The same seed reconstructs the same initial puzzle. Models start from identical cube states, use the same set of 18 legal actions and the same success/move conditions. Local-model prompts use neutral formatting and state-deterministic action ordering to reduce fixed-choice-position bias. Requests include the current state; a move is never fabricated to cover an invalid output.

The interface can run competitors in parallel or sequentially; **sequential local runs** are recommended on limited RAM/VRAM. Hardware, model versions, prompt variants, and parallel/serial mode can affect latency; report these whenever comparing runs.

### Post-move diagnostics

The engine tracks whether a submitted turn made the cube closer to or farther from solved. Exact distances are computed only **within a seven-turn bounded search**. States labeled `>7` have unknown exact distance beyond that bound; `>7` is *not* an exact distance of eight. The post-move distance oracle is **not supplied as the answer to an unassisted model**.

### Assisted mode is a different experiment

The **Solver-guided demo** checkbox can replace selected poor model proposals with reference-solver moves. These interventions are logged and assisted solves are excluded from independent-model success calculations. Keep this **OFF** for the assignment's model-only comparison; never claim an assisted solve was achieved by a standalone model.

## 4. Models and run modes

| Mode | Competitors | Endpoint / behavior | Hosted credits |
|---|---|---|---|
| **Ollama** | Clef Flash, Qwen 3.5 2B, Llama 3.2 3B, Gemma 3 1B | Ollama at `http://localhost:11434`; Clef uses System One; others use chat | None |
| **OpenRouter** | Jev 1.13, GPT-6 Luna Decisions, Cloudflare Clef, Claude Opus 5.5 | Restricted hosted decision/chat endpoints; model IDs are configurable | Possible; requires valid authorized key |
| **Mock** | Simulated competitors | No genuine remote/local model inference | None |

The **recorded result** in this repository is an **Ollama** run. We do **not** claim the hosted OpenRouter experiment was performed. Mock results are never valid as real benchmark results.

## 5. Installation and setup (Windows / PowerShell)

### Requirements

- Python **3.10+** and Windows PowerShell (Linux/macOS also possible with shell changes).
- Ollama installed for genuine local runs; model storage can be on a separate D: drive.
- Sufficient free disk space and RAM/VRAM for the models. Clef Flash is particularly heavy and may take over a minute per move on constrained hardware.
- Internet access for the initial Ollama model downloads or authorized OpenRouter calls, if used.

### A. Clone and install Python dependencies

```powershell
git clone https://github.com/areebahasnain/AI_Eng_A2.git
cd AI_Eng_A2
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Never commit `.env`. It can contain a secret API key. `.env.example` must remain key-free.

### B. Prepare local Ollama models on D: (optional disk layout)

Use Ollama's Windows installer, then configure the model-storage path for your Windows account:

```powershell
New-Item -ItemType Directory -Force D:\OllamaModels
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'D:\OllamaModels', 'User')
```

**Quit and restart Ollama and open a fresh PowerShell window** after changing the environment variable. Verify that its local API responds:

```powershell
ollama --version
Invoke-RestMethod http://localhost:11434/api/tags
```

Download the actual local competitors:

```powershell
ollama pull clef-flash
ollama pull qwen3.5:2b
ollama pull llama3.2:3b
ollama pull gemma3:1b
ollama list
```

Model weights live on D:; the Python project remains wherever it was cloned. The Python backend connects to Ollama via **HTTP**, so no D: path is needed in the project configuration.

### C. Configure `.env`

Edit `.env` with Notepad and set the exact installed model tags:

```ini
STUDENT_NAME=Your Name
STUDENT_ROLL_NO=Your Roll Number
MOCK=1
ALLOW_LIVE_API=0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_CLEF=clef-flash
OLLAMA_MODEL_QWEN=qwen3.5:2b
OLLAMA_MODEL_LLAMA=llama3.2:3b
OLLAMA_MODEL_GEMMA=gemma3:1b
OLLAMA_PROMPT_VARIANT=neutral
OLLAMA_ROTATE_ACTIONS=1
OLLAMA_STICKER_HINTS=0
OLLAMA_STOP_ON_REPEAT_LOOP=0
OLLAMA_REQUEST_TIMEOUT_S=300
OLLAMA_TIME_LIMIT_S=1200
```

`MOCK=1` is a **safe default** for provider initialization. In the interface, choose **Ollama** to make genuine *local* model calls. `ALLOW_LIVE_API=0` protects the restricted hosted key; it does not disable Ollama.

### D. Run the app

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open **http://127.0.0.1:8000**. Choose **Ollama (local models)**, **Primary · exactly 3 moves**, one puzzle for an initial test, **Parallel off**, **Solver-guided demo off**. Click **Run benchmark**, then open the statistics view and export the CSV files.

### E. Verify model adapters before a full race

```powershell
.\.venv\Scripts\python.exe -m scripts.local_preflight --model clef_local --timeout 240
.\.venv\Scripts\python.exe -m scripts.local_preflight --model llama_local --timeout 240
```

Preflight sends real **local** inference requests only. It tests whether the Ollama server and adapter can return a legal move, not whether the model can solve an entire cube.

## 6. OpenRouter policy and secrets

The teacher-provided OpenRouter key is **personalized, restricted, and must never be published**. The application keeps hosted access **off by default**. Use a hosted run only when authorization has been confirmed and the key is valid.

The backend includes these safeguards for hosted model inference:

| Restriction | Enforced limit |
|---|---:|
| Verified starting distance | Exactly 3 turns |
| Decision-model move/request allowance | 20 per decision model |
| Claude Opus request allowance | 5 total, including failed attempts |
| Total target across hosted models | **65** calls |
| Teacher's stated key ceiling | 100 calls (outside cap; do not attempt to use all 100) |
| Hosted retry policy | Zero retries by default |
| API response cache | Persistent SQLite cache checked before requests |
| Quota persistence | SQLite call ledger survives application restart |

Hosted actual request latency and cache retrieval latency are recorded separately. API-reported cost is stored when the provider supplies it. Counters for a specific key do not automatically include calls made by other applications or previous installs, so never assume remaining credit purely from a local counter.

**Do not commit:** `.env`, API keys, usage databases, virtual environments, local model weights, or private raw logs. If a key was previously exposed, ask its issuer to rotate it.

## 7. Interface, exports and API routes

The frontend features animated 3D cube cards, model labels and categories, per-model timers, recent action history, live states, exact-distance progress labels, explicit failures, replay, and aggregate statistics. The **five assignment questions** are drafted from the run data for review and revision.

Selected FastAPI endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /` | Interactive benchmark UI |
| `GET /api/health` | Service health |
| `GET /api/config` | Sanitized public configuration; never exposes the API key |
| `GET /api/usage` | Hosted request-budget overview |
| `POST /api/run` | Create a benchmark run |
| `GET /api/run/{run_id}/events` | Server-Sent Events stream for live updates |
| `POST /api/run/{run_id}/stop` | Stop a running benchmark |
| `GET /api/run/{run_id}` | Retrieve run data |
| `GET /api/runs/latest` | Latest saved run |
| `GET /api/run/{run_id}/trials.csv` | Trial-level export |
| `GET /api/run/{run_id}/moves.csv` | Detailed per-move export |

The sample exported CSVs from the November 8 benchmark are committed under [`results/`](results/); they can be inspected without running the backend. The application's own full per-run JSON files are generated locally and normally excluded from Git.

## 8. Source code map

| Path | Responsibility |
|---|---|
| `backend/cube.py` | 3×3 cube state transitions and legal moves |
| `backend/solver.py` | Reference shortest-path search |
| `backend/contract.py` | Common state/action contract for models |
| `backend/runner.py` | Trial execution, timeouts, stopping criteria, event updates |
| `backend/ollama.py` | Clef Flash and local chat-model HTTP adapters |
| `backend/adapters.py` | OpenRouter decision and chat adapters |
| `backend/ledger.py` | Hosted quota reservations, response caching, usage logs |
| `backend/config.py` | Model definitions, env settings, policies |
| `backend/progress.py` | Post-move progress and bounded exact-distance diagnostics |
| `backend/guidance.py` | Clearly labeled optional assisted controller |
| `backend/stats.py` | Aggregation, benchmark Q&A, CSV generation |
| `backend/main.py` | FastAPI routes and frontend serving |
| `frontend/index.html` | Application page structure |
| `frontend/style.css` | Responsive UI and cube styling |
| `frontend/app.js` | Browser behavior, SSE rendering, replay and statistics |
| `scripts/` | Local model preflight, diagnostics and experimental tools |
| `tests/` | Cube, solver, API, adapter, ledger, and UI regression tests |
| [`REPORT.md`](REPORT.md) | Full assignment report, 70-move traces, conclusions and caveats |
| [`demo/Cube_Benchmark_Highlights.mp4`](demo/Cube_Benchmark_Highlights.mp4) | Recorded demonstration video |
| [`results/`](results/) | Published trial and move CSV evidence |

## 9. Testing and reproducibility

Install development requirements and execute the tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The source archive previously passed **129 offline automated tests** after prompt and ranking fixes. Offline tests use the cube engine plus simulated HTTP responses; they **do not prove actual Ollama model accuracy on a specific PC**. The reported benchmark is the genuine recorded local run documented in [`REPORT.md`](REPORT.md), including negative outcomes.

For repeatability, record the run ID, suite, seed, scramble, selected model tags, Ollama version, hardware, prompts/settings, concurrency, move limit, and elapsed time. Distinguish **local model requests**, **hosted live calls**, **cached outputs**, and **solver-assisted turns**; they are different measurements.

## 10. Findings, limitations and future work

This experiment demonstrates an important result: **speed alone is not enough to solve a sequential spatial puzzle**. In the included single-seed run, every model produced legal actions but none solved the cube; Gemma was the fastest, while Clef took substantially longer per decision. Repeated turns frequently returned the cube to previously visited states.

Because there was only one puzzle, the numbers cannot rank general model ability or prove one model family is intrinsically better. Future experiments should use multiple fixed seeds, model-version documentation, consistent inference settings, and side-by-side ablations of prompt representation. A separate, explicitly labeled tool-assisted controller can be evaluated for reliability but must not be presented as a pure model result.

Read the full discussion and the answers to all five required assignment questions in **[REPORT.md](REPORT.md)**.

---

**Assignment submission contents:** project source, reproducible setup, independently recorded benchmark, [complete report](REPORT.md), [CSV evidence](results/), and [screen recording](demo/Cube_Benchmark_Highlights.mp4). No GitHub Actions are required or used by this project.
