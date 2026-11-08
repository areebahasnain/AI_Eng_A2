import asyncio
import json
from dataclasses import asdict

import httpx

from backend.adapters import ChatAdapter, DecisionsAdapter
from backend.config import ModelSpec, Settings
from backend.contract import build_game_state, MOVE_CRITERIA
from backend.cube import MOVES, SOLVED

KEY = "NOT_A_REAL_OPENROUTER_KEY_TEST_ONLY"
STATE = build_game_state(SOLVED, ["R", "U'"], 30)


def settings(**kw) -> Settings:
    base = dict(api_key=KEY, mock=False, retry_backoff_s=0.0, max_retries=2, request_timeout_s=5)
    base.update(kw)
    return Settings(**base)


DEC_SPEC = ModelSpec("jev", "Jev", "typesafe/jev-1.13", "decision", "decisions", "DECISION MODEL", "#fff")
CHAT_SPEC = ModelSpec("opus", "Opus", "anthropic/claude-opus-5.5", "llm", "chat", "LLM", "#fff")


def run(coro):
    return asyncio.run(coro)


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def decision_body(choice="R", probs=None):
    return {
        "model": "typesafe/jev-1.13",
        "answers": {
            "next_move": {
                "type": "choice",
                "choice": choice,
                "probabilities": probs or {choice: 0.8},
                "confidence": 0.9,
            }
        },
        "usage": {"input_tokens": 100, "output_tokens": 0, "cost": 0.0001},
    }


def chat_body(content):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"cost": 0.02}}


# ---------------------------------------------------------------- Decisions API
def test_decisions_request_shape_and_happy_path():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["payload"] = json.loads(req.content)
        return httpx.Response(200, json=decision_body("U'"))

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert d.ok and d.move == "U'" and d.probability == 0.8 and d.confidence == 0.9
    assert d.attempts == 1 and d.retries == 0 and d.invalid_outputs == 0
    assert d.cost_usd == 0.0001 and d.latency_ms >= 0
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["auth"] == f"Bearer {KEY}"
    p = seen["payload"]
    assert p["model"] == "typesafe/jev-1.13"
    assert p["state"]["cube_facelets"] == SOLVED and p["state"]["recent_moves"] == ["R", "U'"]
    q = p["questions"]["next_move"]
    assert q["type"] == "choice"
    assert list(q["criteria"]) == list(MOVES) and q["criteria"] == MOVE_CRITERIA
    assert len(q["criteria"]) == 18


def test_decision_models_get_identical_questions_and_state():
    payloads = []

    def handler(req):
        payloads.append(json.loads(req.content))
        return httpx.Response(200, json=decision_body())

    async def go():
        async with make_client(handler) as c:
            for model_id in ("typesafe/jev-1.13", "openai/gpt-6-luna-decisions", "cloudflare/clef"):
                spec = ModelSpec("x", "x", model_id, "decision", "decisions", "", "")
                await DecisionsAdapter(spec, settings(), c).decide(STATE)

    run(go())
    assert [p["model"] for p in payloads] == ["typesafe/jev-1.13", "openai/gpt-6-luna-decisions", "cloudflare/clef"]
    for p in payloads[1:]:
        assert p["state"] == payloads[0]["state"] and p["questions"] == payloads[0]["questions"]


def test_illegal_choice_is_counted_and_retried_never_converted():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=decision_body("X" if calls["n"] == 1 else "F2"))

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    d = run(go())
    # An invalid HTTP 200 reply is cached, so repeating the same payload cannot
    # produce a different answer and must not consume another real call.
    assert not d.ok and d.move is None
    assert d.attempts == 1 and d.retries == 0 and d.invalid_outputs == 1
    assert d.api_calls == 1 and calls["n"] == 1
    assert d.attempt_log[0]["kind"] == "invalid"


def test_persistently_invalid_output_fails_the_turn():
    def handler(req):
        return httpx.Response(200, json=decision_body("sideways"))

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(max_retries=2), c).decide(STATE)

    d = run(go())
    assert not d.ok and d.move is None
    assert d.attempts == 1 and d.invalid_outputs == 1
    assert d.fatal_scope is None


def test_rate_limit_is_retried_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=decision_body("D"))

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert d.ok and d.move == "D" and d.retries == 1 and d.invalid_outputs == 0


def test_bad_key_is_fatal_for_the_run_and_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "No auth credentials found"}})

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert not d.ok and d.fatal_scope == "run" and calls["n"] == 1


