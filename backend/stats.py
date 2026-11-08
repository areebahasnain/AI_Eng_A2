"""Aggregate benchmark statistics and the auto-drafted answers to the five questions."""
from __future__ import annotations

import statistics
from typing import Iterable


def _mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, round(q * (len(s) - 1))))
    return s[k]


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def rank_trials(trials: list[dict]) -> list[str]:
    """Order model keys for ONE puzzle: solved first (fewer moves, then faster),
    then unsolved by most facelets correct, then faster."""

    def key(t: dict):
        if t["solved"]:
            return (0, t["moves_used"], t["total_time_s"], 0)
        return (1, -t.get("final_correct_facelets", 0), t["total_time_s"], t["moves_used"])

    return [t["model_key"] for t in sorted(trials, key=key)]


def model_stats(spec: dict, trials: list[dict]) -> dict:
    # Solver-guided local demonstrations must never inflate model solve rates.
    # They are counted separately from unassisted, comparable experiments.
    unassisted = [t for t in trials if not t.get("assisted_mode", False)]
    assisted = [t for t in trials if t.get("assisted_mode", False)]
    n = len(unassisted)
    solved = [t for t in unassisted if t["solved"]]
    ok_lat = [turn["latency_ms"] for t in trials for turn in t["turn_log"] if turn["ok"]]
    last_lat = [turn["last_attempt_ms"] for t in trials for turn in t["turn_log"] if turn["ok"]]
    live_lat = [turn.get("live_latency_ms", 0) / (turn.get("api_calls", 0) + turn.get("local_requests", 0))
                for t in trials for turn in t["turn_log"]
                if turn.get("api_calls", 0) + turn.get("local_requests", 0)]
    cache_lat = [turn.get("cache_latency_ms", 0) / turn.get("cache_hits", 1)
                 for t in trials for turn in t["turn_log"] if turn.get("cache_hits", 0)]
    gaps = [t["gap"] for t in solved if t.get("gap") is not None]
    exact_gaps = [t["gap"] for t in solved if t.get("gap") is not None and t.get("gap_exact")]
    costs = [t["cost_usd"] for t in trials if t.get("cost_usd") is not None]
    return {
        "key": spec["key"],
        "name": spec["name"],
        "model_id": spec["model_id"],
        "category": spec["category"],
        "trials": n,
        "assisted_trials": len(assisted),
        "assisted_solved": sum(1 for t in assisted if t["solved"]),
        "assisted_overrides": sum(t.get("guide_overrides", 0) for t in assisted),
        "solved": len(solved),
        "success_rate": _r(100.0 * len(solved) / n, 1) if n else None,
        "decisions": len(ok_lat),
        "avg_move_latency_ms": _r(_mean(ok_lat), 1),
        "median_move_latency_ms": _r(_pct(ok_lat, 0.5), 1),
        "p95_move_latency_ms": _r(_pct(ok_lat, 0.95), 1),
        "avg_http_latency_ms": _r(_mean(last_lat), 1),
        "avg_live_request_ms": _r(_mean(live_lat), 2),
        "avg_cached_response_ms": _r(_mean(cache_lat), 2),
        "median_live_request_ms": _r(_pct(live_lat, 0.5), 2),
        "p95_live_request_ms": _r(_pct(live_lat, 0.95), 2),
        "api_calls": sum(t.get("api_calls", 0) for t in trials),
        "cache_hits": sum(t.get("cache_hits", 0) for t in trials),
        "local_requests": sum(t.get("local_requests", 0) for t in trials),
        "total_time_s": _r(sum(t["total_time_s"] for t in trials), 2),
        "avg_trial_time_s": _r(_mean([t["total_time_s"] for t in trials]), 2),
        "avg_solve_time_s": _r(_mean([t["total_time_s"] for t in solved]), 2),
        "total_moves": sum(t["moves_used"] for t in trials),
        "avg_moves": _r(_mean([t["moves_used"] for t in trials]), 2),
        "avg_moves_solved": _r(_mean([t["moves_used"] for t in solved]), 2),
        "avg_gap": _r(_mean(gaps), 2),
        "avg_gap_exact": _r(_mean(exact_gaps), 2),
        "gap_samples": len(gaps),
        "gap_exact_samples": len(exact_gaps),
        "optimal_solves": sum(1 for t in solved if t.get("gap") == 0 and t.get("gap_exact")),
        "avg_final_correct_facelets": _r(_mean([t["final_correct_facelets"] for t in trials]), 1),
        "invalid_outputs": sum(t["invalid_outputs"] for t in trials),
        "retries": sum(t["retries"] for t in trials),
        "failed_turns": sum(t["failed_turns"] for t in trials),
        "timeouts": sum(1 for t in trials if t["status"] == "OUT_OF_TIME"),
        "ran_out_of_moves": sum(1 for t in trials if t["status"] == "RAN_OUT_OF_MOVES"),
        "errors": sum(1 for t in trials if t["status"] == "ERROR"),
        "total_cost_usd": _r(sum(costs), 5) if costs else None,
    }


