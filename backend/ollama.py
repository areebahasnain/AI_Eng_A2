"""Ollama local adapters for Clef Flash, Qwen, Llama 3.2, and Gemma.

Never calls OpenRouter. Clef uses System One, and the other three use
Ollama's native chat interface. No model is given a reference solution,
no model-selected move is rewritten in the independent benchmark.
"""
from __future__ import annotations

import json
import hashlib
import random
import re
import time

import httpx

from .adapters import Decision, DecisionsAdapter, InvalidOutput
from .config import ModelSpec, Settings
from .contract import (OLLAMA_CHAT_SYSTEM_PROMPT, OLLAMA_LEGACY_CHAT_SYSTEM_PROMPT,
                       ollama_chat_user_message, ollama_decisions_questions,
                       ollama_chat_response_schema)
from .cube import MOVES

_LEGAL = frozenset(MOVES)
_FENCE = re.compile(r"^```(?:json|text)?\s*\n?(.*?)\n?```$", re.I | re.S)


def parse_local_move(content: str) -> str:
    """Accept ONLY an unambiguous model-produced legal face turn.

    An Ollama model may ignore the requested JSON format and answer with one
    move, a JSON string, or a code-fenced JSON object. Accept those without
    ever scavenging a move from explanations or unfinished thinking.
    """
    if not isinstance(content, str) or not content.strip():
        raise InvalidOutput("local model returned empty final content")
    text = content.strip()
    fence = _FENCE.fullmatch(text)
    if fence:
        text = fence.group(1).strip()
    if text in _LEGAL:
        return text
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidOutput("expected one legal move or a single JSON move field") from exc
    if isinstance(obj, str) and obj in _LEGAL:
        return obj
    if isinstance(obj, dict) and set(obj) == {"move"} and obj["move"] in _LEGAL:
        return obj["move"]
    raise InvalidOutput("response has no single unambiguous legal move")


def action_order_for_observation(game_state: dict, rotate: bool = True) -> list[str]:
    """Non-oracle order rotation; both API styles receive the same ordering.

    Different states and histories yield different choice positions, reducing
    dependence on the first enum/choice (formerly always the upper-face move).
    No cube solver, good-move score or reference solution is consulted.
    """
    moves = list(MOVES)
    if rotate:
        fingerprint = json.dumps({
            "cube_facelets": game_state.get("cube_facelets", ""),
            "recent_moves": game_state.get("recent_moves", []),
        }, sort_keys=True, separators=(",", ":"))
        seed = int.from_bytes(hashlib.sha256(fingerprint.encode()).digest()[:8], "big")
        random.Random(seed).shuffle(moves)
    return moves


