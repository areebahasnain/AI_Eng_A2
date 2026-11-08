"""Teacher's exact-3 puzzle protocol + shared local vision/notation + offline diagnostics."""
import asyncio
import json

import httpx

from backend.adapters import Decision
from backend.config import Settings, ollama_models
from backend.contract import (
    OLLAMA_CHAT_SYSTEM_PROMPT,
    OLLAMA_COMMON_GUIDE,
    build_game_state,
    face_grids,
    ollama_chat_user_message,
    ollama_decisions_questions,
)
from backend.cube import SOLVED, MOVES, apply_move, is_solved
from backend.ollama import OllamaAdapter
from backend.progress import EXACT_DISTANCE_HORIZON, exact_local_distance, measure_progress
from backend.runner import Run, build_puzzles, play_trial
from backend.solver import shortest_path_cached


def test_grid_rows_are_six_distinct_face_on_observations():
    puzzle = build_puzzles('primary', 1, 67, None)[0]
    state = puzzle['state']
    grids = face_grids(state)
    assert list(grids) == list('URFDLB')
    assert len(grids) == 6
    for idx, face in enumerate('URFDLB'):
        assert len(grids[face]) == 3
        assert all(len(row.split()) == 3 for row in grids[face])
        assert ''.join(''.join(row.split()) for row in grids[face]) == state[idx * 9:idx * 9 + 9]
    # The solved state is only an example in the README; the actual prompt uses
    # the *scrambled* state, without an answer key.
    game_state = build_game_state(state, [], 20, readable_grids=True)
    assert game_state['faces_3x3'] == grids
    assert game_state['cube_facelets'] == state
    assert 'scramble' not in game_state
    assert 'distance' not in game_state
    assert 'solution' not in game_state
    assert 'faces_3x3' not in build_game_state(state, [], 20)  # hosted payload unchanged


def test_four_ollama_models_get_same_rules_and_state():
    puzzle = build_puzzles('warmup', 1, 45, None)[0]
    game_state = build_game_state(puzzle['state'], ['U'], 19, readable_grids=True)
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append((req.url.path, body))
        if req.url.path == '/v1/systemone':
            return httpx.Response(200, json={'answers': {'next_move': {'choice': 'U'}}})
        return httpx.Response(200, json={'message': {'content': '{"move": "U"}'}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for spec in ollama_models():
                r = await OllamaAdapter(spec, Settings(provider='ollama', mock=False), client).decide(game_state)
                assert r.ok and r.move == 'U'

    asyncio.run(go())
    assert len(seen) == 4
    assert seen[0][0] == '/v1/systemone'
    assert seen[0][1]['state'] == game_state
    assert seen[0][1]['questions']['next_move']['instructions'] == OLLAMA_COMMON_GUIDE
    for i, (route, body) in enumerate(seen[1:], start=1):
        assert route == '/api/chat'
        assert body['messages'][0]['content'] == OLLAMA_CHAT_SYSTEM_PROMPT
        assert json.dumps(game_state, separators=(',', ':')) in body['messages'][1]['content']
        assert body['format']['type'] == 'object'
        assert 'clockwise' in OLLAMA_COMMON_GUIDE
        assert "counterclockwise" in OLLAMA_COMMON_GUIDE
        assert 'face being turned' in OLLAMA_COMMON_GUIDE.lower()
        assert '18 legal' in OLLAMA_COMMON_GUIDE
    assert set(ollama_decisions_questions()['next_move']['criteria']) == set(MOVES)


def test_exact_distance_direction_after_correct_and_wrong_moves():
    puzzle = build_puzzles('primary', 1, 102, None)[0]
    state = puzzle['state']
    assert exact_local_distance(state) == 3
    correct_first = shortest_path_cached(state, 3)[0]
    closer = apply_move(state, correct_first)
    assert exact_local_distance(closer) == 2
    good = measure_progress(3, 2)
    assert good['distance_change'] == 'closer' and good['distance_delta'] == -1
    # The model can also pick a legal move which leads away from solved.
    wrong = next((m for m in MOVES if exact_local_distance(apply_move(state, m)) == 4), None)
    assert wrong is not None
    bad = measure_progress(3, 4)
    assert bad['distance_change'] == 'farther' and bad['distance_delta'] == 1
    assert measure_progress(3, 3)['distance_change'] == 'same'
    assert measure_progress(None, None)['distance_change'] == 'unknown'
    assert measure_progress(7, None)['distance_change'] == 'farther'
    assert measure_progress(None, 7)['distance_change'] == 'closer'
    assert EXACT_DISTANCE_HORIZON == 7


def test_ollama_runner_records_progress_but_does_not_give_oracle_to_model():
    puzzle = build_puzzles('warmup', 1, 202, None)[0]
    solution = shortest_path_cached(puzzle['state'], 3)

    class ExactThreeMoves:
        def __init__(self):
            self.index = 0
        async def decide(self, state):
            assert state['faces_3x3'] == face_grids(state['cube_facelets'])
            assert 'distance' not in state and 'shortest_path' not in state
            move = solution[self.index]
            self.index += 1
            return Decision(move, True, 3.5, 3.5, 1, 0, 0, local_requests=1, live_latency_ms=3.5)

    models = ollama_models()
    s = Settings(provider='ollama', mock=False, models=models, max_moves=20, time_limit_s=20)
    run = Run({'suite': 'warmup', 'n_puzzles': 1, 'seed': 202, 'provider': 'ollama'}, s, [models[1].key])
    result = asyncio.run(play_trial(run, puzzle, models[1].key, ExactThreeMoves()))
    assert result['solved'] and result['moves_used'] == 3
    assert result['progress_counts']['closer'] == 3
    assert result['final_exact_distance'] == 0
    assert [t['distance_after'] for t in result['turn_log']] == [2, 1, 0]
    assert [t['distance_change'] for t in result['turn_log']] == ['closer'] * 3
    moves = [e for e in run.events if e['type'] == 'move']
    assert [e['distance_after_label'] for e in moves] == ['2', '1', '0']
    assert is_solved(result['final_state'])
