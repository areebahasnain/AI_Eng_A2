"""One local inference check on the *actual downloaded* Ollama model.

Never contacts OpenRouter or reads/prints the OpenRouter key.
Use: python -m scripts.diagnose_local_models --model llama_local
"""
import argparse
import asyncio
import json

from backend.config import load_settings, ollama_models
from backend.contract import build_game_state
from backend.ollama import OllamaAdapter
from backend.progress import local_cycle_observation, one_step_sticker_observation
from backend.runner import build_puzzles


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=[m.key for m in ollama_models()], default='llama_local')
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    models = {m.key: m for m in ollama_models()}
    settings = load_settings()
    settings.provider, settings.mock = 'ollama', False
    puzzle = build_puzzles('primary', 1, args.seed, None)[0]
    state = build_game_state(puzzle['state'], [], 20, readable_grids=True)
    state.update(local_cycle_observation(puzzle['state'], {puzzle['state']}))
    if settings.ollama_sticker_hints:
        state.update(one_step_sticker_observation(puzzle['state'], {puzzle['state']}))
    model = models[args.model]
    print('One local test only. OpenRouter requests: ZERO')
    print('Model:', model.key, '=>', model.model_id)
    adapter = OllamaAdapter(model, settings)
    try:
        d = await adapter.decide(state)
    finally:
        await adapter.aclose()
    print('Valid move returned:', d.ok)
    print('Move:', d.move)
    print('Elapsed seconds:', round(d.latency_ms/1000, 2))
    print('Actual local requests:', d.local_requests)
    print('Invalid outputs:', d.invalid_outputs)
    print('Error:', d.error)
    print('Safe attempt diagnostic:', json.dumps(d.attempt_log, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
