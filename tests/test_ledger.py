"""Safety regression tests. All HTTP is mocked; never use the teacher's key."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.adapters import ChatAdapter, DecisionsAdapter
from backend.config import ModelSpec, Settings
from backend.ledger import APILedger, MAX_TOTAL, MAX_CLAUDE, MAX_DECISION_EACH, QuotaExhausted


def test_atomic_global_and_per_model_limits(tmp_path):
    path = tmp_path / 'persistent.sqlite3'
    keys = ['jev', 'luna', 'clef', 'opus']
    def reserve(arg):
        k, i = arg
        ledger = APILedger(path)
        try:
            ledger.claim(k, f'{k}-model', f'https://example.org/{k}', {'different': i})
            return k
        except QuotaExhausted:
            return None
    jobs = [(k, i) for i in range(35) for k in keys]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(reserve, jobs))
    assert sum(v is not None for v in results) == MAX_TOTAL == 65
    assert results.count('opus') == MAX_CLAUDE == 5
    assert all(results.count(k) == MAX_DECISION_EACH for k in ('jev', 'luna', 'clef'))
    fresh = APILedger(path).snapshot()
    assert fresh['total_used'] == MAX_TOTAL
    assert all(fresh['by_model'][k]['used'] == (5 if k == 'opus' else 20) for k in keys)


def test_cache_survives_restart_and_bypasses_spent_quota(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    db = APILedger(path)
    url = 'https://example.org/alpha/decisions'
    request = {'model': 'jev-test', 'state': {'cube': 'hello'}}
    first = db.claim('jev', 'jev-test', url, request)
    assert first.row_id is not None
    db.finish(first, status=200, body={'answers': {'next_move': {'choice': 'U'}},
                                        'usage': {'cost': 0.125}}, network_ms=133.4)
    # Spend the remaining model allowance without creating a response cache.
    for i in range(19):
        db.claim('jev', 'jev-test', url, {'unique': i})
    restarted = APILedger(path)
    cached = restarted.claim('jev', 'jev-test', url, request)
    assert cached.cache_hit and cached.cached_body['answers']['next_move']['choice'] == 'U'
    assert restarted.snapshot()['by_model']['jev']['used'] == 20
    assert restarted.snapshot()['by_model']['jev']['cache_hits'] == 1
    with pytest.raises(QuotaExhausted):
        restarted.claim('jev', 'jev-test', url, {'not_cached': True})
    assert restarted.snapshot()['known_cost_usd'] == 0.125


def test_failed_http_call_is_spent_but_not_cached(tmp_path):
    db = APILedger(tmp_path / 'usage.sqlite3')
    request = {'prompt': 'unique'}
    first = db.claim('opus', 'opus-test', 'https://somewhere.test', request)
    db.finish(first, status=429, body={'error': {'message': 'rate limit'}}, network_ms=1.2)
    again = db.claim('opus', 'opus-test', 'https://somewhere.test', request)
    assert again.row_id is not None and not again.cache_hit
    assert db.snapshot()['by_model']['opus']['used'] == 2
    assert db.snapshot()['cache_entries'] == 0


def test_adapter_cache_prevents_repeat_paid_call_and_tracks_live_vs_cache(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    hits = []
    def handler(request):
        hits.append(request)
        return httpx.Response(200, json={
            'answers': {'next_move': {'choice': 'F', 'probabilities': {'F': .8}}},
            'usage': {'cost': 0.002},
        })
    spec = ModelSpec('jev', 'Jev', 'test-jev', 'decision', 'decisions', '', '')
    settings = Settings(api_key='TEST_ONLY', mock=False, provider='openrouter',
                        ledger_path=path)
    state = {'cube_facelets': 'unique'}
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            a = DecisionsAdapter(spec, settings, client)
            d1 = await a.decide(state)
            d2 = await a.decide(state)
            return d1, d2
    first, second = asyncio.run(go())
    assert len(hits) == 1
    assert first.ok and second.ok
    assert first.api_calls == 1 and first.cache_hits == 0 and first.cost_usd == 0.002
    assert second.api_calls == 0 and second.cache_hits == 1 and second.cost_usd is None
    assert first.live_latency_ms >= 0 and second.cache_latency_ms >= 0
    assert APILedger(path).snapshot()['total_used'] == 1


def test_claude_fallback_counts_as_real_calls(tmp_path):
    calls = []
    def handler(req):
        payload = __import__('json').loads(req.content)
        calls.append(payload)
        if 'response_format' in payload:
            return httpx.Response(400, json={'error': {'message': 'response_format unsupported'}})
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"move":"U"}'}}]})
    spec = ModelSpec('opus', 'Claude', 'opus-test', 'llm', 'chat', '', '')
    s = Settings(api_key='TEST_ONLY', mock=False, provider='openrouter',
                 ledger_path=tmp_path / 'usage.sqlite3', max_retries=0)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ChatAdapter(spec, s, client).decide({'cube_facelets': 'unique'})
    d = asyncio.run(go())
    assert d.ok and len(calls) == 2
    assert d.api_calls == 2 and APILedger(s.ledger_path).snapshot()['by_model']['opus']['used'] == 2
