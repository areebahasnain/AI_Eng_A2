"""Ollama is a local resource; the backend must reject accidental parallel runs."""
from fastapi.testclient import TestClient
from backend import main


def test_local_provider_forces_sequential_even_if_client_requests_parallel(monkeypatch):
    main.RUNS.clear()
    async def stop_immediately(run):
        run.status = 'done'
    monkeypatch.setattr(main, 'execute', stop_immediately)
    with TestClient(main.app) as client:
        response = client.post('/api/run', json={
            'provider':'ollama', 'models':['llama_local'],
            'parallel': True, 'n_puzzles': 1,
        })
        assert response.status_code == 200, response.text
        run = main.RUNS[response.json()['run_id']]
        assert run.request['parallel'] is False
        assert run.settings.provider == 'ollama'
    main.RUNS.clear()
