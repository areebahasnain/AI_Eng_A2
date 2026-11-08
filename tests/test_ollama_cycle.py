"""Offline checks for honest local cycle feedback (no Ollama/network required)."""
import asyncio

from backend.adapters import Decision
from backend.config import Settings, ollama_models
from backend.contract import OLLAMA_COMMON_GUIDE
from backend.cube import MOVES, apply_move
from backend.progress import local_cycle_observation, repeated_closed_loop
from backend.runner import Run, build_puzzles, play_trial


def test_first_step_does_not_preemptively_ban_anything():
    original = build_puzzles('primary', 1, 9, None)[0]['state']
    first = local_cycle_observation(original, {original})
    assert first['avoid_revisit_moves'] == []
    state = apply_move(original, 'D')
    next_turn = local_cycle_observation(state, {original, state})
    assert "D'" in next_turn['avoid_revisit_moves']
    assert 'D' not in next_turn['avoid_revisit_moves']
    assert set(next_turn['avoid_revisit_moves']).issubset(set(MOVES))


def test_repeated_closed_loop_finds_exact_cycles_only():
    p = build_puzzles('primary', 1, 99, None)[0]['state']
    states = [p]
    moves = ['D', "D'", 'D', "D'"]
    for m in moves: states.append(apply_move(states[-1], m))
    assert repeated_closed_loop(states, moves) == 2
    assert repeated_closed_loop(states[:-1], moves[:-1]) is None
    assert repeated_closed_loop(states, ['U', 'F', 'L', 'B']) is None


def test_local_runner_stops_after_repeated_cycle_without_supplying_solution():
    puzzle = build_puzzles('primary', 1, 52, None)[0]
    models = ollama_models()

    class CyclicModel:
        def __init__(self): self.calls, self.states = 0, []
        async def decide(self, observation):
            self.states.append(observation)
            assert observation['faces_3x3']
            assert 'distance_after' not in observation
            assert 'shortest_path' not in observation
            assert 'solution' not in observation
            chosen = ['D', "D'"][self.calls % 2]
            self.calls += 1
            return Decision(chosen, True, 0.1, 0.1, 1, 0, 0, local_requests=1)

    s = Settings(provider='ollama', mock=False, models=models, time_limit_s=40,
                 ollama_stop_on_repeat_loop=True)
    model = CyclicModel()
    run = Run({'suite': 'primary', 'n_puzzles': 1, 'seed': 52}, s, [models[0].key])
    result = asyncio.run(play_trial(run, puzzle, models[0].key, model))
    assert result['status'] == 'STALLED_LOOP'
    assert not result['solved'] and result['moves'] == ['D', "D'", 'D', "D'"]
    assert result['turns'] == 4 and result['local_requests'] == 4
    assert result['revisited_states'] == 3
    assert len(model.states) == 4
    assert "D'" in model.states[1]['avoid_revisit_moves']
    assert model.states[2]['avoid_revisit_moves']
    assert [t['revisited_state'] for t in result['turn_log']] == [False, True, True, True]
    assert any(e['type'] == 'loop_detected' for e in run.events)
    assert 'inverse' in OLLAMA_COMMON_GUIDE


def test_hosted_payload_not_given_cycle_feedback():
    from backend.contract import build_game_state
    state = build_puzzles('primary', 1, 11, None)[0]['state']
    hosted = build_game_state(state, ['D'], 19, readable_grids=False)
    assert 'avoid_revisit_moves' not in hosted
    assert 'cycle_guidance' not in hosted


def test_standard_local_benchmark_does_not_end_early_for_loops():
    p = build_puzzles('primary', 1, 52, None)[0]
    models = ollama_models()
    class Repeater:
        def __init__(self): self.calls = 0
        async def decide(self, state):
            move = ['D', "D'"][self.calls % 2]
            self.calls += 1
            return Decision(move, True, 0.1, 0.1, 1, 0, 0, local_requests=1)
    s = Settings(provider='ollama', mock=False, models=models, max_moves=6,
                 time_limit_s=40)
    run = Run({'suite':'primary','n_puzzles':1,'seed':52},s,[models[0].key])
    result = asyncio.run(play_trial(run,p,models[0].key,Repeater()))
    assert result['status']=='RAN_OUT_OF_MOVES'
    assert result['turns']==6
    assert len([e for e in run.events if e['type']=='loop_detected']) >= 1
