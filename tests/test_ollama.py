"""Ollama contract tests use MockTransport (no installed models or network)."""
import asyncio
import json

import httpx

from backend.config import Settings, ollama_models
from backend.contract import build_game_state
from backend.cube import SOLVED
from backend.ollama import OllamaAdapter


def test_local_clef_uses_systemone_endpoint():
    seen = []
    def handler(req):
        seen.append(req)
        payload = json.loads(req.content)
        assert req.url.path == '/v1/systemone'
        assert payload['state']['cube_facelets'] == SOLVED
        return httpx.Response(200, json={'answers': {'next_move': {
            'choice': 'F', 'probabilities': {'F': .5}, 'confidence': .6}}})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[0], Settings(provider='ollama', mock=False), client).decide(
                build_game_state(SOLVED, [], 20))
    d = asyncio.run(go())
    assert len(seen) == 1 and d.move == 'F' and d.ok
    assert d.api_calls == 0 and d.local_requests == 1
    assert 'authorization' not in seen[0].headers


def test_local_qwen_uses_chat_endpoint():
    def handler(req):
        data = json.loads(req.content)
        assert req.url.path == '/api/chat'
        assert data['format']['properties']['move']['type'] == 'string'
        return httpx.Response(200, json={'message': {'role': 'assistant', 'content': '{"move":"U2"}'}})
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[1], Settings(provider='ollama', mock=False), client).decide(
                build_game_state(SOLVED, [], 20))
    d = asyncio.run(go())
    assert d.ok and d.move == 'U2' and d.local_requests == 1


def test_local_ollama_has_separate_request_timeout():
    from backend.config import Settings
    recorded = []
    def handler(req):
        recorded.append(req)
        return httpx.Response(200, json={'message': {'content': '{"move":"U"}'}})
    async def go():
        s = Settings(provider='ollama', mock=False, request_timeout_s=1,
                     ollama_request_timeout_s=240, ollama_max_tokens=64,
                     ollama_disable_thinking=True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[1], s, client).decide(
                build_game_state(SOLVED, [], 20))
    result = asyncio.run(go())
    assert result.ok and result.move == 'U'
    payload = json.loads(recorded[0].content)
    assert payload['options']['num_predict'] == 64
    assert payload['think'] is False


def test_timeout_error_is_explanatory():
    def handler(req):
        raise httpx.ReadTimeout('')
    async def go():
        s = Settings(provider='ollama', mock=False, ollama_request_timeout_s=240)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OllamaAdapter(ollama_models()[1], s, client).decide(
                build_game_state(SOLVED, [], 20))
    d = asyncio.run(go())
    assert not d.ok and d.move is None
    assert 'within 240s' in d.error and 'disable Parallel' in d.error
