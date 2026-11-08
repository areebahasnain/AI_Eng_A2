import asyncio

from backend.config import load_settings
from backend.cube import MOVES, apply_moves, is_solved
from backend.runner import Run, build_puzzles, attach_optimal, execute
from backend.solver import distance
from backend.stats import rank_trials


def fast_settings(**kw):
    s = load_settings()
    s.mock = True
    s.mock_speed = 5000.0
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def do_run(settings, **req):
    request = dict(suite="warmup", n_puzzles=2, seed=11, scramble_len=None, parallel=True)
    request.update(req)
    run = Run(request, settings, [m.key for m in settings.models])

    async def go():
        await execute(run)

    asyncio.run(go())
    return run


def test_puzzles_are_deterministic_and_unsolved():
    a = build_puzzles("primary", 5, 123, None)
    b = build_puzzles("primary", 5, 123, None)
    assert a == b
    assert [p["scramble_len"] for p in a] == [3] * 5
    assert all(not is_solved(p["state"]) for p in a)
    assert all(distance(p["state"]) == 3 for p in a)
    assert build_puzzles("primary", 5, 124, None) != a


def test_suite_lengths():
    assert {p["scramble_len"] for p in build_puzzles("warmup", 6, 1, None)} == {3}
    assert {p["scramble_len"] for p in build_puzzles("extension", 12, 1, None)} == {3}
    assert build_puzzles("custom", 2, 1, 3)[0]["scramble_len"] == 3


def test_exact_optimum_attached_for_small_and_bound_for_large():
    small = build_puzzles("primary", 3, 5, None)
    for p in small:
        asyncio.run(attach_optimal(p))
        assert p["optimal_exact"] and p["optimal"] == distance(p["state"]) <= p["scramble_len"]
        assert p["reference_len"] == p["optimal"]
    big = build_puzzles("extension", 1, 5, None)[0]
    asyncio.run(attach_optimal(big))
    assert big["optimal_exact"] and big["optimal"] == 3


def test_full_mock_run_is_consistent():
    run = do_run(fast_settings(), n_puzzles=3)
    assert run.status == "done" and run.summary
    assert len(run.results) == 3 * 4

    types = [e["type"] for e in run.events]
    assert types[0] == "run_started" and types[-1] == "run_done"
    assert types.count("puzzle_started") == 3 and types.count("puzzle_done") == 3

    by_puzzle = {}
    for r in run.results:
        by_puzzle.setdefault(r["puzzle_index"], []).append(r)
        assert r["turns"] <= run.settings.max_moves
        assert r["moves_used"] <= r["turns"]
        assert all(m in MOVES for m in r["moves"])
        # Replaying the recorded moves on the puzzle reproduces the recorded outcome.
        puzzle = run.puzzles[r["puzzle_index"] - 1]
        final = apply_moves(puzzle["state"], r["moves"])
        assert final == r["final_state"]
        assert is_solved(final) == r["solved"] == (r["status"] == "SOLVED")
        if r["solved"]:
            assert r["gap"] == r["moves_used"] - puzzle["optimal"] >= 0
        else:
            assert r["gap"] is None
        assert r["total_time_s"] >= 0
    # every model got the same puzzle
    for rs in by_puzzle.values():
        assert len({r["puzzle_id"] for r in rs}) == 1 and len(rs) == 4


def test_move_limit_marks_unsolved_attempts():
    run = do_run(fast_settings(max_moves=1), n_puzzles=2, suite="primary")
    for r in run.results:
        assert r["turns"] <= 1
        if not r["solved"]:
            assert r["status"] == "RAN_OUT_OF_MOVES"


def test_time_limit_produces_out_of_time():
    s = fast_settings(time_limit_s=0.05, mock_speed=1.0)
    run = do_run(s, n_puzzles=1, suite="primary")
    assert any(r["status"] == "OUT_OF_TIME" for r in run.results)
    for r in run.results:
        if r["status"] == "OUT_OF_TIME":
            assert not r["solved"] and r["total_time_s"] >= 0.04


def test_sequential_mode_runs_every_trial():
    run = do_run(fast_settings(), n_puzzles=2, parallel=False)
    assert run.status == "done" and len(run.results) == 8


def test_summary_statistics_match_the_trials():
    run = do_run(fast_settings(), n_puzzles=4, suite="primary")
    for ms in run.summary["models"]:
        trials = [r for r in run.results if r["model_key"] == ms["key"]]
        solved = [t for t in trials if t["solved"]]
        assert ms["trials"] == len(trials) == 4
        assert ms["solved"] == len(solved)
        assert ms["success_rate"] == round(100 * len(solved) / len(trials), 1)
        assert ms["total_moves"] == sum(t["moves_used"] for t in trials)
        lat = [turn["latency_ms"] for t in trials for turn in t["turn_log"] if turn["ok"]]
        assert ms["avg_move_latency_ms"] == round(sum(lat) / len(lat), 1)
        if solved:
            gaps = [t["gap"] for t in solved]
            assert ms["avg_gap"] == round(sum(gaps) / len(gaps), 2)
    for q in ("q1", "q2", "q3", "q4", "q5"):
        assert run.summary["analysis"][q]["answer"]


def test_ranking_puts_solved_first_then_fewer_moves():
    trials = [
        dict(model_key="a", solved=False, moves_used=5, total_time_s=1, final_correct_facelets=40),
        dict(model_key="b", solved=True, moves_used=5, total_time_s=9, final_correct_facelets=54),
        dict(model_key="c", solved=True, moves_used=3, total_time_s=30, final_correct_facelets=54),
        dict(model_key="d", solved=False, moves_used=5, total_time_s=1, final_correct_facelets=48),
    ]
    assert rank_trials(trials) == ["c", "b", "d", "a"]


def test_claude_trial_stops_after_five_moves_even_if_global_limit_is_twenty():
    from backend.adapters import Decision
    from backend.runner import play_trial
    class AlwaysU:
        async def decide(self, game_state):
            return Decision('U', True, 0.1, 0.1, 1, 0, 0)
    s = fast_settings(max_moves=20)
    p = build_puzzles('primary', 1, 12, None)[0]
    run = Run({'suite': 'primary', 'n_puzzles': 1, 'seed': 12}, s, ['opus'])
    result = asyncio.run(play_trial(run, p, 'opus', AlwaysU()))
    assert not result['solved'] and result['status'] == 'RAN_OUT_OF_MOVES'
    assert result['turns'] == result['turn_limit'] == 5