def test_unknown_model_is_fatal_for_that_model():
    def handler(req):
        return httpx.Response(404, json={"error": {"message": "No endpoints found for model"}})

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert not d.ok and d.fatal_scope == "model" and "404" in d.error


def test_network_timeout_is_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ReadTimeout("boom")
        return httpx.Response(200, json=decision_body("B2"))

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert d.ok and d.move == "B2" and d.attempts == 3


def test_api_key_never_appears_in_decision_record():
    def handler(req):
        return httpx.Response(401, json={"error": {"message": "nope"}})

    async def go():
        async with make_client(handler) as c:
            return await DecisionsAdapter(DEC_SPEC, settings(), c).decide(STATE)

    assert KEY not in json.dumps(asdict(run(go())))


# ------------------------------------------------------------------ Chat adapter
def test_chat_request_shape_uses_constrained_json():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["payload"] = json.loads(req.content)
        return httpx.Response(200, json=chat_body('{"move": "R\'"}'))

    async def go():
        async with make_client(handler) as c:
            return await ChatAdapter(CHAT_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert d.ok and d.move == "R'" and d.cost_usd == 0.02
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    p = seen["payload"]
    assert p["model"] == "anthropic/claude-opus-5.5"
    rf = p["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["properties"]["move"]["enum"] == list(MOVES)
    user = p["messages"][-1]["content"]
    assert SOLVED in user and '"recent_moves": ["R", "U\'"]' in user


def test_chat_state_matches_decision_state():
    seen = {}

    def handler(req):
        seen["payload"] = json.loads(req.content)
        return httpx.Response(200, json=chat_body('{"move": "R"}'))

    async def go():
        async with make_client(handler) as c:
            await ChatAdapter(CHAT_SPEC, settings(), c).decide(STATE)

    run(go())
    assert json.dumps(STATE) in seen["payload"]["messages"][-1]["content"]


def test_chat_malformed_outputs_are_counted_not_coerced():
    outputs = iter(['R', '{"move": "R3"}', '{"move": "R", "why": "x"}'])

    def handler(req):
        return httpx.Response(200, json=chat_body(next(outputs)))

    async def go():
        async with make_client(handler) as c:
            return await ChatAdapter(CHAT_SPEC, settings(max_retries=2), c).decide(STATE)

    d = run(go())
    assert not d.ok and d.move is None and d.invalid_outputs == 1


def test_chat_accepts_markdown_fenced_json():
    def handler(req):
        return httpx.Response(200, json=chat_body('```json\n{"move": "L2"}\n```'))

    async def go():
        async with make_client(handler) as c:
            return await ChatAdapter(CHAT_SPEC, settings(), c).decide(STATE)

    assert run(go()).move == "L2"


def test_chat_falls_back_when_structured_output_unsupported():
    payloads = []

    def handler(req):
        payloads.append(json.loads(req.content))
        if "response_format" in payloads[-1]:
            return httpx.Response(400, json={"error": {"message": "response_format json_schema is not supported"}})
        return httpx.Response(200, json=chat_body('{"move": "F"}'))

    async def go():
        async with make_client(handler) as c:
            return await ChatAdapter(CHAT_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert d.ok and d.move == "F"
    assert "response_format" in payloads[0] and "response_format" not in payloads[1]
    assert d.retries == 0  # the adjustment does not eat a retry


def test_chat_fallback_also_triggers_on_404_no_structured_output_route():
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(404, json={"error": {"message": "No endpoints found that support structured_outputs / response_format"}})
        return httpx.Response(200, json=chat_body('{"move": "D2"}'))

    async def go():
        async with make_client(handler) as c:
            return await ChatAdapter(CHAT_SPEC, settings(), c).decide(STATE)

    d = run(go())
    assert d.ok and d.move == "D2" and calls == [True, False]


def test_chat_reasoning_and_temperature_are_opt_in():
    seen = {}

    def handler(req):
        seen["payload"] = json.loads(req.content)
        return httpx.Response(200, json=chat_body('{"move": "U"}'))

    async def go(**kw):
        async with make_client(handler) as c:
            await ChatAdapter(CHAT_SPEC, settings(**kw), c).decide(STATE)

    run(go())
    assert "reasoning" not in seen["payload"] and "temperature" not in seen["payload"]
    run(go(llm_reasoning_effort="low", llm_temperature=0.0))
    assert seen["payload"]["reasoning"] == {"effort": "low"} and seen["payload"]["temperature"] == 0.0
