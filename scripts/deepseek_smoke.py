"""Safe local-only DeepSeek diagnostic; never uses or prints an OpenRouter key.

Run: .\\.venv\\Scripts\\python.exe -m scripts.deepseek_smoke
Tests Ollama availability, model installation, then ONE short inference request.
"""
from __future__ import annotations
import asyncio
import time
import httpx
from backend.config import load_settings, ollama_models
from backend.deepseek_io import parse_deepseek_move
from backend.adapters import InvalidOutput


async def main():
    settings = load_settings()
    name = next(m.model_id for m in ollama_models() if m.key == 'deepseek_local')
    base = settings.ollama_base_url
    print('DeepSeek LOCAL-ONLY smoke check. OpenRouter API calls: ZERO')
    print('Model:', name, 'Ollama URL:', base)
    timeout = httpx.Timeout(connect=10, read=settings.ollama_request_timeout_s, write=20, pool=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            tags = (await client.get(base + '/api/tags')).json()
            installed = {m.get('name') for m in tags.get('models', [])}
            print('Model installed:', name in installed)
            if name not in installed:
                print('Check ollama list and OLLAMA_MODEL_DEEPSEEK in .env.'); return
            payload = {
                'model': name,
                'messages': [{'role':'user', 'content':
                    'Choose exactly one legal Rubik cube face turn from U R F D L B. '
                    'Respond with a SINGLE LETTER such as R. Do not explain.'}],
                'think': False, 'stream': False,
                'options': {'temperature': 0.0, 'num_predict': 256},
            }
            t0 = time.perf_counter()
            resp = await client.post(base + '/api/chat', json=payload)
            print('HTTP status:', resp.status_code)
            resp.raise_for_status()
            body = resp.json()
            message = body.get('message') or {}
            content = message.get('content') or ''
            print('Elapsed seconds:', round(time.perf_counter() - t0, 2))
            print('Final content characters:', len(content))
            print('Thinking characters:', len(message.get('thinking') or ''))
            print('Done reason:', body.get('done_reason'))
            print('Generated tokens:', body.get('eval_count'))
            try:
                move = parse_deepseek_move(content)
                print('SUCCESS: completed legal model-generated move:', move)
            except InvalidOutput as exc:
                print('NOT A VALID MOVE:', exc)
                print('No move was invented. Run the full-prompt diagnostic next.')
        except httpx.HTTPError as exc:
            print('Local Ollama connection/request failed:', type(exc).__name__, str(exc)[:250])


if __name__ == '__main__':
    asyncio.run(main())
