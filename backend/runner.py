"""Benchmark runner: same scrambled cube for every model, one decision per turn.

Experiment protocol (identical for all models)
----------------------------------------------
* Every model starts each puzzle from the *same* seeded scramble.
* A *turn* is one request for a move.  A valid move is applied by the engine.  A turn
  whose answer is unusable even after retries (malformed JSON, illegal move, HTTP
  error, timeout) is logged and counted but changes nothing; it still uses up one of
  the ``max_moves`` turns, so reaching the limit is always an unsuccessful attempt.
* A trial ends as SOLVED, RAN_OUT_OF_MOVES, OUT_OF_TIME (wall-clock limit), or ERROR
  (too many consecutive failed turns, or a fatal API error).
* Per-move latency = wall time from sending the request until an accepted answer,
  including any retries and back-off.  Total time = wall time of the whole trial.
"""
from __future__ import annotations

import asyncio
import json
import random
import secrets
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .adapters import make_adapter
from .config import ROOT, SUITES, Settings
from .ledger import APILedger
from .contract import build_game_state
from .cube import apply_move, correct_facelets, faces_solved, generate_scramble, is_solved, scramble_state
from .solver import shortest_path_cached
from .progress import (EXACT_DISTANCE_HORIZON, exact_local_distance,
                       measure_progress, local_cycle_observation,
                       one_step_sticker_observation, repeated_closed_loop)
from .stats import rank_trials, summarize
from .guidance import optimal_next_moves, choose_guided_move

RESULTS_DIR = ROOT / "results"
EXACT_SEARCH_MAX_SCRAMBLE = 8  # exact optimum is computed for scrambles up to this length


class RunFatal(Exception):
    """An error that makes continuing pointless for every model (bad key, no credits)."""


class Run:
    def __init__(self, request: dict, settings: Settings, model_keys: list[str]):
        self.id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        self.request = request
        self.settings = settings
        self.model_keys = model_keys
        self.status = "pending"  # pending | running | done | stopped | error
        self.error: str | None = None
        self.events: list[dict] = []
        self.puzzles: list[dict] = []
        self.results: list[dict] = []
        self.summary: dict | None = None
        self.task: asyncio.Task | None = None
        self.started_at: float | None = None
        self.usage_before: dict | None = None
        self.usage_after: dict | None = None

    @property
    def finished(self) -> bool:
        return self.status in {"done", "stopped", "error"}

    def emit(self, type_: str, **data: Any) -> None:
        self.events.append({"type": type_, "ts": time.time(), **data})

    def specs(self) -> list[dict]:
        m = self.settings.model_map()
        return [asdict(m[k]) for k in self.model_keys]

    def to_dict(self, include_events: bool = False) -> dict:
        d = {
            "id": self.id,
            "status": self.status,
            "error": self.error,
            "mock": self.settings.mock,
            "request": self.request,
            "limits": self.settings.public_dict()["limits"],
            "models": self.specs(),
            "puzzles": self.puzzles,
            "results": self.results,
            "summary": self.summary,
            "usage_before": self.usage_before,
            "usage_after": self.usage_after,
        }
        if include_events:
            d["events"] = self.events
        return d


def build_puzzles(suite: str, n: int, seed: int, scramble_len: int | None) -> list[dict]:
    """Each generated starting state is EXACTLY three face turns from solved."""
    if suite not in {*SUITES, "custom"}:
        raise ValueError(f"Unknown suite {suite!r}")
    if scramble_len is not None and int(scramble_len) != 3:
        raise ValueError("Teacher's protocol requires EXACTLY 3 moves from solved.")
    rng = random.Random(f"{suite}-{seed}")
    puzzles = []
    for i in range(n):
        for _ in range(5000):
            scramble = generate_scramble(3, rng)
            state = scramble_state(scramble)
            path = shortest_path_cached(state, 3)
            if path is not None and len(path) == 3:
                break
        else:
            raise RuntimeError("Could not generate an exact-3-move cube")
        puzzles.append({
            "id": f"{suite}-{seed}-{i + 1}", "index": i + 1,
            "suite": suite, "scramble": scramble,
            "scramble_len": 3, "state": state,
            "optimal": 3, "optimal_exact": True, "reference_len": 3,
        })
    return puzzles


async def attach_optimal(puzzle: dict) -> None:
    """Exact shortest distance via BFS when feasible; else scramble length as an upper bound."""
    n = puzzle["scramble_len"]
    if n <= EXACT_SEARCH_MAX_SCRAMBLE:
        path = await asyncio.to_thread(shortest_path_cached, puzzle["state"], n)
        if path is not None:
            puzzle["optimal"] = len(path)
            puzzle["optimal_exact"] = True
            puzzle["reference_len"] = len(path)
            return
    puzzle["optimal"] = None
    puzzle["optimal_exact"] = False
    puzzle["reference_len"] = n  # upper bound: the optimum is <= scramble length


