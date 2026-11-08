import json
import time

import pytest
from fastapi.testclient import TestClient

from backend import main

SECRET = "NOT_A_REAL_OPENROUTER_KEY_TEST_ONLY"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("STUDENT_NAME", "Test Student")
    monkeypatch.setenv("STUDENT_ROLL_NO", "XX-123")
    monkeypatch.setenv("MOCK_SPEED", "5000")
    main.RUNS.clear()
    with TestClient(main.app) as c:
        yield c


def wait_done(client, run_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/run/{run_id}").json()
        if r["status"] in {"done", "stopped", "error"}:
            return r
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_config_never_leaks_the_api_key(client):
    body = client.get("/api/config")
    assert SECRET not in body.text
    cfg = body.json()
    assert cfg["api_key_set"] is True
    assert cfg["student_name"] == "Test Student" and cfg["student_roll_no"] == "XX-123"
    assert [m["key"] for m in cfg["models"]] == ["opus", "jev", "luna", "clef"]
    assert {m["model_id"] for m in cfg["models"]} == {
        "anthropic/claude-opus-5.5", "typesafe/jev-1.13", "openai/gpt-6-luna-decisions", "cloudflare/clef"}


def test_index_and_static_assets_are_served_without_the_key(client):
    for path in ("/", "/static/app.js", "/static/style.css"):
        r = client.get(path)
        assert r.status_code == 200 and SECRET not in r.text


def test_geometry_endpoint(client):
    g = client.get("/api/geometry").json()
    assert len(g["facelets"]) == 54 and len(g["solved"]) == 54


def test_run_without_key_in_live_mode_is_rejected(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ALLOW_LIVE_API", "1")
    r = client.post("/api/run", json={"suite": "warmup", "n_puzzles": 1, "mock": False})
    assert r.status_code == 400 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_mock_run_end_to_end_with_sse_and_exports(client):
    r = client.post("/api/run", json={"suite": "warmup", "n_puzzles": 2, "seed": 4, "mock": True})
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    with client.stream("GET", f"/api/run/{run_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_done"
    assert events[0]["mock"] is True
    assert SECRET not in json.dumps(events)

    run = wait_done(client, run_id)
    assert run["status"] == "done" and len(run["results"]) == 8 and run["mock"] is True
    assert SECRET not in json.dumps(run)

    trials = client.get(f"/api/run/{run_id}/trials.csv")
    assert trials.status_code == 200 and trials.text.count("\n") == 9
    assert "model_name" in trials.text.splitlines()[0]
    moves = client.get(f"/api/run/{run_id}/moves.csv")
    assert moves.status_code == 200 and moves.text.count("\n") > 8


def test_only_one_run_at_a_time_and_stop(client):
    # slow mock so the first run is still going when we try to start another
    import os
    os.environ["MOCK_SPEED"] = "1"
    r = client.post("/api/run", json={"suite": "primary", "n_puzzles": 5, "seed": 1, "mock": True})
    run_id = r.json()["run_id"]
    assert client.post("/api/run", json={"suite": "warmup", "n_puzzles": 1, "mock": True}).status_code == 409
    stopped = client.post(f"/api/run/{run_id}/stop").json()
    assert stopped["status"] == "stopped"
    assert client.get(f"/api/run/{run_id}").json()["status"] == "stopped"


def test_unknown_model_key_is_rejected(client):
    r = client.post("/api/run", json={"models": ["nope"], "mock": True})
    assert r.status_code == 400


def test_live_mode_must_be_explicitly_enabled_even_when_key_is_present(client):
    r = client.post('/api/run', json={'provider': 'openrouter', 'n_puzzles': 1})
    assert r.status_code == 400 and 'ALLOW_LIVE_API=1' in r.json()['detail']
    usage = client.get('/api/usage')
    assert usage.status_code == 200
    assert usage.json()['total_used'] == 0
    assert SECRET not in usage.text


def test_invalid_custom_distance_rejected(client):
    r = client.post('/api/run', json={'suite': 'custom', 'scramble_len': 4, 'mock': True})
    assert r.status_code == 422
