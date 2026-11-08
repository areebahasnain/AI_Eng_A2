# Clef & Llama 3.2 update — November 8, 2026

- Retired DeepSeek (`deepseek_local`) from Ollama's four-model roster.
- Added Meta Llama 3.2 3B (`llama_local`, `OLLAMA_MODEL_LLAMA=llama3.2:3b`). Ollama tag is downloadable to `D:\OllamaModels` via `ollama pull llama3.2:3b`.
- Kept the System One request to `/v1/systemone` and Clef's original model-selected response. No forced reranking or hidden optimal-move substitutions.
- Examined saved user run histories: Clef solved 3 of 4 recent completed runs; the later failed seed differs from the solved seeds. One failing prompt/seed does not establish an API regression.
- Identified a heuristic trap: the sticker-count scorecard prefers `D2` on seed 734383 although `D` decreases the true distance from 3 to 2. Sticker hints are now **OFF by default** (`OLLAMA_STICKER_HINTS=0`). They remain optional for disclosed experimental comparisons.
- Compact per-move sticker counts and removed duplicated prose in the optional scorecard, reducing local System One payload size.
- Added robust parsing of plain legal move text and JSON legal-move objects for the three local chat models, with at most one local retry if (and only if) a completed answer is invalid. Neither retry nor parsing creates a new move independently.
- Added `scripts/local_preflight.py` to verify installed tags and make ONE same-seed local decision per selected model, reporting format, latency, exact one-step distance, and errors.
- Hosted OpenRouter adapters, persistent ledger, and the teacher's API quotas are unchanged.
- Tests run offline. Actual Clef and Llama model weights require the user's local Ollama installation and cannot be tested in this authoring environment.