async def play_trial(run: Run, puzzle: dict, spec_key: str, adapter) -> dict:
    s = run.settings
    spec = s.model_map()[spec_key]
    state = puzzle["state"]
    t0 = time.perf_counter()
    applied: list[str] = []
    turn_log: list[dict] = []
    status: str | None = None
    error: str | None = None
    consecutive_failures = 0
    invalid_total = retries_total = failed_turns = 0
    api_calls_total = cache_hits_total = local_requests_total = 0
    live_latency_total = cache_latency_total = 0.0
    cost_total = 0.0
    saw_cost = False
    diagnose_local = s.provider == "ollama" and not s.mock
    guided = diagnose_local and bool(run.request.get("ollama_guided", False))
    guided_distance = 3  # the generated state is proven exactly 3 moves from solved
    guide_overrides = 0
    guide_accepted = 0
    previous_distance = 3 if diagnose_local else None  # generated puzzle is proven exact-3
    progress_counts = {"closer": 0, "farther": 0, "same": 0, "unknown": 0}
    # State-memory feedback is local-only. No solved-distance oracle enters prompts.
    state_history = [state] if diagnose_local else []
    seen_states = {state} if diagnose_local else set()
    repeat_visits = 0

    trial_limit = min(s.max_moves, 5 if spec_key == "opus" else 20)
    for turn in range(1, trial_limit + 1):
        elapsed = time.perf_counter() - t0
        remaining = s.time_limit_s - elapsed
        if remaining <= 0:
            status = "OUT_OF_TIME"
            break
        run.emit("model_thinking", puzzle=puzzle["index"], model=spec_key, turn=turn)
        game_state = build_game_state(
            state, applied[-s.recent_window :] if s.recent_window else [], trial_limit - turn + 1,
            readable_grids=diagnose_local,
        )
        if diagnose_local:
            # Cheap one-step memory; no lookahead solver in unassisted mode.
            game_state.update(local_cycle_observation(state, seen_states))
            if s.ollama_sticker_hints:
                game_state.update(one_step_sticker_observation(state, seen_states))
        candidates = []
        if guided:
            # This is intentionally SOLVER ASSISTANCE, not model ability.
            # A later action guard can override an incorrect model proposal.
            candidates = await asyncio.to_thread(optimal_next_moves, state, guided_distance)
            game_state["solver_guided_demo"] = True
            game_state["distance_reducing_choices"] = candidates
            game_state["guided_disclosure"] = (
                "This is a SOLVER-ASSISTED LOCAL DEMO, not an unassisted benchmark. "
                "Propose one move from distance_reducing_choices. The engine may "
                "replace your proposal if it does not reduce exact distance."
            )
        try:
            decision = await asyncio.wait_for(adapter.decide(game_state), timeout=remaining)
        except asyncio.TimeoutError:
            status = "OUT_OF_TIME"
            break

        api_calls_total += decision.api_calls
        cache_hits_total += decision.cache_hits
        local_requests_total += decision.local_requests
        live_latency_total += decision.live_latency_ms
        cache_latency_total += decision.cache_latency_ms
        invalid_total += decision.invalid_outputs
        retries_total += decision.retries
        if decision.cost_usd is not None:
            cost_total += decision.cost_usd
            saw_cost = True
        entry = {
            "turn": turn,
            "move": decision.move,
            "ok": decision.ok,
            "latency_ms": round(decision.latency_ms, 1),
            "last_attempt_ms": round(decision.last_attempt_ms, 1),
            "attempts": decision.attempts,
            "api_calls": decision.api_calls,
            "cache_hits": decision.cache_hits,
            "local_requests": decision.local_requests,
            "live_latency_ms": round(decision.live_latency_ms, 2),
            "cache_latency_ms": round(decision.cache_latency_ms, 2),
            "retries": decision.retries,
            "invalid_outputs": decision.invalid_outputs,
            "error": decision.error,
            "confidence": decision.confidence,
            "probability": decision.probability,
            "cost_usd": decision.cost_usd,
            "http_status": decision.http_status,
            "elapsed_s": round(time.perf_counter() - t0, 3),
        }

        if decision.fatal_scope == "run":
            turn_log.append(entry)
            raise RunFatal(f"{spec.name}: {decision.error}")

        # For an explicitly assisted demo only, a malformed LOCAL model answer
        # may be replaced with a *solver-only* move. That is not model success;
        # it is labelled separately and excluded from model solve-rate statistics.
        solver_only_fallback = (guided and not decision.ok and
                                decision.invalid_outputs > 0 and
                                decision.fatal_scope is None)
        if not decision.ok and not solver_only_fallback:
            failed_turns += 1
            consecutive_failures += 1
            entry["correct_facelets"] = correct_facelets(state)
            turn_log.append(entry)
            run.emit("turn_failed", puzzle=puzzle["index"], model=spec_key, **entry)
            if decision.fatal_scope in ("model", "quota"):
                status, error = ("CALL_LIMIT" if decision.fatal_scope == "quota" else "ERROR"), decision.error
                break
            if consecutive_failures >= s.max_consecutive_failures:
                status = "ERROR"
                error = f"{consecutive_failures} consecutive failed decisions: {decision.error}"
                break
            continue

        consecutive_failures = 0
        proposed_move = decision.move
        applied_move = decision.move
        if solver_only_fallback:
            failed_turns += 1
            applied_move = candidates[0]
            guide_overrides += 1
            entry["model_proposed_move"] = None
            entry["guide_overrode"] = True
            entry["model_response_ok"] = False
            entry["distance_reducing_choices"] = candidates
            entry["move_source"] = "solver_only_fallback"
            entry["move"] = applied_move
            guided_distance -= 1
        elif guided:
            applied_move, overridden = choose_guided_move(proposed_move, candidates)
            guide_overrides += int(overridden)
            guide_accepted += int(not overridden)
            entry["model_proposed_move"] = proposed_move
            entry["guide_overrode"] = overridden
            entry["distance_reducing_choices"] = candidates
            entry["move_source"] = "reference_guard" if overridden else "model"
            entry["model_response_ok"] = True
            entry["move"] = applied_move
            guided_distance -= 1
        state = apply_move(state, applied_move)
        applied.append(applied_move)
        solved = is_solved(state)
        loop_length = None
        if diagnose_local:
            revisited = state in seen_states
            entry["revisited_state"] = revisited
            entry["cycle_length"] = (len(state_history) - 1 -
                                     max(i for i, old in enumerate(state_history) if old == state)) if revisited else None
            repeat_visits += int(revisited)
            seen_states.add(state)
            state_history.append(state)
            # A-B-A-B-A means the same closed sequence has been repeated twice.
            # Stop this LOCAL trial as unsolved; never substitute a solver move.
            loop_length = repeated_closed_loop(state_history, applied)
        if diagnose_local:
            # Exact bounded shortest-path evaluation is *after* the model's answer
            # and is never included in subsequent model prompts.
            next_distance = await asyncio.to_thread(exact_local_distance, state)
            diagnostic = measure_progress(previous_distance, next_distance)
            entry.update(diagnostic)
            progress_counts[diagnostic["distance_change"]] += 1
            previous_distance = next_distance
        entry["correct_facelets"] = correct_facelets(state)
        entry["state_after"] = state  # lets the UI replay a saved run without a cube engine
        turn_log.append(entry)
        run.emit(
            "move",
            puzzle=puzzle["index"],
            model=spec_key,
            state=state,
            solved=solved,
            faces_solved=faces_solved(state),
            moves_used=len(applied),
            **entry,
        )
        if solved:
            status = "SOLVED"
            break
        if loop_length is not None:
            run.emit("loop_detected", puzzle=puzzle["index"], model=spec_key,
                     loop_length=loop_length, moves_used=len(applied))
            # Off by default: teacher's benchmark gives every model up to 20 moves.
            # Optional early stop saves local diagnostic time, but that variant
            # must NOT be reported as the standard 20-move comparison.
            if s.ollama_stop_on_repeat_loop:
                status = "STALLED_LOOP"
                error = (f"Repeated the same {loop_length}-move closed loop twice; "
                         "stopped without changing any model decision.")
                break

    if status is None:
        status = "RAN_OUT_OF_MOVES"

    total = time.perf_counter() - t0
    if status == "OUT_OF_TIME":
        total = max(total, 0.0)
    solved = status == "SOLVED"
    gap = (len(applied) - puzzle["reference_len"]) if solved else None
    ok_lat = [t["latency_ms"] for t in turn_log if t["ok"]]
    result = {
        "puzzle_id": puzzle["id"],
        "puzzle_index": puzzle["index"],
        "model_key": spec_key,
        "assisted_mode": guided,
        "guide_overrides": guide_overrides,
        "guide_accepted": guide_accepted,
        "model_name": spec.name,
        "model_id": spec.model_id,
        "category": spec.category,
        "status": status,
        "solved": solved,
        "error": error,
        "turns": len(turn_log),
        "turn_limit": trial_limit,
        "api_calls": api_calls_total,
        "cache_hits": cache_hits_total,
        "local_requests": local_requests_total,
        "live_latency_ms": round(live_latency_total, 2),
        "cache_latency_ms": round(cache_latency_total, 2),
        "moves_used": len(applied),
        "moves": applied,
        "total_time_s": round(total, 3),
        "avg_move_latency_ms": round(sum(ok_lat) / len(ok_lat), 1) if ok_lat else None,
        "invalid_outputs": invalid_total,
        "retries": retries_total,
        "failed_turns": failed_turns,
        "scramble_len": puzzle["scramble_len"],
        "optimal": puzzle["optimal"],
        "optimal_exact": puzzle["optimal_exact"],
        "reference_len": puzzle["reference_len"],
        "gap": gap,
        "gap_exact": bool(puzzle["optimal_exact"]) if solved else None,
        "final_correct_facelets": correct_facelets(state),
        "final_state": state,
        "distance_horizon": EXACT_DISTANCE_HORIZON if diagnose_local else None,
        "final_exact_distance": previous_distance if diagnose_local else None,
        "progress_counts": progress_counts if diagnose_local else None,
        "revisited_states": repeat_visits if diagnose_local else None,
        "cycle_aware_prompt": diagnose_local,
        "solver_guided_demo": guided,
        "sticker_scorecard": diagnose_local and s.ollama_sticker_hints,
        "cost_usd": round(cost_total, 6) if saw_cost else None,
        "turn_log": turn_log,
    }
    run.results.append(result)
    run.emit("model_done", puzzle=puzzle["index"], model=spec_key, result=_light(result))
    return result


