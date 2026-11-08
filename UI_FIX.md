# Fix: "Failed to initialise UI: Cannot set properties of null (setting 'checked')"

The uploaded frontend contains no `.checked = ...` assignment, even though the browser reported one. This is consistent with the browser running a cached, older `/static/app.js` against the newer HTML controls.

## Changes

- The backend now embeds content-based version hashes in the HTML URLs for `app.js` and `style.css`.
- HTML and static assets have `Cache-Control: no-store`, preventing stale browser copies from being reused.
- Frontend initialization checks its expected controls and reports which HTML IDs are missing if a future update becomes inconsistent.
- Regression tests cover asset versioning and required control IDs.

## Recommended upgrade (Windows PowerShell)

1. Stop the server with `Ctrl+C`.
2. Apply the **patch ZIP** on top of the existing `rubiks-cube-race` folder, preserving its directory structure. Overwrite the matching project files only.
3. **Do not remove or replace** `.env`, `data/usage.sqlite3`, or `results/`. These contain your private settings, cumulative API counts/cache, and past results.
4. Restart your backend:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
   ```

5. Open `http://localhost:8000` and press `Ctrl+Shift+R` once.

If using the complete ZIP in a **new** folder, copy your current private `.env`, existing `data/usage.sqlite3`, and any `results/` files into the replacement folder first. Recreate the virtual environment and install requirements; `.venv` is intentionally not packaged.

**Security:** Neither ZIP contains your real `.env`, private API key, local virtual environment, usage database, or recorded runs. The backend's quota enforcement has not been weakened and no paid API requests were made to test this fix.

## Validation

- Browser smoke test with mocked backend responses: UI initialized, 4 model cards rendered, no JavaScript errors.
- Python automated test suite: 81 passed.
