"""Simulation-based regression tests; these do NOT run local model weights."""
import asyncio
import json
import httpx

from backend.adapters import Decision
from backend.config import Settings, ollama_models
from backend.contract import build_game_state
from backend.cube import MOVES, apply_moves, is_solved
from backend.guidance import optimal_next_moves, choose_guided_move
from backend.ollama import OllamaAdapter
from backend.runner import Run, build_puzzles, play_trial
from backend.stats import model_stats


def test_guidance_exact_three_move_path_on_many_independent_scrambles():
    tested = 0
    for seed in range(25):
        for p in build_puzzles('primary', 2, seed, None):
            state = p['state']
            for depth in (3, 2, 1):
                options = optimal_next_moves(state, depth)
                assert options
                assert set(options).issubset(MOVES)
                assert len(options) < 18
                # Always-U is an adversarial model; the reference guard prevents
                # it from derailing an explicitly assisted demo.
                move, replaced = choose_guided_move('U', options)
                assert replaced == ('U' not in options)
                state = apply_moves(state, [move])
            assert is_solved(state)
            tested += 1
    assert tested == 50


class AlwaysU:
    async def decide(self, state):
        return Decision('U', True, 0.1, 0.1, 1, 0, 0, local_requests=1)


class AlwaysInvalid:
    async def decide(self, state):
        return Decision(None, False, 0.1, 0.1, 1, 0, 1,
                        error='Local Ollama: InvalidOutput: empty content',
                        local_requests=1)


def _run(adapter, guided):
    m = ollama_models()[1]
    s = Settings(provider='ollama', mock=False, models=[m], max_moves=20,
                 time_limit_s=15, ollama_time_limit_s=15)
    puzzle = build_puzzles('primary', 1, 23, None)[0]
    run = Run({'suite':'primary','n_puzzles':1, 'seed':23,
               'ollama_guided': guided}, s, [m.key])
    trial = asyncio.run(play_trial(run, puzzle, m.key, adapter))
    return trial, m


def test_guided_model_wrong_actions_are_transparently_overridden():
    trial, model = _run(AlwaysU(), True)
    assert trial['solved'] and trial['assisted_mode']
    assert trial['moves_used'] == 3
    assert trial['guide_overrides'] >= 1
    assert all('model_proposed_move' in t for t in trial['turn_log'])
    assert any(t['move_source'] == 'reference_guard' for t in trial['turn_log'])
    stats = model_stats({'key': model.key, 'name': model.name,
                         'model_id': model.model_id, 'category': model.category}, [trial])
    # A forced solve must NOT appear as a 100% independent model solve rate.
    assert stats['solved'] == 0 and stats['trials'] == 0
    assert stats['success_rate'] is None
    assert stats['assisted_trials'] == stats['assisted_solved'] == 1


def test_guided_invalid_answers_logged_as_solver_only_not_model_success():
    trial, _ = _run(AlwaysInvalid(), True)
    assert trial['solved'] and trial['moves_used'] == 3
    assert trial['invalid_outputs'] == 3
    assert trial['failed_turns'] == 3
    assert trial['guide_overrides'] == 3
    assert all(t['move_source'] == 'solver_only_fallback' for t in trial['turn_log'])
    assert all(not t['ok'] for t in trial['turn_log'])


def test_unassisted_model_still_allowed_to_fail_without_rewriting_moves():
    trial, _ = _run(AlwaysInvalid(), False)
    assert not trial['solved'] and trial['status'] == 'ERROR'
    assert trial['moves_used'] == 0
    assert not trial['assisted_mode'] and trial['invalid_outputs'] == 3


def test_llama_recovery_second_local_call_is_logged_and_valid():
    seen = []
    def handler(req):
        payload = json.loads(req.content)
        seen.append(payload)
        if len(seen) == 1:
            return httpx.Response(200, json={
                'done_reason':'length', 'eval_count':384,
                'message': {'content':'', 'thinking':'still reasoning'}
            })
        return httpx.Response(200, json={
            'done_reason':'stop', 'message': {'content':'"L2"'}
        })
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            spec = ollama_models()[2]
            settings = Settings(provider='ollama', mock=False, ollama_max_tokens=128)
            return await OllamaAdapter(spec, settings, client).decide(build_game_state('U'*9+'R'*9+'F'*9+'D'*9+'L'*9+'B'*9, [],20))
    decision = asyncio.run(run())
    assert decision.ok and decision.move == 'L2'
    assert decision.local_requests == decision.attempts == 2
    assert decision.retries == 1 and decision.invalid_outputs == 1
    assert seen[0]['format']['type'] == 'object' and seen[1]['format']['type'] == 'string'
    assert seen[0]['think'] is False and seen[1]['think'] is False
    assert seen[1]['options']['num_predict'] == 48
    assert decision.attempt_log[0]['error'] == 'InvalidOutput'


def test_llama_stops_after_one_recovery_not_infinite():
    count = 0
    def handler(req):
        nonlocal count
        count += 1
        return httpx.Response(200, json={'message': {'content':''}, 'done_reason':'length'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[2], Settings(provider='ollama', mock=False), client).decide(build_game_state('U'*9+'R'*9+'F'*9+'D'*9+'L'*9+'B'*9, [], 20))
    decision = asyncio.run(run())
    assert count == 2 and not decision.ok and decision.invalid_outputs == 2
    assert decision.local_requests == 2
    assert 'done_reason=length' in decision.error


def test_local_clef_remains_one_request_without_recovery():
    count = 0
    def handler(req):
        nonlocal count
        count += 1
        return httpx.Response(200, json={'answers': {'next_move': {
            'choice': 'D', 'probabilities': {'D': .2}, 'confidence': .1}}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[0], Settings(provider='ollama', mock=False), client).decide(build_game_state('U'*9+'R'*9+'F'*9+'D'*9+'L'*9+'B'*9, [], 20))
    d = asyncio.run(run())
    assert count == 1 and d.ok and d.move == 'D'