class OllamaAdapter:
    def __init__(self, spec: ModelSpec, settings: Settings, client: httpx.AsyncClient | None = None):
        self.spec = spec
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    async def aclose(self):
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _payload(self, state: dict, recovery: bool = False) -> tuple[str, dict]:
        moves = action_order_for_observation(state, self.settings.ollama_rotate_actions)
        if self.spec.api == "systemone":
            return "/v1/systemone", {
                "model": self.spec.model_id,
                "state": state,
                "questions": ollama_decisions_questions(moves),
            }
        payload = {
            "model": self.spec.model_id,
            "stream": False,
            "think": not self.settings.ollama_disable_thinking,
            "keep_alive": "2m",
            "messages": [
                {"role": "system", "content": (OLLAMA_LEGACY_CHAT_SYSTEM_PROMPT
                    if self.settings.ollama_prompt_variant == "legacy" else OLLAMA_CHAT_SYSTEM_PROMPT)},
                {"role": "user", "content": ollama_chat_user_message(state, moves)},
            ],
            "options": {
                "num_predict": self.settings.ollama_max_tokens,
                "temperature": 0.1,
            },
        }
        if recovery:
            # One strictly bounded retry only after an invalid *completed*
            # response. Never retry HTTP timeouts, which are slow locally.
            # We use a different output format without changing cube facts.
            payload["format"] = {"type": "string", "enum": moves}
            payload["options"]["num_predict"] = min(48, self.settings.ollama_max_tokens)
            payload["messages"][0]["content"] += (
                ' On this attempt reply with exactly one JSON string whose value is a legal move; no example, no commentary.'
            )
        else:
            payload["format"] = ollama_chat_response_schema(moves)
        return "/api/chat", payload

    async def decide(self, game_state: dict) -> Decision:
        started = time.perf_counter()
        timeout = httpx.Timeout(
            connect=10, read=self.settings.ollama_request_timeout_s,
            write=30, pool=30,
        )
        client = self._client or httpx.AsyncClient(timeout=timeout)
        if self._client is None:
            self._client = client

        log = []
        invalid = 0
        last_ms = 0.0
        last_error = None
        fatal_scope = None
        # Clef is a one-forward-pass decision model. Keep exactly one call.
        # Chat models get ONE extra bounded attempt for malformed outputs.
        max_attempts = 1 if self.spec.api == "systemone" else 2
        for attempt in range(1, max_attempts + 1):
            path, payload = self._payload(game_state, recovery=attempt > 1)
            attempt_started = time.perf_counter()
            body: dict = {}
            content = ""
            try:
                response = await client.post(self.settings.ollama_base_url + path,
                                             json=payload, timeout=timeout)
                response.raise_for_status()
                body = response.json()
                if self.spec.api == "systemone":
                    move, conf, prob = DecisionsAdapter.parse(self, body)
                else:
                    message = body.get("message") or {}
                    content = message.get("content") or ""
                    try:
                        move = parse_local_move(content)
                    except InvalidOutput as exc:
                        raise InvalidOutput(
                            f"{exc}; done_reason={body.get('done_reason')}, "
                            f"thinking_chars={len(message.get('thinking') or '')}, "
                            f"eval_count={body.get('eval_count')}"
                        ) from exc
                    conf = prob = None
                last_ms = (time.perf_counter() - attempt_started) * 1000
                log.append({
                    "attempt": attempt, "kind": "local", "ms": last_ms,
                    "api_calls": 0, "local_requests": 1,
                    "done_reason": body.get("done_reason"),
                    "output_chars": len(content),
                    "thinking_chars": len((body.get("message") or {}).get("thinking") or ""),
                    "eval_count": body.get("eval_count"),
                    "decode_mode": "systemone" if self.spec.api == "systemone" else (
                        "json_string_recovery" if attempt > 1 else "json_object"),
                })
                total_ms = (time.perf_counter() - started) * 1000
                return Decision(move, True, total_ms, last_ms, attempt,
                                attempt - 1, invalid,
                                confidence=conf, probability=prob, attempt_log=log,
                                live_latency_ms=total_ms, local_requests=attempt)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, InvalidOutput) as exc:
                last_ms = (time.perf_counter() - attempt_started) * 1000
                if isinstance(exc, httpx.ReadTimeout):
                    detail = (f"No answer from {self.spec.model_id} within "
                              f"{self.settings.ollama_request_timeout_s:g}s. "
                              "Check ollama ps, RAM/VRAM, and disable Parallel.")
                elif isinstance(exc, httpx.ConnectError):
                    detail = "Cannot connect to Ollama at " + self.settings.ollama_base_url
                elif isinstance(exc, httpx.HTTPStatusError):
                    detail = f"HTTP {exc.response.status_code}: {exc.response.text[:140]}"
                else:
                    detail = str(exc)[:250] or "No model response"
                if isinstance(exc, InvalidOutput):
                    invalid += 1
                if isinstance(exc, httpx.HTTPStatusError):
                    fatal_scope = "model"
                last_error = f"Local Ollama: {type(exc).__name__}: {detail}"
                log.append({
                    "attempt": attempt, "kind": "local_error", "ms": last_ms,
                    "api_calls": 0, "local_requests": 1,
                    "done_reason": body.get("done_reason"),
                    "output_chars": len(content),
                    "thinking_chars": len((body.get("message") or {}).get("thinking") or ""),
                    "eval_count": body.get("eval_count"),
                    "decode_mode": "systemone" if self.spec.api == "systemone" else (
                        "json_string_recovery" if attempt > 1 else "json_object"),
                    "error": type(exc).__name__, "detail": detail,
                })
                # One recovery ONLY for malformed output, not timeout/network.
                if not (self.spec.api != "systemone" and attempt == 1 and
                        isinstance(exc, InvalidOutput)):
                    break
        total_ms = (time.perf_counter() - started) * 1000
        return Decision(None, False, total_ms, last_ms, len(log),
                        max(0, len(log) - 1), invalid, error=last_error,
                        fatal_scope=fatal_scope, local_requests=len(log),
                        live_latency_ms=total_ms, attempt_log=log)
