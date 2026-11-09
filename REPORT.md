# Assignment 02 — Rubik’s Cube Race: Experimental Report

> **Assignment:** AI Engineering — Assignment 02  
> **Run ID:** `20261108-162041-6b63`  
> **Recorded:** November 8, 2026  
> **Suite:** Primary, exactly three moves from solved  
> **Execution:** Local Ollama models; **unassisted** model decisions  
> **Outcome:** **0 of 4 competitors solved the puzzle**

This document is a detailed record of one completed four-model race. It combines the application's results screen with the exported per-trial and per-move logs. It is intended for the project repository and the assignment report. **The numbers are observations from this one run, not general performance claims about the model families.**

## Project team and submission links

| Team member | Roll number |
|---|---|
| Emman Abrar | `23K-0051` |
| Areeba Hasnain | `23K-0059` |
| Hamza Sheikh | `23K-0060` |

- **[Project documentation and setup](README.md)** — architecture, requirements, installation, run modes, and reproduction steps.
- **[Recorded demonstration (MP4)](demo/Cube_Benchmark_Highlights.mp4)** — approximately 3 minutes 19 seconds; includes the application interface, live/replayed competition and benchmark statistics.
- **[Raw trial CSV](results/trials-20261108-162041-6b63.csv)** and **[raw move CSV](results/moves-20261108-162041-6b63.csv)** — exported evidence for the run analysed here.

> The video is a highlight recording. Timing shown during replay/edited footage is not a substitute for the measured latency and wall-clock values in the CSV exports.

## Data and provenance

- [Per-trial export](results/trials-20261108-162041-6b63.csv) — one record per model; status, timing, quota counters, final distance, and cost fields.
- [Per-move export](results/moves-20261108-162041-6b63.csv) — all 70 decisions, latencies, action history, and post-move distance diagnostics.
- Application statistics screen supplied with the same run — contains the displayed scramble, five auto-drafted questions, percentile statistics, and aggregate summaries.
- An associated complete JSON result is reported as saved under the app's local `results/` directory, **but that JSON was not supplied with this documentation**, so its unseen fields have not been used.

The CSV files were reviewed independently. The four trial rows account for exactly **10 + 20 + 20 + 20 = 70 accepted actions**, matching the 70 per-move records. There are no nonzero `api_calls`, `cache_hits`, `retries`, `invalid_outputs`, or `failed_turns` in the uploaded records.

## 1. Executive summary

- **Task:** Solve one standard 3×3 cube beginning **exactly three face turns** away from solved.
- **Common initial scramble:** `R2 F2 D2` (from the displayed experiment summary).
- **Reference optimal solution length:** **3** turns, marked as an exact shortest distance by the benchmark.
- **Competitors:** Clef Flash, Qwen 3.5 2B, Llama 3.2 3B, and Gemma 3 1B.
- **Same test puzzle:** `primary-188575-1`, seed `188575`, used for all competitors.
- **Maximum actions per model:** **20**. A separate time cap was **1,200 seconds (20 minutes)** per model.
- **Successful solves:** **0/4** models. No valid solved-puzzle optimality gaps can be calculated.
- **Fastest live local decision-making:** **Gemma 3 1B**, at **6.41 seconds per move** on average.
- **Slowest:** **Clef Flash**, at **112.43 seconds per move** on average, and it hit the 20-minute time limit after only ten moves.
- **Best observed proximity in this run:** **Clef Flash reached two moves from solved**. It did not solve.
- **Remote API usage:** **0 requests**; **70** local Ollama requests and **0** cache hits.
- **Known billed OpenRouter cost:** **$0.00000** for this local run. Power/hardware expenditure was not measured.

**Main finding:** Every model returned syntactically valid moves, but their sequences did not reliably progress toward the solved state. This is primarily a **decision-quality / multi-turn planning** failure in this run, not a response-parsing failure.

## 2. Experimental design and conditions