def _light(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in {"turn_log", "final_state"}}


async def _gather_or_cancel(coros) -> list:
    tasks = [asyncio.create_task(c) for c in coros]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def save_run(run: Run) -> Path | None:
    try:
        RESULTS_DIR.mkdir(exist_ok=True)
        path = RESULTS_DIR / f"run-{run.id}.json"
        path.write_text(json.dumps(run.to_dict(include_events=False), indent=2))
        return path
    except OSError:
        return None


async def execute(run: Run) -> None:
    s = run.settings
    client: httpx.AsyncClient | None = None
    adapters: dict = {}
    ledger: APILedger | None = None
    try:
        req = run.request
        run.status = "running"
        run.started_at = time.time()
        puzzles = build_puzzles(req["suite"], req["n_puzzles"], req["seed"], req.get("scramble_len"))
        for p in puzzles:
            await attach_optimal(p)
        run.puzzles = puzzles

        if s.provider != "mock" and not s.mock:
            client = httpx.AsyncClient(
                timeout=s.request_timeout_s, limits=httpx.Limits(max_connections=32)
            )
            if s.provider == "openrouter":
                ledger = APILedger(s.ledger_path)
                run.usage_before = ledger.snapshot()
        specs = s.model_map()
        adapters = {k: make_adapter(specs[k], s, client, ledger=ledger) for k in run.model_keys}

        run.emit(
            "run_started",
            run_id=run.id,
            mock=s.mock,
            request=run.request,
            limits=s.public_dict()["limits"],
            models=run.specs(),
            puzzles=[dict(p) for p in puzzles],
        )

        for puzzle in puzzles:
            run.emit("puzzle_started", puzzle=puzzle["index"], total=len(puzzles), data={
                k: puzzle[k] for k in ("id", "index", "scramble", "scramble_len", "state",
                                       "optimal", "optimal_exact", "reference_len")
            })
            coros = [play_trial(run, puzzle, k, adapters[k]) for k in run.model_keys]
            if req.get("parallel", True):
                trials = await _gather_or_cancel(coros)
            else:
                trials = []
                for c in coros:
                    trials.append(await c)
            ranking = rank_trials(trials)
            run.emit("puzzle_done", puzzle=puzzle["index"], ranking=ranking,
                     results=[_light(t) for t in trials])

        run.summary = summarize(run.results, run.specs())
        run.status = "done"
        if ledger: run.usage_after = ledger.snapshot()
        path = save_run(run)
        run.emit("run_done", summary=run.summary, saved=path.name if path else None)
    except asyncio.CancelledError:
        run.status = "stopped"
        run.summary = summarize(run.results, run.specs()) if run.results else None
        if ledger: run.usage_after = ledger.snapshot()
        save_run(run)
        run.emit("run_stopped", summary=run.summary)
    except RunFatal as exc:
        run.status = "error"
        run.error = str(exc)
        run.summary = summarize(run.results, run.specs()) if run.results else None
        if ledger: run.usage_after = ledger.snapshot()
        save_run(run)
        run.emit("run_error", message=run.error, summary=run.summary)
    except Exception as exc:  # pragma: no cover - defensive
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"
        if ledger: run.usage_after = ledger.snapshot()
        save_run(run)
        run.emit("run_error", message=run.error, summary=None)
    finally:
        for a in adapters.values():
            try:
                await a.aclose()
            except Exception:  # pragma: no cover
                pass
        if client is not None:
            await client.aclose()
