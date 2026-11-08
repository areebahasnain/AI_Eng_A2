r"""Paired Ollama prompt-order A/B diagnostic (never calls OpenRouter).

Use from project root, e.g.:
  .\.venv\Scripts\python.exe -m scripts.compare_local_prompts --model gemma_local --seed 483 --puzzles 2
  .\.venv\Scripts\python.exe -m scripts.compare_local_prompts --model clef_local --seed 483 --puzzles 1
  .\.venv\Scripts\python.exe -m scripts.compare_local_prompts --model clef_local --dry-run

Tests two configurations on the SAME verified three-move puzzles:
  legacy = old chat example and fixed action order
  neutral = no literal move example and state-seeded action rotation
Outputs raw moves, legal validity, whether first move reduces exact distance,
request latency, and actual local Ollama call count. A positive first move is
NOT a successful full solve. No reference solution is supplied to the models.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from backend.config import load_settings, ollama_models
from backend.contract import build_game_state
from backend.cube import MOVES, apply_move
from backend.ollama import OllamaAdapter
from backend.progress import local_cycle_observation
from backend.runner import build_puzzles
from backend.solver import shortest_path_cached


async def main_async(args):
    specs = {s.key: s for s in ollama_models()}
    spec = specs[args.model]
    puzzles = build_puzzles('primary', args.puzzles, args.seed, None)
    results = []
    for puzzle in puzzles:
        state = build_game_state(puzzle['state'], [], 20, readable_grids=True)
        state.update(local_cycle_observation(puzzle['state'], {puzzle['state']}))
        optimal_first = {move for move in MOVES
                         if shortest_path_cached(apply_move(puzzle['state'], move), 2) is not None}
        for label, rotate in [('legacy', False), ('neutral', True)]:
            settings = load_settings()
            settings.provider = 'ollama'
            settings.mock = False
            settings.ollama_prompt_variant = label
            settings.ollama_rotate_actions = rotate
            settings.ollama_request_timeout_s = args.timeout
            adapter = OllamaAdapter(spec, settings)
            path, payload = adapter._payload(state)
            request_json = json.dumps(payload)
            assert 'distance_reducing_choices' not in request_json
            assert 'shortest_path' not in request_json
            if args.dry_run:
                print(f'{puzzle["id"]} {label:7s} endpoint={path} payload_chars={len(request_json)} '
                      '(no model requests)')
                continue
            try:
                decision = await adapter.decide(state)
            finally:
                await adapter.aclose()
            row = {
                'puzzle_id': puzzle['id'], 'model': spec.model_id, 'prompt_variant': label,
                'seed': args.seed, 'legal_move': bool(decision.ok),
                'move': decision.move if decision.ok else None,
                'optimal_first_move': bool(decision.ok and decision.move in optimal_first),
                'local_requests': decision.local_requests, 'latency_ms': round(decision.latency_ms, 1),
                'invalid_outputs': decision.invalid_outputs, 'error': decision.error,
            }
            results.append(row)
            print(f'{puzzle["id"]:22s} {label:7s} move={str(row["move"]):4s} '
                  f'valid={row["legal_move"]} optimal_first={row["optimal_first_move"]} '
                  f'time={row["latency_ms"]:.0f}ms requests={row["local_requests"]}')
    if args.dry_run:
        return
    destination = Path(args.output)
    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.write_text(json.dumps({
        'description': 'Paired local Ollama first-move comparison. NOT full solve rates.',
        'seed': args.seed, 'model': spec.model_id, 'rows': results,
    }, indent=2), encoding='utf-8')
    print('Saved:', destination)
    for variant in ('legacy', 'neutral'):
        subset = [row for row in results if row['prompt_variant'] == variant]
        print(f'{variant}: {sum(r["optimal_first_move"] for r in subset)}/{len(subset)} '
              'optimal first moves; ' +
              f'{sum(r["legal_move"] for r in subset)}/{len(subset)} valid output')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=[m.key for m in ollama_models()], default='gemma_local')
    parser.add_argument('--seed', type=int, default=483)
    parser.add_argument('--puzzles', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=240)
    parser.add_argument('--output', default='results/local-prompt-ab.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.puzzles <= 20:
        parser.error('--puzzles must be between 1 and 20')
    if not 10 <= args.timeout <= 3600:
        parser.error('--timeout must be between 10 and 3600')
    asyncio.run(main_async(args))


if __name__ == '__main__':
    main()