def _fmt(x, unit="", nd=None):
    if x is None:
        return "n/a"
    return f"{x:.{nd}f}{unit}" if nd is not None else f"{x}{unit}"


def build_analysis(stats: list[dict]) -> dict:
    """Draft answers to the five required questions, computed from the data."""
    # Never let an instant cache lookup make a model appear faster than a
    # genuinely measured inference call. Pure cache replays have no new speed data.
    any_live = any(s["avg_live_request_ms"] is not None for s in stats)
    cached_without_live = not any_live and any(s["cache_hits"] for s in stats)
    for s in stats:
        s["comparison_latency_ms"] = (s["avg_live_request_ms"] if any_live else
                                      None if cached_without_live else s["avg_move_latency_ms"])
    with_lat = [s for s in stats if s["comparison_latency_ms"] is not None]
    out: dict = {}
    speed_label = "live request" if any_live else "simulated move"

    # Q1 - fastest decisions: use fresh live requests, never cache lookup timing.
    if with_lat:
        ordered = sorted(with_lat, key=lambda s: s["comparison_latency_ms"])
        fast = ordered[0]
        slow = ordered[-1]
        ratio = (slow["comparison_latency_ms"] / fast["comparison_latency_ms"]) if fast["comparison_latency_ms"] else None
        out["q1"] = {
            "question": "Which model is fastest in terms of making decisions?",
            "answer": f"{fast['name']} - average {_fmt(fast['comparison_latency_ms'], ' ms')} per {speed_label} "
            f"(median {_fmt(fast['median_live_request_ms'] if any_live else fast['median_move_latency_ms'], ' ms')}, "
            f"p95 {_fmt(fast['p95_live_request_ms'] if any_live else fast['p95_move_latency_ms'], ' ms')})."
            + (f" That is about {ratio:.1f}x faster than the slowest model, {slow['name']}." if ratio and len(ordered) > 1 else ""),
            "evidence": [f"{s['name']}: {_fmt(s['comparison_latency_ms'], ' ms')} avg / move" for s in ordered],
            "winner": fast["key"],
        }
    else:
        out["q1"] = {"question": "Which model is fastest in terms of making decisions?",
                     "answer": "No fresh inference latency available (models failed or this was a cached replay), so speed cannot be compared.", "evidence": [], "winner": None}

    # Q2 - highest solve rate
    rated = [s for s in stats if s["success_rate"] is not None]
    if rated:
        top = max(s["success_rate"] for s in rated)
        winners = [s for s in rated if s["success_rate"] == top]
        names = " and ".join(s["name"] for s in winners)
        out["q2"] = {
            "question": "Which model achieved the highest solve rate?",
            "answer": f"{names} - {top:.0f}% of puzzles solved within the move limit"
            + (" (tie)." if len(winners) > 1 else "."),
            "evidence": [f"{s['name']}: {s['solved']}/{s['trials']} solved ({s['success_rate']:.0f}%)" for s in
                         sorted(rated, key=lambda s: -s["success_rate"])],
            "winner": winners[0]["key"] if len(winners) == 1 else None,
        }
    else:
        out["q2"] = {"question": "Which model achieved the highest solve rate?", "answer": "No trials recorded.",
                     "evidence": [], "winner": None}

    # Q3 - shortest solutions / closeness to optimum
    gapped = [s for s in stats if s["avg_gap"] is not None]
    exact_all = all(s["gap_samples"] == s["gap_exact_samples"] for s in gapped) if gapped else True
    if gapped:
        best = min(gapped, key=lambda s: (s["avg_gap"], s["avg_moves_solved"] or 0))
        out["q3"] = {
            "question": "Which model found the shortest solutions, and how close were they to the known optimum?",
            "answer": f"{best['name']} - on puzzles it solved it averaged {_fmt(best['avg_moves_solved'])} moves, "
            f"an optimality gap of {best['avg_gap']:+.2f} moves on average; "
            f"{best['optimal_solves']} of its {best['solved']} solves were exactly optimal."
            + ("" if exact_all else " (Some puzzles have no exact optimum - scramble length was used as an upper bound there.)"),
            "evidence": [
                f"{s['name']}: avg {_fmt(s['avg_moves_solved'])} moves on solved puzzles, gap {s['avg_gap']:+.2f}, "
                f"{s['optimal_solves']}/{s['solved']} optimal"
                for s in sorted(gapped, key=lambda s: s["avg_gap"])
            ]
            + [f"{s['name']}: no solved puzzles, gap undefined" for s in stats if s["avg_gap"] is None],
            "note": "The gap is averaged over solved puzzles only, so a model that rarely solves can still have a small gap - read it together with success rate.",
            "winner": best["key"],
        }
    else:
        out["q3"] = {"question": "Which model found the shortest solutions, and how close were they to the known optimum?",
                     "answer": "No model solved any puzzle, so there is no optimality gap to report.",
                     "evidence": [], "winner": None}

    # Q4 - did the fastest model also achieve the best quality?
    def quality_key(s):
        return (-(s["success_rate"] or 0), s["avg_gap"] if s["avg_gap"] is not None else 99)

    if with_lat and rated:
        fastest = min(with_lat, key=lambda s: s["comparison_latency_ms"])
        best_q = min(rated, key=quality_key)
        tied_best = [s for s in rated if quality_key(s) == quality_key(best_q)]
        if fastest["key"] in {s["key"] for s in tied_best}:
            ans = (f"Yes - {fastest['name']} was both the fastest ({_fmt(fastest['comparison_latency_ms'], ' ms')} / move) "
                   f"and (jointly) the best on solution quality ({fastest['success_rate']:.0f}% solved).")
        else:
            ans = (f"No - {fastest['name']} was fastest ({_fmt(fastest['comparison_latency_ms'], ' ms')} / move) but solved "
                   f"{fastest['success_rate']:.0f}% with avg gap {_fmt(fastest['avg_gap'])}, while {best_q['name']} had the best quality "
                   f"({best_q['success_rate']:.0f}% solved, avg gap {_fmt(best_q['avg_gap'])}) at {_fmt(best_q['comparison_latency_ms'], ' ms')} / move.")
        out["q4"] = {"question": "Did the fastest model also achieve the best solution quality?", "answer": ans,
                     "evidence": [], "winner": None}
    else:
        out["q4"] = {"question": "Did the fastest model also achieve the best solution quality?",
                     "answer": "Not enough data.", "evidence": [], "winner": None}

    # Q5 - what would you use?
    ev = []
    for s in stats:
        solved = s["solved"]
        per_solve = (s["total_time_s"] / solved) if solved and s["total_time_s"] is not None else None
        ev.append(f"{s['name']}: {s['success_rate'] if s['success_rate'] is not None else 'n/a'}% solved, "
                  f"{_fmt(s['comparison_latency_ms'], ' ms')} / move, "
                  f"{_fmt(per_solve, ' s', 1)} of wall time per solved puzzle, "
                  f"{s['invalid_outputs']} invalid outputs, cost {_fmt(s['total_cost_usd'], ' USD')}")
    if with_lat and rated and max(s["success_rate"] for s in rated) > 0:
        fastest = min(with_lat, key=lambda s: s["comparison_latency_ms"])
        best_q = min(rated, key=quality_key)
        if fastest["key"] == best_q["key"]:
            rec = (f"Use {fastest['name']}: it was both fastest and best in this benchmark, so there is no trade-off to hedge.")
        elif fastest["category"] == "decision" and best_q["category"] == "llm":
            rec = ("Use a hybrid agent: let the fast decision model make routine moves and escalate to the frontier LLM "
                   "when its confidence is low or progress stalls. The data shows a real trade-off - "
                   f"{fastest['name']} is far quicker per move, while {best_q['name']} solved more puzzles.")
        elif fastest["category"] == "llm" and best_q["category"] == "decision":
            rec = (f"Use {best_q['name']}: it solved the most puzzles and the frontier LLM was not even faster here.")
        else:
            rec = (f"Prefer {best_q['name']} for quality ({best_q['success_rate']:.0f}% solved) and consider "
                   f"{fastest['name']} where latency matters most.")
    else:
        rec = "No model solved a puzzle in this run, so no recommendation is supported yet - run the primary benchmark with live models."
    out["q5"] = {
        "question": "Would you use the fastest decision model, the frontier LLM, or a hybrid agent in a real-world application? What evidence supports your choice?",
        "answer": rec,
        "evidence": ev,
        "note": "This is an auto-drafted starting point computed from the numbers. Rewrite it in your own words in the report.",
        "winner": None,
    }
    return out


def summarize(results: list[dict], model_specs: Iterable[dict]) -> dict:
    specs = list(model_specs)
    stats = [model_stats(sp, [t for t in results if t["model_key"] == sp["key"]]) for sp in specs]
    stats = [s for s in stats if s["trials"] > 0]
    return {"models": stats, "analysis": build_analysis(stats)}
