# Offline verification receipt

Project source: user's `rubiks-cube-race (9).zip` with private `.env`, virtual environment, results, and SQLite database excluded from the output.

- Existing tests: 122 passing before modifications.
- Updated tests: 129 passing after changes.
- JavaScript syntax: `node --check frontend/app.js` successful.
- Local A/B payload dry-run: successful for Gemma and Clef; uses no model calls.
- Exactly-three-move invariant: verified with the cube engine for 256 independently seeded puzzles.
- Local action order: on 256 such puzzle states, initial action was `U` 15 times with the state-seeded ordering; formerly `U` was presented first 256/256 times. This is *presentation-order coverage*, not model solve accuracy.
- No actual inference on Clef, Qwen, Llama 3.2, or Gemma has been performed here. Their weights reside on the user's D: drive; the true effect on solve success requires user-side tests.
- No OpenRouter calls were made and no restricted key was used.
- The source ZIP and patch exclude `.env`, the `.venv` directory, `results/`, and `data/usage.sqlite3`.

Changes to prompting are **not** guaranteed to make small models solve a 3x3 cube. Keep solver guidance OFF for fair independent-model results; if enabled, assisted results are labeled and excluded from model-only success rates.