| Field | Recorded setting |
|---|---|
| Run ID | `20261108-162041-6b63` |
| Test suite | Primary |
| Puzzles evaluated | 1 |
| Seed | `188575` |
| Puzzle ID | `primary-188575-1` |
| Starting scramble | `R2 F2 D2` |
| Verified shortest distance | 3 face turns; exact reference |
| Legal action space | 18 face turns (`U`, `U'`, `U2`, `R`, `R'`, `R2`, `F`, `F'`, `F2`, `D`, `D'`, `D2`, `L`, `L'`, `L2`, `B`, `B'`, `B2`) |
| Moves allowed | 20 per local model |
| Wall-clock limit | 1,200 seconds per model |
| Execution mode | Ollama, local inference |
| Models selected | All four local models |
| Solver-guided assistance | **Disabled**, shown as `assisted_mode=False` in all trial rows |
| OpenRouter calls | 0 |
| Cache hits | 0 |
| Retries | 0 |
| Invalid outputs | 0 |
| Failed turns | 0 |
| Distance measurement | Exact shortest-path search only within 7 turns; farther states reported `>7` |
| Parallel setting | Not established by the supplied CSV or pasted settings; do not infer it |
| Model temperatures / quantization / hardware | Not included in supplied measurements |

A scramble of length three is **not enough** to prove an exact distance of three in general: cancellations can make a scramble shorter. For this run, the benchmark's reference result explicitly records the optimal distance as 3 with `optimal_exact=True` in all four trial rows.

### How to read the metrics

- **Move latency:** Time to obtain an accepted local move from the model; the trial CSV reports its average.
- **Live request latency:** Total time attributable to local model requests, excluding cache hits; here every request was live/local.
- **Trial wall time:** Elapsed time for that model's entire attempt; an unsuccessful trial has **no solve time** even though a wall-time duration is reported.
- **Success rate:** Number of solved puzzles divided by the puzzles attempted. Each model attempted **only one**.
- **Optimality gap:** Actual solution length minus the exact shortest solution, defined **only for solved puzzles**.
- **Post-move distance:** Exact distance when bounded search resolves it; `>7` is *not* an exact distance.
- **Local request:** One invocation of an Ollama model on the user's computer, distinct from a billed remote OpenRouter request.

## 3. Complete four-model results

| Model | Ollama model ID | Outcome | Actions | Wall time | Mean live latency / move | Success | Final distance | Correct facelets |
|---|---|---|---:|---:|---:|---:|---|---:|
| Clef Flash | `clef-flash` | Out of time | 10 | 20m 00.03s | 112.43 s | 0/1 (0%) | 2 | 34 |
| Qwen 3.5 2B | `qwen3.5:2b` | Ran out of moves | 20 | 4m 48.89s | 14.35 s | 0/1 (0%) | >7 (unresolved) | 15 |
| Llama 3.2 3B | `llama3.2:3b` | Ran out of moves | 20 | 3m 41.44s | 11.02 s | 0/1 (0%) | 7 | 30 |
| Gemma 3 1B | `gemma3:1b` | Ran out of moves | 20 | 2m 08.17s | 6.41 s | 0/1 (0%) | 6 | 19 |

**Reading the table:** “Final distance” is the number of remaining face turns **if resolved within the seven-turn search horizon**. The final Qwen position is beyond that horizon; the source does not specify its exact distance. “Correct facelets” counts matching stickers and is not itself proof of solving.

### Actual request and validation counts

