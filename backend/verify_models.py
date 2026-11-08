"""Safe model-ID helper (NO network by default).

  python -m backend.verify_models            # prints configured IDs, zero calls
  python -m backend.verify_models --online   # optional catalog GETs, no key sent

For a teacher-provided restricted key, avoid optional probes unless approved.
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from .config import load_settings


async def _online() -> int:
    s = load_settings()
    print('Catalog lookup only: no OpenRouter API key is sent in this tool.')
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f'{s.base_url}/v1/models')
            r.raise_for_status()
            found = {item.get('id') for item in r.json().get('data', [])}
        except (httpx.HTTPError, ValueError) as exc:
            print(f'Could not fetch model catalog: {type(exc).__name__}')
            return 1
    missing = False
    for m in s.models:
        yes = m.model_id in found
        print(f'{"CATALOG LISTED" if yes else "NOT CONFIRMED":15} {m.name}: {m.model_id}')
        missing |= not yes
    print('Note: listing a model does not prove your individual key is authorized to call it.')
    return 1 if missing else 0


def main() -> int:
    s = load_settings()
    if '--online' in sys.argv[1:]:
        return asyncio.run(_online())
    print('OFFLINE CONFIGURATION ONLY: no network requests or API credits used.')
    for m in s.models:
        print(f'  {m.name:25} {m.model_id:34} ({m.api})')
    print('Use --online only if an optional catalog GET is appropriate.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
