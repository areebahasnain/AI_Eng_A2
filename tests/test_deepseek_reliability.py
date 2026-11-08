"""Regression: the local fourth slot is Llama 3.2, not DeepSeek.

The original test filename is retained so the downloadable patch overwrites
its predecessor on Windows. It makes no inference or network requests.
"""
import asyncio
import json

import httpx
import pytest

from backend.adapters import InvalidOutput
from backend.config import Settings, ollama_models
from backend.contract import build_game_state
from backend.cube import SOLVED
from backend.ollama import OllamaAdapter, parse_local_move


def test_deepseek_removed_and_llama_32_selected():
    models = ollama_models()
    assert len(models) == 4
    assert [m.key for m in models] == ['clef_local', 'qwen_local', 'llama_local', 'gemma_local']
    assert models[2].model_id == 'llama3.2:3b'
    assert all('deepseek' not in m.model_id.lower() for m in models)
    assert models[0].api == 'systemone'
    assert models[2].api == 'ollama_chat'


@pytest.mark.parametrize('raw, move', [
    ('U', 'U'), ('D\'', "D'"), ('U2', 'U2'),
    ('{"move":"L2"}', 'L2'), ('"F"', 'F'),
    ('```json\n{"move":"B\'"}\n```', "B'"),
])
def test_parses_only_an_explicit_legal_move(raw, move):
    assert parse_local_move(raw) == move


@pytest.mark.parametrize('raw', [
    '', '<think>choose U', 'I think U is best', 'U or R',
    '{"move":"A"}', '{"move":"R","extra":1}',
    '<think>U</think>', 'D D\'', 'U\nR',
])
def test_rejects_unfinished_thinking_and_ambiguous_output(raw):
    with pytest.raises(InvalidOutput):
        parse_local_move(raw)


def test_llama_empty_answer_one_local_fallback_never_openrouter():
    payloads = []
    def handler(req):
        payload = json.loads(req.content)
        payloads.append(payload)
        if len(payloads) == 1:
            return httpx.Response(200, json={'message': {'content': '', 'thinking':'unfinished'},
                                             'done_reason':'length'})
        return httpx.Response(200, json={'message': {'content':'"R\'"'}, 'done_reason':'stop'})

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[2], Settings(provider='ollama', mock=False), client).decide(
                build_game_state(SOLVED, [], 20))

    result = asyncio.run(check())
    assert result.ok and result.move == "R'"
    assert result.local_requests == 2 and result.api_calls == 0
    assert result.invalid_outputs == 1
    assert payloads[0]['format']['type'] == 'object'
    assert payloads[1]['format']['type'] == 'string'
    assert all(p['model'] == 'llama3.2:3b' for p in payloads)