| Model | Local requests | Remote OpenRouter calls | Cache hits | Invalid outputs | Retries | Failed turns | Guided overrides | Recorded cost (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Clef Flash | 10 | 0 | 0 | 0 | 0 | 0 | 0 | Not reported |
| Qwen 3.5 2B | 20 | 0 | 0 | 0 | 0 | 0 | 0 | Not reported |
| Llama 3.2 3B | 20 | 0 | 0 | 0 | 0 | 0 | 0 | Not reported |
| Gemma 3 1B | 20 | 0 | 0 | 0 | 0 | 0 | 0 | Not reported |
| **Total** | **70** | **0** | **0** | **0** | **0** | **0** | **0** | **No billed remote usage reported** |

The application's header displays `$0.00000` as **known cost**, consistent with zero remote calls, while individual `cost_usd` values in the trials CSV are blank. The experiment does not measure electricity or hardware amortization.

## 4. Speed comparison

| Rank (fastest first) | Model | Avg accepted move latency | Approximate relative to Gemma | Trial wall time |
|---:|---|---:|---:|---:|
| 1 | Gemma 3 1B | 6.41 s | 1.00× | 2m 08.17s |
| 2 | Llama 3.2 3B | 11.02 s | 1.72× | 3m 41.44s |
| 3 | Qwen 3.5 2B | 14.35 s | 2.24× | 4m 48.89s |
| 4 | Clef Flash | 112.43 s | 17.55× | 20m 00.03s |

**Interpretation:** Gemma's average local response was about **17.6× faster** than Clef's. This measures time to return a move on the machine used for this experiment; it is **not** a comparison of hardware-independent model efficiency. Clef's total trial wall time reached 20 minutes, while its ten accepted move latencies account for roughly 18 minutes 44 seconds. Wall-time and request-time measurements need not be identical.

### Why the other models finished more moves

Clef took about 112 seconds per accepted decision on average, so it reached the 1,200-second wall-clock limit after ten actions. Qwen, Llama, and Gemma were faster per move and were able to execute all twenty allowed actions. **Completing more actions did not translate into solving.**

## 5. Move quality and distance diagnostics

The engine evaluated how each accepted move changed the shortest known distance from solved, when resolvable. Reducing that distance is a useful local signal, but it does not guarantee a future solve. The distance indicator is a **post-move diagnostic**, not a correct-answer label sent to the models.

| Model | Closer (`↓`) | Farther (`↑`) | Unchanged (`→`) | Unknown (`>7`) | Best verified distance reached | Final state |
|---|---:|---:|---:|---:|---:|---|
| Clef Flash | 4 | 3 | 3 | 0 | 2 | 2 |
| Qwen 3.5 2B | 2 | 7 | 5 | 6 | 3 | >7 (unknown exact distance) |
| Llama 3.2 3B | 6 | 10 | 0 | 4 | 3 | 7 |
| Gemma 3 1B | 6 | 9 | 5 | 0 | 3 | 6 |
| **All 70 moves** | **18** | **29** | **13** | **10** | — | — |

Of all 70 actions, 18 demonstrably reduced verified distance, 29 increased it, 13 left it unchanged, and 10 could not be classified within the bounded search horizon. The 10 unknown actions should **not** be counted as improvements or regressions.

### Decision traces reveal action loops

| Model | Most frequent move | Count | Immediately repeated previous move | Observed behavior |
|---|---|---:|---:|---|
| Clef Flash | `D'` | 4/10 | 2 | D/D' and B/B' reversals; briefly reached distance 2 |
| Qwen 3.5 2B | `R` | 13/20 | 12 | Long runs of R, followed by U/R repetition |
| Llama 3.2 3B | `L2` | 16/20 | 11 | Mostly L2 with occasional F2; repeats half-turns |
| Gemma 3 1B | `U2` | 18/20 | 15 | Mostly U2; repeated 180° turns undo each other |

**Important:** Two successive half-turns of the same face cancel (`U2 U2` or `L2 L2` is an identity). Four consecutive quarter-turns of the same face also return that face to its original orientation. These simple cycles help explain why valid output can still be unproductive.

### Model-by-model observations

**Clef Flash:** All ten responses were accepted as valid actions. It reached verified distance 2 after turn 4, returned to distance 3 or 4 several times, and finished again at distance 2 after turn 10. The run stopped due to the 20-minute limit, not the 20-move limit. Its mean latency made it the slowest by a wide margin. This is a *nearer final position*, not a completed solve.

**Qwen 3.5 2B:** Chose `R` in 13/20 actions and `U` in 6/20. Its first eight actions included eight consecutive `R` turns, creating repeated rotations with little durable progress. It ended at a state recorded as `>7`, meaning the seven-turn bounded solver did not resolve an exact distance. It produced no invalid outputs but exhausted all twenty moves.

**Llama 3.2 3B:** Selected `L2` in 16/20 actions and `F2` in 4/20. The repeated `L2` half-turns alternated between states, frequently moving from distance 6 to 7 and back. It finished at exact distance 7 after twenty legal actions.

**Gemma 3 1B:** Selected `U2` in 18/20 actions, with one `U'` and one `B2`. After moving farther from solved, it often alternated between verified distances 5 and 6 by repeatedly applying `U2`. It was fastest but did not solve.

**Quality conclusion:** In this one puzzle, none of the four models demonstrated reliable multi-turn planning. The evidence does not show that any model is consistently better on solve quality across different seeds. It does show striking action repetition in the observed traces.

## 6. Answers to the five assignment questions

### Q1. Which model was fastest at making decisions?

**Gemma 3 1B.** It averaged **6,406.22 ms per live local request** (about 6.41 s per move); the application reports a median of **5,894.46 ms** and p95 of **7,449.76 ms**. In comparison:

- Llama 3.2 3B: **11,023.32 ms/move**.
- Qwen 3.5 2B: **14,346.80 ms/move**.
- Clef Flash: **112,430.08 ms/move**.

Gemma was approximately **17.6× faster** than Clef for the average live local decision. This speed comparison says nothing by itself about solving correctness.

### Q2. Which model achieved the highest solve rate?

**None. All four tied at 0%**, solving **0 of 1** puzzle each. Clef timed out after ten moves; Qwen, Llama, and Gemma each used all twenty permitted moves without solving. One test puzzle is too small a sample to rank the models' typical solve rates.

### Q3. Which model found the shortest solutions, and how close were they to the optimum?

**No model produced a complete solution**, so the shortest successful solution and the optimality gap are **not applicable** for all four competitors. The known shortest solution for the starting position is **3 turns**. Clef did get to two moves away, but that is not a solved sequence and must not be reported as an optimality gap.

### Q4. Did the fastest model also achieve the best solution quality?

**No meaningful quality winner can be identified.** Gemma was fastest, but all models had **0% success**. The UI's auto-generated “yes, jointly best” statement is mathematically based on a four-way tie at zero; it is **misleading if interpreted as evidence that Gemma solves cubes better**. Speed and quality cannot be linked on this run because every attempt failed.

### Q5. Would you use the fastest decision model, the frontier LLM, or a hybrid agent in a real-world application?

**A verified hybrid system is the most defensible engineering choice to investigate, but this run does not validate its solve rate.** Small local models produced fast or slow plausible moves without dependable completion. A practical system could use a model to propose actions, a deterministic simulator to reject illegal actions and detect cycles, and an exact search component for recovery or correctness-critical cases. Such a system must be **reported as solver/tool-assisted**, not as a standalone model solving performance.

For this **unassisted benchmark**, the evidence supports only the narrower conclusion that **no tested local model completed the single three-turn puzzle**, and Clef was markedly slower while Gemma was fastest. The original OpenRouter decision-model versus Claude comparison was **not conducted** here, so this run alone cannot establish which hosted model type is preferable.

## 7. Limitations and methodological cautions

1. **Only one starting state.** Each reported 0% is 0/1 and cannot establish general solve accuracy or a meaningful confidence interval.
2. **Local, smaller models.** This was Clef Flash, Qwen 2B, Llama 3B, and Gemma 1B in Ollama, **not** the requested hosted Jev/Luna/Clef/Claude benchmark.
3. **No independent machine specifications supplied.** CPU/GPU, available RAM, quantization settings, Ollama version, and possible cold-start effects were not recorded in the exports. Latencies may change substantially on other hardware.
4. **Bounded distance oracle.** States reported `>7` have unknown exact distances, not distance 8.
5. **Unassisted outputs.** All trial rows say `assisted_mode=False`, with zero guided overrides. These are model-generated moves, not solver-substituted moves.
6. **Post-move evaluation vs. model input.** The CSV shows distances after actions, but **does not prove** which exact prompt features were active or whether each model saw distance feedback. Do not infer settings from the diagnostic columns.
7. **Not a full budget demonstration.** Zero OpenRouter calls in this run do not establish whether hosted request caps, cache persistence, or the Claude five-call limit would operate correctly in a separate hosted run.
8. **Elapsed time differs from summed inference time.** Use live request latency for model speed and trial wall clock for deadline behavior; they represent different metrics.
9. **No billed API charge measured.** A displayed `known cost` of zero does not mean local computation is free of electricity or hardware cost.
10. **Model-selection evidence is narrow.** These observations cannot justify changing the assignment's models or declaring that model families are intrinsically unable to solve near-solved cubes.

## 8. Recommendations for the next controlled experiment

For a stronger and fairer report, run **several fixed, independently generated exact-three-turn seeds** and report solved/attempted per model, while preserving identical cube states, legal moves, move limits, and allowed information. Keep parallel/serial execution consistent and record the hardware configuration. In an A/B test, compare neutral prompts against a single changed instruction at a time; avoid changing both the model and its prompt simultaneously.

Record per model: total attempts, accepted and invalid outputs, actual latency, retries, timeout status, successful solve length, exact optimality gap **only on successful solves**, and the fraction of moves that reduced verified distance. For the teacher's hosted run, keep the separate, persistent 65-call overall target and five-call Claude cap; **do not** count these 70 local Ollama calls as OpenRouter expenditure.

If demonstrating a simulator-verified or solver-guided controller, publish its outcomes in a **separate assisted-results section**, with explicit override counts. Do not combine assisted success with standalone model success.

## 9. Reproducing and reviewing this run

When the FastAPI backend is running on the author’s computer, it serves its results at:

```text
http://127.0.0.1:8000/api/run/20261108-162041-6b63/trials.csv
http://127.0.0.1:8000/api/run/20261108-162041-6b63/moves.csv
```

Those `127.0.0.1` URLs work **only on the machine running that FastAPI server**, not from GitHub. The two CSV files linked from the `results/` folder are the portable evidence included in this repository. If the app still has its original full JSON under `results/`, preserve it locally as primary evidence; it was not uploaded with this request.

The run was configured for **Primary · exactly 3 moves**, **1 puzzle**, **seed 188575**, **Ollama**, and four selected local models. The complete per-turn logs follow below so the CSVs can be audited without launching the app.

## 10. Full per-move decision logs (70 actions)

The `distance` column shows the recorded exact shortest distance *before → after* when within the seven-turn horizon. `>7` means exact distance unknown. `✓ closer`/`↑ farther`/`→ same` are derived from the exported `distance_change` field, not guesses. These logs are exhaustive for the four trials in the CSV.


<details>
<summary><strong>Clef Flash — 10 moves (expand full trace)</strong></summary>


| Turn | Move | Local latency (s) | Distance before → after | Outcome | Correct facelets | Elapsed (s) |
|---:|---|---:|---|---|---:|---:|
| 1 | `D'` | 147.66 | 3 → 3 | Unchanged | 26 | 147.66 |
| 2 | `D` | 106.03 | 3 → 3 | Unchanged | 30 | 253.70 |
| 3 | `D'` | 108.05 | 3 → 3 | Unchanged | 26 | 361.75 |
| 4 | `D'` | 106.38 | 3 → 2 | Closer | 34 | 468.13 |
| 5 | `D'` | 110.19 | 2 → 3 | Farther | 26 | 578.32 |
| 6 | `B` | 111.55 | 3 → 4 | Farther | 17 | 689.87 |
| 7 | `B'` | 106.11 | 4 → 3 | Closer | 26 | 795.99 |
| 8 | `L` | 106.39 | 3 → 4 | Farther | 20 | 902.38 |
| 9 | `L'` | 107.03 | 4 → 3 | Closer | 26 | 1,009.41 |
| 10 | `D` | 114.92 | 3 → 2 | Closer | 34 | 1,124.33 |

</details>

**Clef Flash action sequence:** `D'` `D` `D'` `D'` `D'` `B` `B'` `L` `L'` `D`


<details>
<summary><strong>Qwen 3.5 2B — 20 moves (expand full trace)</strong></summary>


| Turn | Move | Local latency (s) | Distance before → after | Outcome | Correct facelets | Elapsed (s) |
|---:|---|---:|---|---|---:|---:|
| 1 | `R` | 47.14 | 3 → 4 | Farther | 24 | 47.14 |
| 2 | `R` | 17.19 | 4 → 4 | Unchanged | 30 | 64.34 |
| 3 | `R` | 13.88 | 4 → 4 | Unchanged | 24 | 78.23 |
| 4 | `R` | 13.83 | 4 → 3 | Closer | 30 | 92.06 |
| 5 | `R` | 15.06 | 3 → 4 | Farther | 24 | 107.13 |
| 6 | `R` | 14.59 | 4 → 4 | Unchanged | 30 | 121.73 |
| 7 | `R` | 11.78 | 4 → 4 | Unchanged | 24 | 133.51 |
| 8 | `R` | 11.97 | 4 → 3 | Closer | 30 | 145.48 |
| 9 | `L` | 11.93 | 3 → 4 | Farther | 24 | 157.42 |
| 10 | `R` | 11.64 | 4 → 5 | Farther | 18 | 169.28 |
| 11 | `R` | 11.97 | 5 → 5 | Unchanged | 24 | 181.26 |
| 12 | `U` | 11.97 | 5 → 6 | Farther | 17 | 193.25 |
| 13 | `R` | 11.81 | 6 → 7 | Farther | 11 | 205.08 |
| 14 | `U` | 12.41 | 7 → >7 | Farther | 11 | 217.60 |
| 15 | `U` | 11.30 | >7 → >7 | Unknown (>7) | 9 | 229.12 |
| 16 | `U` | 11.50 | >7 → >7 | Unknown (>7) | 14 | 240.86 |
| 17 | `R` | 11.75 | >7 → >7 | Unknown (>7) | 16 | 252.82 |
| 18 | `R` | 11.88 | >7 → >7 | Unknown (>7) | 18 | 264.91 |
| 19 | `U` | 11.78 | >7 → >7 | Unknown (>7) | 14 | 276.90 |
| 20 | `U` | 11.54 | >7 → >7 | Unknown (>7) | 15 | 288.64 |

</details>

**Qwen 3.5 2B action sequence:** `R` `R` `R` `R` `R` `R` `R` `R` `L` `R` `R` `U` `R` `U` `U` `U` `R` `R` `U` `U`


<details>
<summary><strong>Llama 3.2 3B — 20 moves (expand full trace)</strong></summary>


| Turn | Move | Local latency (s) | Distance before → after | Outcome | Correct facelets | Elapsed (s) |
|---:|---|---:|---|---|---:|---:|
| 1 | `L2` | 27.43 | 3 → 4 | Farther | 30 | 27.43 |
| 2 | `F2` | 12.01 | 4 → 5 | Farther | 30 | 39.45 |
| 3 | `L2` | 10.93 | 5 → 6 | Farther | 28 | 50.39 |
| 4 | `L2` | 10.33 | 6 → 5 | Closer | 30 | 60.74 |
| 5 | `L2` | 9.67 | 5 → 6 | Farther | 28 | 70.41 |
| 6 | `F2` | 9.42 | 6 → 7 | Farther | 34 | 79.83 |
| 7 | `L2` | 10.49 | 7 → >7 | Farther | 36 | 90.45 |
| 8 | `F2` | 10.80 | >7 → >7 | Unknown (>7) | 30 | 101.46 |
| 9 | `L2` | 10.52 | >7 → >7 | Unknown (>7) | 30 | 112.19 |
| 10 | `L2` | 10.75 | >7 → >7 | Unknown (>7) | 30 | 123.13 |
| 11 | `L2` | 9.74 | >7 → >7 | Unknown (>7) | 30 | 132.88 |
| 12 | `F2` | 9.63 | >7 → 7 | Closer | 30 | 142.50 |
| 13 | `L2` | 10.50 | 7 → 6 | Closer | 28 | 153.17 |
| 14 | `L2` | 10.54 | 6 → 7 | Farther | 30 | 163.74 |
| 15 | `L2` | 9.69 | 7 → 6 | Closer | 28 | 173.43 |
| 16 | `L2` | 9.65 | 6 → 7 | Farther | 30 | 183.08 |
| 17 | `L2` | 9.45 | 7 → 6 | Closer | 28 | 192.53 |
| 18 | `L2` | 9.66 | 6 → 7 | Farther | 30 | 202.18 |
| 19 | `L2` | 9.60 | 7 → 6 | Closer | 28 | 211.79 |
| 20 | `L2` | 9.66 | 6 → 7 | Farther | 30 | 221.44 |

</details>

**Llama 3.2 3B action sequence:** `L2` `F2` `L2` `L2` `L2` `F2` `L2` `F2` `L2` `L2` `L2` `F2` `L2` `L2` `L2` `L2` `L2` `L2` `L2` `L2`


<details>
<summary><strong>Gemma 3 1B — 20 moves (expand full trace)</strong></summary>


| Turn | Move | Local latency (s) | Distance before → after | Outcome | Correct facelets | Elapsed (s) |
|---:|---|---:|---|---|---:|---:|
| 1 | `U2` | 12.40 | 3 → 4 | Farther | 26 | 12.40 |
| 2 | `U'` | 5.89 | 4 → 4 | Unchanged | 22 | 18.29 |
| 3 | `U2` | 5.99 | 4 → 4 | Unchanged | 22 | 24.28 |
| 4 | `U2` | 6.03 | 4 → 4 | Unchanged | 22 | 30.31 |
| 5 | `U2` | 5.88 | 4 → 4 | Unchanged | 22 | 36.19 |
| 6 | `U2` | 5.91 | 4 → 4 | Unchanged | 22 | 42.10 |
| 7 | `B2` | 5.84 | 4 → 5 | Farther | 16 | 47.95 |
| 8 | `U2` | 5.69 | 5 → 6 | Farther | 19 | 53.65 |
| 9 | `U2` | 5.79 | 6 → 5 | Closer | 16 | 59.45 |
| 10 | `U2` | 6.00 | 5 → 6 | Farther | 19 | 65.45 |
| 11 | `U2` | 5.88 | 6 → 5 | Closer | 16 | 71.33 |
| 12 | `U2` | 5.72 | 5 → 6 | Farther | 19 | 77.05 |
| 13 | `U2` | 5.85 | 6 → 5 | Closer | 16 | 82.90 |
| 14 | `U2` | 5.78 | 5 → 6 | Farther | 19 | 88.68 |
| 15 | `U2` | 5.81 | 6 → 5 | Closer | 16 | 94.49 |
| 16 | `U2` | 5.79 | 5 → 6 | Farther | 19 | 100.28 |
| 17 | `U2` | 6.19 | 6 → 5 | Closer | 16 | 106.47 |
| 18 | `U2` | 7.27 | 5 → 6 | Farther | 19 | 113.74 |
| 19 | `U2` | 7.45 | 6 → 5 | Closer | 16 | 121.19 |
| 20 | `U2` | 6.98 | 5 → 6 | Farther | 19 | 128.17 |

</details>

**Gemma 3 1B action sequence:** `U2` `U'` `U2` `U2` `U2` `U2` `B2` `U2` `U2` `U2` `U2` `U2` `U2` `U2` `U2` `U2` `U2` `U2` `U2` `U2`


## 11. Reporting checklist

- [x] Same puzzle and verified three-turn optimal distance for all four local models.
- [x] Model names and exact Ollama IDs listed.
- [x] Twenty-move limit and 20-minute time cap stated.
- [x] Unassisted mode and zero guided overrides disclosed.
- [x] Success, move count, live decision latency, wall time, and recorded cost discussed.
- [x] Per-move distance diagnostics, request counts, invalid outputs, and cache hits included.
- [x] Five assignment questions answered with appropriate qualifications.
- [x] Original trials and move CSV files linked and supplied.
- [ ] Repeat the experiment on more independent seeds to make broader quality comparisons.
- [ ] If the teacher's OpenRouter key becomes available, report that separate **hosted** experiment under its own request limits and cache ledger.
- [x] Attach the supplied demo highlight recording to the repository.
- [ ] Add the retained full JSON result if available; it was not provided with the CSV exports.

---

**Report conclusion:** In this **single, real local Ollama experiment**, all four models returned legal moves, but **none solved a cube with an exact three-turn solution**. Gemma was quickest to choose moves, while Clef reached the nearest observed position but timed out. The major observed failure mode was **repetitive or counterproductive action selection**, not output-format validation. This report preserves that negative result rather than manufacturing a successful solve.
