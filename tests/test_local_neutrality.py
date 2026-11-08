"""Regression protection for non-leading, comparable local Ollama prompts."""
from __future__ import annotations

import asyncio
import json

import httpx

from backend.config import Settings, ollama_models
from backend.contract import (
    MOVE_CRITERIA, OLLAMA_CHAT_SYSTEM_PROMPT, OLLAMA_COMMON_GUIDE,
    build_game_state,
)
from backend.cube import MOVES, apply_move
from backend.ollama import OllamaAdapter, action_order_for_observation
from backend.runner import build_puzzles
from backend.solver import shortest_path_cached


def _observation(seed=483):
    puzzle = build_puzzles('primary', 1, seed, None)[0]
    return build_game_state(puzzle['state'], [], 20, readable_grids=True), puzzle


def test_no_concrete_output_move_example_in_neutral_prompt():
    assert '{"move": "U"}' not in OLLAMA_CHAT_SYSTEM_PROMPT
    assert 'e.g.' not in OLLAMA_CHAT_SYSTEM_PROMPT
    assert 'inverse' in OLLAMA_COMMON_GUIDE
    assert '18 legal' in OLLAMA_COMMON_GUIDE


def test_all_18_actions_are_present_in_both_api_formats_identical_order():
    state, puzzle = _observation()
    order = action_order_for_observation(state)
    assert len(order) == 18 and set(order) == set(MOVES)
    assert action_order_for_observation(state) == order
    assert action_order_for_observation(state, False) == list(MOVES)
    assert list(MOVE_CRITERIA) == list(MOVES)
    specs = ollama_models()
    payloads = [OllamaAdapter(spec, Settings(models=specs))._payload(state)[1]
                for spec in specs]
    clef = payloads[0]['questions']['next_move']
    assert list(clef['criteria']) == order
    assert clef['instructions'] == OLLAMA_COMMON_GUIDE
    for payload in payloads[1:]:
        assert payload['format']['properties']['move']['enum'] == order
        assert list(json.loads(payload['messages'][1]['content'].split(
            'The 18 allowed moves and their meanings (JSON):\n', 1)[1].split(
            '\nReturn exactly one legal move', 1)[0])) == order
        assert payload['messages'][0]['content'] == OLLAMA_CHAT_SYSTEM_PROMPT
        assert puzzle['state'] in payload['messages'][1]['content']
    assert len({json.dumps(p['messages']) for p in payloads[1:]}) == 1


def test_recovery_prompt_has_no_literal_move_example():
    state, _ = _observation()
    payload = OllamaAdapter(ollama_models()[1], Settings())._payload(state, recovery=True)[1]
    assert payload['format']['type'] == 'string'
    assert set(payload['format']['enum']) == set(MOVES)
    assert 'e.g.' not in payload['messages'][0]['content']


def test_action_order_changes_without_information_from_reference_solver():
    state, puzzle = _observation()
    order = action_order_for_observation(state)
    # Position rotation is deterministic and depends only on current observation.
    assert len(set(order)) == 18
    reversed_history = dict(state, recent_moves=['L2'])
    assert action_order_for_observation(reversed_history) != order
    assert len(shortest_path_cached(puzzle['state'], 3)) == 3
    for m in order:
        assert len(apply_move(puzzle['state'], m)) == 54
    # Neither the scramble nor solution enters the prompt.
    payload = OllamaAdapter(ollama_models()[0], Settings())._payload(state)[1]
    assert 'scramble' not in str(payload).lower()
    assert 'distance_reducing_choices' not in str(payload)


def test_legacy_prompt_only_changes_chat_instructions_not_game_state_or_actions():
    state, _ = _observation()
    spec = ollama_models()[1]
    neutral = OllamaAdapter(spec, Settings(ollama_prompt_variant='neutral'))._payload(state)[1]
    legacy = OllamaAdapter(spec, Settings(ollama_prompt_variant='legacy'))._payload(state)[1]
    assert neutral['messages'][1] == legacy['messages'][1]
    assert neutral['format'] == legacy['format']
    assert neutral['messages'][0] != legacy['messages'][0]


def test_local_models_always_return_unassisted_raw_moves_without_solver_intervention():
    state, puzzle = _observation()
    requests = []
    def server(req):
        requests.append(req.url.path)
        if req.url.path == '/v1/systemone':
            return httpx.Response(200, json={'answers': {'next_move': {'choice': "B2"}}})
        return httpx.Response(200, json={'message': {'content': '{"move":"B2"}'}})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
            return [await OllamaAdapter(spec, Settings(provider='ollama', mock=False), client).decide(state)
                    for spec in ollama_models()]
    results = asyncio.run(go())
    assert len(requests) == 4
    assert all(r.ok and r.move == 'B2' and r.local_requests == 1 and not r.api_calls for r in results)
