"""Check exact local Ollama model installation and one move per model.

Usage (Windows PowerShell, from project root):
  .\.venv\Scripts\python.exe -m scripts.local_preflight
  .\.venv\Scripts\python.exe -m scripts.local_preflight --model clef_local --timeout 240

No requests to OpenRouter. Never reads, prints, or sends an API key. This is a
preflight of availability/output format, NOT evidence the model can solve cubes.
"""
from __future__ import annotations

import argparse
import asyncio
import json

import httpx

from backend.config import load_settings, ollama_models
from backend.contract import build_game_state
from backend.cube import apply_move, is_solved
from backend.ollama import OllamaAdapter
from backend.progress import exact_local_distance, local_cycle_observation
from backend.runner import build_puzzles


async def check(models: list[str], timeout_s: float, seed: int) -> int:
    settings = load_settings()
    settings.provider = 'ollama'
    settings.mock = False
    settings.ollama_request_timeout_s = timeout_s
    models_by_key = {m.key: m for m in ollama_models()}
    print('Ollama ONLY; OpenRouter calls: 0; teacher API key not used.', flush=True)
    print('Local Ollama:', settings.ollama_base_url, flush=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as client:
        try:
            response = await client.get(settings.ollama_base_url + '/api/tags')
            response.raise_for_status()
            tags = {m.get('name') for m in response.json().get('models', [])}
        except (httpx.HTTPError, ValueError) as e:
            print('Ollama server unavailable:', type(e).__name__, flush=True)
            return 2

        missing = [models_by_key[k] for k in models if models_by_key[k].model_id not in tags]
        if missing:
            for spec in missing:
                print('MISSING:', spec.model_id, '=> run: ollama pull ' + spec.model_id, flush=True)
            return 2

        puzzle = build_puzzles('primary', 1, seed, None)[0]
        print('Seed:', seed, 'Verified starting distance:', puzzle['optimal'], flush=True)
        error = False
        for key in models:
            spec = models_by_key[key]
            game_state = build_game_state(puzzle['state'], [], 20, readable_grids=True)
            game_state.update(local_cycle_observation(puzzle['state'], {puzzle['state']}))
            if settings.ollama_sticker_hints:
                from backend.progress import one_step_sticker_observation
                game_state.update(one_step_sticker_observation(puzzle['state'], {puzzle['state']}))
            adapter = OllamaAdapter(spec, settings, client)
            print('\nModel:', spec.name, '/', spec.model_id, flush=True)
            decision = await adapter.decide(game_state)
            print('Valid move:', decision.ok, '| Move:', decision.move or '<none>',
                  '| Time seconds:', round(decision.latency_ms / 1000, 2),
                  '| Local requests:', decision.local_requests, flush=True)
            print('Request diagnostics:', json.dumps(decision.attempt_log), flush=True)
            if decision.ok:
                nxt = apply_move(puzzle['state'], decision.move)
                new_dist = await asyncio.to_thread(exact_local_distance, nxt)
                print('Verified distance after proposed move:', new_dist,
                      '| Solved:', is_solved(nxt), flush=True)
            else:
                error = True
                print('Error:', decision.error, flush=True)
        return int(error)


def main() -> None:
    parser = argparse.ArgumentParser(description='One local Ollama cube move per installed model')
    parser.add_argument('--model', choices=[m.key for m in ollama_models()],
                        action='append', help='Test only the chosen model; repeat for several models')
    parser.add_argument('--timeout', type=float, default=240.0,
                        help='Local request timeout in seconds, not an OpenRouter timeout')
    parser.add_argument('--seed', type=int, default=383828,
                        help='Fixed reproducible puzzle seed; 383828 was a Clef success')
    args = parser.parse_args()
    keys = args.model or [m.key for m in ollama_models()]
    raise SystemExit(asyncio.run(check(keys, max(5.0, args.timeout), args.seed)))


if __name__ == '__main__':
    main()
