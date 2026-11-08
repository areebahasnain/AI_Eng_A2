"""Simulated models for offline development - NOT real results.

Mock mode lets you build/test the UI and the whole pipeline without spending API
credits.  The simulated "models" have invented speed/accuracy profiles; the UI
shows a red MOCK banner and every saved result file is stamped ``"mock": true``.
Never report mock numbers as experimental findings.
"""
from __future__ import annotations

import asyncio
import random
import time

from .adapters import Decision
from .config import ModelSpec, Settings
from .cube import MOVES, apply_move, correct_facelets
from .solver import shortest_path_cached

# latency range (seconds), probability of picking an optimal first move, probability a
# first attempt is malformed (exercises the retry/invalid-output accounting).
PROFILES = {
    "opus": dict(lat=(3.0, 9.0), p_opt=0.88, p_invalid=0.05),
    "jev": dict(lat=(0.12, 0.45), p_opt=0.35, p_invalid=0.0),
    "luna": dict(lat=(0.25, 0.80), p_opt=0.45, p_invalid=0.0),
    "clef": dict(lat=(0.18, 0.55), p_opt=0.30, p_invalid=0.0),
}
DEFAULT_PROFILE = dict(lat=(0.2, 0.6), p_opt=0.3, p_invalid=0.0)


class MockAdapter:
    def __init__(self, spec: ModelSpec, settings: Settings):
        self.spec = spec
        self.settings = settings
        self.profile = PROFILES.get(spec.key, DEFAULT_PROFILE)
        self.rng = random.Random(f"mock-{spec.key}")

    async def aclose(self) -> None:
        return None

    def _pick_move(self, state: str, shortest: tuple[str, ...] | None) -> str:
        if shortest:
            optimal = shortest[0]
            if self.rng.random() < self.profile["p_opt"]:
                return optimal
            return self.rng.choice([m for m in MOVES if m != optimal])
        # Deep state: greedy on facelet progress, with noise.
        if self.rng.random() < 0.5:
            return self.rng.choice(MOVES)
        scored = [(correct_facelets(apply_move(state, m)), m) for m in MOVES]
        best = max(s for s, _ in scored)
        return self.rng.choice([m for s, m in scored if s == best])

    async def decide(self, game_state: dict) -> Decision:
        state = game_state["cube_facelets"]
        turn_start = time.perf_counter()
        speed = self.settings.mock_speed
        shortest = await asyncio.to_thread(shortest_path_cached, state, 7)

        invalid = 0
        attempts = 1
        lo, hi = self.profile["lat"]
        log = []
        if self.rng.random() < self.profile["p_invalid"]:
            await asyncio.sleep(self.rng.uniform(lo, hi) / speed)
            invalid, attempts = 1, 2
            log.append({"attempt": 1, "kind": "invalid", "http_status": 200, "ms": 0.0,
                        "error": "mock: malformed output", "move": None})
        t_last = time.perf_counter()
        await asyncio.sleep(self.rng.uniform(lo, hi) / speed)
        move = self._pick_move(state, shortest)
        now = time.perf_counter()
        confidence = probability = None
        if self.spec.category == "decision":
            probability = round(self.rng.uniform(0.35, 0.95), 4)
            confidence = round(min(0.99, probability * self.rng.uniform(0.9, 1.05)), 4)
        log.append({"attempt": attempts, "kind": "ok", "http_status": 200,
                    "ms": round((now - t_last) * 1000, 1), "error": None, "move": move})
        return Decision(
            move=move, ok=True,
            latency_ms=(now - turn_start) * 1000.0,
            last_attempt_ms=(now - t_last) * 1000.0,
            attempts=attempts, retries=attempts - 1, invalid_outputs=invalid,
            confidence=confidence, probability=probability, cost_usd=None,
            http_status=200, attempt_log=log,
        )
