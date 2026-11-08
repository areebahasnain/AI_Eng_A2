"""OpenRouter adapters.

* ``DecisionsAdapter`` - POST /api/alpha/decisions (Jev, GPT-6 Luna Decisions, Clef).
  A typed ``choice`` question whose options are the 18 legal moves.
* ``ChatAdapter`` - POST /api/v1/chat/completions (Claude Opus 5.5), constrained to
  a JSON object ``{"move": "..."}`` via ``response_format`` when supported.

Both share one retry / timeout / validation policy (``_BaseAdapter.decide``), so no
model gets special treatment.  Malformed or illegal outputs are *never* silently
converted into moves: they are counted, logged, retried, and - if retries run out -
reported as a failed turn.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field

import httpx

from .config import ModelSpec, Settings
from .ledger import APILedger, QuotaExhausted
from .contract import (
    CHAT_RESPONSE_SCHEMA,
    CHAT_SYSTEM_PROMPT,
    QUESTION_ID,
    chat_user_message,
    decisions_questions,
)
from .cube import MOVE_SET

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
RUN_FATAL_STATUS = {401, 402, 403}  # bad key / no credits: every model would fail
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class InvalidOutput(Exception):
    """The model answered, but not with a legal single move."""


@dataclass
class Decision:
    move: str | None
    ok: bool
    latency_ms: float  # whole turn, including retries and back-off
    last_attempt_ms: float  # the final HTTP round trip only
    attempts: int
    retries: int
    invalid_outputs: int
    error: str | None = None
    confidence: float | None = None
    probability: float | None = None
    cost_usd: float | None = None
    http_status: int | None = None
    fatal_scope: str | None = None  # None | "model" | "run"
    attempt_log: list[dict] = field(default_factory=list)
    api_calls: int = 0
    cache_hits: int = 0
    live_latency_ms: float = 0.0
    cache_latency_ms: float = 0.0
    local_requests: int = 0


@dataclass
class _Attempt:
    kind: str  # ok | retry | invalid | fatal_model | fatal_run
    ms: float
    status: int | None = None
    move: str | None = None
    error: str | None = None
    confidence: float | None = None
    probability: float | None = None
    cost_usd: float | None = None
    retry_after: float | None = None
    adjusted: bool = False  # request was changed (e.g. structured output dropped); repeat now
    api_calls: int = 0
    cache_hits: int = 0
    live_latency_ms: float = 0.0
    cache_latency_ms: float = 0.0


def _error_message(body) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or err)[:300]
        if err:
            return str(err)[:300]
    return ""


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    try:
        return min(float(raw), 10.0) if raw is not None else None
    except ValueError:
        return None


class _BaseAdapter:
    path = ""

    def __init__(self, spec: ModelSpec, settings: Settings, client: httpx.AsyncClient | None = None,
                 ledger: APILedger | None = None):
        self.spec = spec
        self.settings = settings
        self._client = client
        self._owns_client = client is None
        self.ledger = ledger if ledger is not None else APILedger(settings.ledger_path)

    # -- plumbing -----------------------------------------------------------------
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.settings.request_timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    @property
    def url(self) -> str:
        return f"{self.settings.base_url}{self.path}"

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.app_url,
            "X-OpenRouter-Title": "Rubik's Cube Race (AI Engineering Assignment 02)",
        }

    # -- to be provided by subclasses ---------------------------------------------
    def build_payload(self, game_state: dict) -> dict:  # pragma: no cover - abstract
        raise NotImplementedError

    def parse(self, data: dict) -> tuple[str, float | None, float | None]:  # pragma: no cover
        """Return (move, confidence, probability_of_move) or raise InvalidOutput."""
        raise NotImplementedError

    def on_bad_request(self, message: str) -> bool:
        """Hook: return True if the payload was adjusted and the call should be repeated."""
        return False

    # -- one HTTP attempt ---------------------------------------------------------
    async def _attempt(self, payload: dict) -> _Attempt:
        """One request: durable claim BEFORE network I/O, then durable response/cache."""
        t0 = time.perf_counter()
        def ms() -> float:
            return (time.perf_counter() - t0) * 1000.0

        try:
            claim = self.ledger.claim(self.spec.key, self.spec.model_id, self.url, payload)
        except QuotaExhausted as exc:
            return _Attempt("quota", ms(), error=str(exc))
        if claim.cache_hit:
            status, body = 200, claim.cached_body
            api_calls, cache_hits = 0, 1
            network_ms, cache_ms = 0.0, claim.cache_ms
        else:
            api_calls, cache_hits = 1, 0
            try:
                resp = await self.client.post(
                    self.url, json=payload, headers=self.headers(),
                    timeout=self.settings.request_timeout_s,
                )
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                error = f"network error: {type(exc).__name__}"
                network_ms = ms()
                self.ledger.finish(claim, status=None, body=None,
                                   network_ms=network_ms, error=error)
                return _Attempt("retry", network_ms, error=error, api_calls=1,
                                live_latency_ms=network_ms)
            status = resp.status_code
            try:
                body = resp.json()
            except ValueError:
                body = None
            network_ms = ms()
            self.ledger.finish(claim, status=status, body=body if isinstance(body, dict) else None,
                               network_ms=network_ms)
            cache_ms = 0.0
        kw = dict(api_calls=api_calls, cache_hits=cache_hits,
                  live_latency_ms=network_ms, cache_latency_ms=cache_ms)
        message = _error_message(body)
        if status in RUN_FATAL_STATUS:
            return _Attempt("fatal_run", ms(), status, error=f"HTTP {status}: {message or 'rejected'}", **kw)
        if status in RETRYABLE_STATUS:
            return _Attempt("retry", ms(), status, error=f"HTTP {status}: {message}".strip(": "),
                            retry_after=_retry_after(resp) if not claim.cache_hit else None, **kw)
        if status in (400, 404, 422) and self.on_bad_request(message):
            return _Attempt("retry", ms(), status, error=f"HTTP {status} ({message}); adjusted request",
                            adjusted=True, **kw)
        if status >= 400:
            return _Attempt("fatal_model", ms(), status, error=f"HTTP {status}: {message}".strip(": "), **kw)
        if not isinstance(body, dict):
            return _Attempt("invalid", ms(), status, error="response body is not JSON", **kw)
        if body.get("error"):
            code = body["error"].get("code") if isinstance(body["error"], dict) else None
            kind = "retry" if code in RETRYABLE_STATUS or code is None else "fatal_model"
            return _Attempt(kind, ms(), status, error=f"upstream error: {message}", **kw)
        usage = body.get("usage")
        cost = float(usage["cost"]) if (api_calls and isinstance(usage, dict)
                    and isinstance(usage.get("cost"), (int, float))) else None
        try:
            move, conf, prob = self.parse(body)
        except InvalidOutput as exc:
            return _Attempt("invalid", ms(), status, error=str(exc), cost_usd=cost, **kw)
        return _Attempt("ok", ms(), status, move=move, confidence=conf,
                        probability=prob, cost_usd=cost, **kw)

    # -- one turn: identical retry policy for every model --------------------------
    async def decide(self, game_state: dict) -> Decision:
        s = self.settings
        payload = self.build_payload(game_state)
        max_attempts = s.max_retries + 1
        turn_start = time.perf_counter()
        attempts = invalid = 0
        api_calls = cache_hits = 0
        live_latency_ms = cache_latency_ms = 0.0
        log: list[dict] = []
        cost_total = 0.0
        saw_cost = False
        last: _Attempt | None = None

        while attempts < max_attempts:
            attempts += 1
            att = await self._attempt(payload)
            if att.error and s.api_key:
                att.error = att.error.replace(s.api_key, "[REDACTED]")
            last = att
            api_calls += att.api_calls
            cache_hits += att.cache_hits
            live_latency_ms += att.live_latency_ms
            cache_latency_ms += att.cache_latency_ms
            if att.cost_usd is not None:
                cost_total += att.cost_usd
                saw_cost = True
            if att.kind == "invalid":
                invalid += 1
            log.append(
                {
                    "attempt": attempts,
                    "kind": att.kind,
                    "http_status": att.status,
                    "ms": round(att.ms, 1),
                    "error": att.error,
                    "move": att.move,
                    "api_calls": att.api_calls,
                    "cache_hits": att.cache_hits,
                    "live_latency_ms": round(att.live_latency_ms, 2),
                    "cache_latency_ms": round(att.cache_latency_ms, 2),
                }
            )
            if att.adjusted:
                # Request was adjusted (e.g. structured output unsupported) - repeat
                # immediately without using up a retry.  Happens at most once per adapter.
                payload = self.build_payload(game_state)
                attempts -= 1
                continue
            if att.kind == "ok":
                return Decision(
                    move=att.move, ok=True,
                    latency_ms=(time.perf_counter() - turn_start) * 1000.0,
                    last_attempt_ms=att.ms, attempts=attempts, retries=attempts - 1,
                    invalid_outputs=invalid, confidence=att.confidence,
                    probability=att.probability,
                    cost_usd=cost_total if saw_cost else None,
                    http_status=att.status, attempt_log=log,
                    api_calls=api_calls, cache_hits=cache_hits,
                    live_latency_ms=live_latency_ms, cache_latency_ms=cache_latency_ms,
                )
            if att.kind in ("fatal_run", "fatal_model", "quota"):
                break
            if att.kind == "invalid" and att.cache_hits:
                break  # same prompt cannot change if the answer is already cached
            if att.kind == "invalid" and att.api_calls:
                break  # persisted invalid 200; repeating identical payload only replays it
            if attempts < max_attempts:  # transient failure; retry only if enabled
                delay = att.retry_after if att.retry_after is not None else min(
                    8.0, s.retry_backoff_s * (2 ** (attempts - 1))
                )
                if delay > 0:
                    await asyncio.sleep(delay)

        assert last is not None
        scope = {"fatal_run": "run", "fatal_model": "model", "quota": "quota"}.get(last.kind)
        return Decision(
            move=None, ok=False,
            latency_ms=(time.perf_counter() - turn_start) * 1000.0,
            last_attempt_ms=last.ms, attempts=attempts, retries=max(0, attempts - 1),
            invalid_outputs=invalid, error=last.error or "no valid move returned",
            cost_usd=cost_total if saw_cost else None,
            http_status=last.status, fatal_scope=scope, attempt_log=log,
            api_calls=api_calls, cache_hits=cache_hits,
            live_latency_ms=live_latency_ms, cache_latency_ms=cache_latency_ms,
        )


class DecisionsAdapter(_BaseAdapter):
    """POST /api/alpha/decisions with a typed ``choice`` question."""

    path = "/alpha/decisions"

    def build_payload(self, game_state: dict) -> dict:
        return {
            "model": self.spec.model_id,
            "state": game_state,
            "questions": decisions_questions(),
        }

    def parse(self, data: dict):
        answers = data.get("answers", data)
        answer = answers.get(QUESTION_ID) if isinstance(answers, dict) else None
        if not isinstance(answer, dict):
            raise InvalidOutput(f"response has no answers.{QUESTION_ID}")
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in MOVE_SET:
            raise InvalidOutput(f"illegal choice {str(choice)[:40]!r}")
        probs = answer.get("probabilities")
        prob = None
        if isinstance(probs, dict) and isinstance(probs.get(choice), (int, float)):
            prob = float(probs[choice])
        conf = answer.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else None
        return choice, conf, prob


class ChatAdapter(_BaseAdapter):
    """POST /api/v1/chat/completions, answer constrained to ``{"move": "..."}``."""

    path = "/v1/chat/completions"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._structured = self.settings.llm_structured

    def build_payload(self, game_state: dict) -> dict:
        s = self.settings
        payload: dict = {
            "model": self.spec.model_id,
            "messages": [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": chat_user_message(game_state)},
            ],
            "max_tokens": s.llm_max_tokens,
            "stream": False,
        }
        if self._structured:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "cube_move", "strict": True, "schema": CHAT_RESPONSE_SCHEMA},
            }
        if s.llm_temperature is not None:
            payload["temperature"] = s.llm_temperature
        if s.llm_reasoning_effort in {"low", "medium", "high"}:
            payload["reasoning"] = {"effort": s.llm_reasoning_effort}
        return payload

    def on_bad_request(self, message: str) -> bool:
        if self._structured and re.search(r"response_format|json_schema|structured", message, re.I):
            self._structured = False  # fall back to prompt-only JSON, still validated strictly
            return True
        return False

    def parse(self, data: dict):
        try:
            choice0 = data["choices"][0]
            content = choice0["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InvalidOutput("response has no choices[0].message.content")
        if isinstance(content, list):  # content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not isinstance(content, str) or not content.strip():
            reason = choice0.get("finish_reason") if isinstance(choice0, dict) else None
            raise InvalidOutput(f"empty content (finish_reason={reason})")
        text = content.strip()
        fence = _FENCE_RE.match(text)  # markdown fences are formatting, not a different answer
        if fence:
            text = fence.group(1).strip()
        try:
            obj = json.loads(text)
        except ValueError:
            raise InvalidOutput(f"not valid JSON: {text[:60]!r}")
        if not isinstance(obj, dict) or set(obj) != {"move"}:
            raise InvalidOutput(f"expected exactly {{\"move\": ...}}, got {text[:60]!r}")
        move = obj["move"]
        if not isinstance(move, str) or move not in MOVE_SET:
            raise InvalidOutput(f"illegal move {str(move)[:40]!r}")
        return move, None, None


def make_adapter(spec: ModelSpec, settings: Settings, client: httpx.AsyncClient | None = None,
                 ledger: APILedger | None = None):
    if settings.provider == "ollama":
        from .ollama import OllamaAdapter
        return OllamaAdapter(spec, settings, client)
    if settings.mock:
        from .mock import MockAdapter
        return MockAdapter(spec, settings)
    cls = DecisionsAdapter if spec.api == "decisions" else ChatAdapter
    return cls(spec, settings, client, ledger=ledger)
