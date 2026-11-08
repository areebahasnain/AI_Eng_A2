"""Local-only Ollama health probe; no OpenRouter calls or credential printing.

Examples (Windows PowerShell):
  .\\.venv\\Scripts\\python.exe -m scripts.ollama_probe --model llama_local
  .\\.venv\\Scripts\\python.exe -m scripts.ollama_probe --model gemma_local
  .\\.venv\\Scripts\\python.exe -m scripts.ollama_probe --model llama_local --full

A simple response establishes that the downloaded model can complete a short
request. --full uses one of the benchmark's exactly-three-moves-away states.
"""
from __future__ import annotations
import argparse
import asyncio
import time
from typing import Any

import httpx
from backend.config import load_settings, ollama_models
from backend.contract import build_game_state
from backend.ollama import OllamaAdapter
from backend.progress import local_cycle_observation, one_step_sticker_observation
from backend.runner import build_puzzles


def _s(value: Any) -> str:
    return str(value)[:160] if value is not None else 'unknown'


async def main() -> None:
    parser = argparse.ArgumentParser(description='Check local Ollama model health without any cloud API usage')
    parser.add_argument('--model', choices=[m.key for m in ollama_models()], default='llama_local')
    parser.add_argument('--timeout', type=float, default=60.0, help='per-request local timeout seconds')
    parser.add_argument('--full', action='store_true', help='also test one real three-move cube state')
    args = parser.parse_args()
    s = load_settings()
    spec = next(m for m in ollama_models() if m.key == args.model)
    print('LOCAL ONLY. OpenRouter requests: ZERO. API key is not used.', flush=True)
    print('Model:', spec.model_id, 'Endpoint:', s.ollama_base_url, flush=True)
    timeout = httpx.Timeout(connect=10, read=max(5.0, args.timeout), write=20, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            tags = (await client.get(s.ollama_base_url + '/api/tags')).json()
            installed = [m.get('name') for m in tags.get('models', [])]
            print('Installed exact model tag:', spec.model_id in installed, flush=True)
            if spec.model_id not in installed:
                print('Installed models:', ', '.join(_s(x) for x in installed), flush=True)
                return
            try:
                ps = (await client.get(s.ollama_base_url + '/api/ps')).json()
                for m in ps.get('models', []):
                    print('Loaded:', _s(m.get('name')), 'RAM bytes:', _s(m.get('size')),
                          'VRAM bytes:', _s(m.get('size_vram')), flush=True)
            except httpx.HTTPError:
                pass

            if spec.api == 'systemone':
                print('Clef Flash uses a separate /v1/systemone endpoint; run --full to test it.', flush=True)
            else:
                request = {
                    'model': spec.model_id,
                    'messages': [{'role': 'user', 'content':
                                  'Choose any ONE valid Rubik cube face turn. '
                                  'Your entire final answer must be exactly U.'}],
                    'stream': False, 'think': False,
                    'options': {'temperature': 0, 'num_predict': 128},
                }
                t0 = time.perf_counter()
                response = await client.post(s.ollama_base_url + '/api/chat', json=request)
                print('Simple prompt HTTP:', response.status_code, flush=True)
                response.raise_for_status()
                data = response.json()
                msg = data.get('message') or {}
                content = msg.get('content') or ''
                print('Simple prompt response:', repr(content[:80]), flush=True)
                print('Thinking characters:', len(msg.get('thinking') or ''),
                      'Final characters:', len(content), flush=True)
                print('Done reason:', _s(data.get('done_reason')),
                      'Generated tokens:', _s(data.get('eval_count')),
                      'Prompt tokens:', _s(data.get('prompt_eval_count')),
                      'Load ms:', round((data.get('load_duration') or 0)/1e6),
                      'Elapsed sec:', round(time.perf_counter()-t0, 2), flush=True)
            if args.full:
                puzzle = build_puzzles('primary', 1, 17, None)[0]
                state = build_game_state(puzzle['state'], [], 20, readable_grids=True)
                state.update(local_cycle_observation(puzzle['state'], {puzzle['state']}))
                if s.ollama_sticker_hints:
                    state.update(one_step_sticker_observation(puzzle['state'], {puzzle['state']}))
                s.ollama_request_timeout_s = max(5.0, args.timeout)
                # Reuse the same client, local-only; no live OpenRouter routes.
                adapter = OllamaAdapter(spec, s, client)
                print('Starting ONE full cube decision...', flush=True)
                result = await adapter.decide(state)
                print('Full prompt valid move:', result.ok,
                      'Move:', result.move or '<none>',
                      'Seconds:', round(result.latency_ms/1000, 2),
                      'Local attempts:', result.local_requests, flush=True)
                for item in result.attempt_log:
                    print('Attempt:', item.get('attempt'), 'Mode:', item.get('decode_mode'),
                          'Error:', _s(item.get('error')), 'Details:', _s(item.get('detail')),
                          'Done reason:', _s(item.get('done_reason')),
                          'Tokens:', _s(item.get('eval_count')), 'Final chars:', _s(item.get('output_chars')),
                          'Thinking chars:', _s(item.get('thinking_chars')), flush=True)
                if result.error:
                    print('Final error:', result.error, flush=True)
        except httpx.HTTPError as exc:
            print('Local Ollama request failed:', type(exc).__name__, _s(exc), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
