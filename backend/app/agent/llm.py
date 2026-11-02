"""Thin async wrapper over Groq chat completions (OpenAI-compatible)."""

import asyncio
import json
import logging
from dataclasses import dataclass, field

import groq

from app.config import GROQ_API_KEY, GROQ_FAST_MODEL, GROQ_MODEL

log = logging.getLogger(__name__)
_clients: dict[int, groq.AsyncGroq] = {}
MAX_QUOTA_WAIT = 60  # seconds; the free quotas refill within a minute
BUSY = "The assistant is busy (rate limit reached). Please try again in a minute."


class LLMUnavailable(Exception):
    """Raised with a user-presentable message."""


def client(max_retries: int = 2) -> groq.AsyncGroq:
    """max_retries=0 for the main model: on a 429 we'd rather switch to the
    fast model at once than sit in the SDK's retry-after back-off (~20 s)."""
    if not GROQ_API_KEY:
        raise LLMUnavailable("GROQ_API_KEY is not configured on the server.")
    if max_retries not in _clients:
        _clients[max_retries] = groq.AsyncGroq(api_key=GROQ_API_KEY, max_retries=max_retries, timeout=45)
    return _clients[max_retries]


def estimate_tokens(value) -> int:
    """Cheap token estimate (~3.6 chars/token for English) used for budgeting."""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    return int(len(value) / 3.6) + 1


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str = ""


@dataclass
class RoundResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""


def _params(model: str) -> dict:
    params = {"temperature": 0.1, "max_completion_tokens": 1200}
    if "gpt-oss" in model:
        # Keep hidden reasoning short: it counts against the 8K tokens/minute quota.
        params["extra_body"] = {"reasoning_effort": "low"}
    return params


def _retry_after(exc: groq.RateLimitError) -> int:
    return int(float(exc.response.headers.get("retry-after", MAX_QUOTA_WAIT + 1))) + 1


async def stream_round(messages, tools=None, tool_choice="auto", model=GROQ_MODEL, on_token=None, on_wait=None) -> RoundResult:
    """One streamed completion. Text deltas go to on_token; tool calls are accumulated.

    On a rate limit, switches to the other model, which has its own separate quota
    on Groq. If that's used up too, waits once for it, telling the student via on_wait.
    """
    other = GROQ_FAST_MODEL if model != GROQ_FAST_MODEL else GROQ_MODEL
    try:
        try:
            return await _stream_once(messages, tools, tool_choice, model, on_token, retries=0)
        except (groq.APITimeoutError, groq.APIConnectionError) as exc:
            log.warning("transient Groq error on %s (%s); retrying once", model, exc.__class__.__name__)
            return await _stream_once(messages, tools, tool_choice, model, on_token, retries=0)
    except groq.RateLimitError as exc:
        first_wait = _retry_after(exc)
        log.warning("rate limited on %s; falling back to %s", model, other)
    try:
        try:
            return await _stream_once(messages, tools, tool_choice, other, on_token, retries=0)
        except groq.RateLimitError as exc:
            # A model out of its daily quota stays out for a while: wait for the one that frees up first.
            seconds, sooner = min((_retry_after(exc), other), (first_wait, model))
            if on_wait is None or seconds > MAX_QUOTA_WAIT:
                raise LLMUnavailable(BUSY)
            await on_wait(seconds)
            await asyncio.sleep(seconds)
            return await _stream_once(messages, tools, tool_choice, sooner, on_token, retries=0)
    except groq.RateLimitError:
        raise LLMUnavailable(BUSY)
    except (groq.APITimeoutError, groq.APIConnectionError):
        raise LLMUnavailable("Couldn't reach the language model. Please try again.")


async def _stream_once(messages, tools, tool_choice, model, on_token, retries=2) -> RoundResult:
    kwargs = dict(model=model, messages=messages, stream=True, **_params(model))
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    try:
        stream = await client(retries).chat.completions.create(**kwargs)
    except groq.APIStatusError as exc:
        if exc.status_code == 413:
            raise LLMUnavailable("This conversation has become too long for the model. Please start a new chat.")
        raise
    result = RoundResult(model=model)
    calls: dict[int, ToolCall] = {}
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            result.content += delta.content
            if on_token:
                await on_token(delta.content)
        for tc in delta.tool_calls or []:
            call = calls.setdefault(tc.index, ToolCall(id=tc.id or "", name=""))
            if tc.id:
                call.id = tc.id
            if tc.function and tc.function.name:
                call.name = tc.function.name
            if tc.function and tc.function.arguments:
                call.arguments += tc.function.arguments
    result.tool_calls = [calls[i] for i in sorted(calls)]
    return result


async def complete(messages, model=GROQ_FAST_MODEL, max_tokens=400, temperature=None) -> str:
    """Non-streamed completion (summaries, email drafts). Falls back to the fast
    model when the main one is rate limited."""
    params = _params(model)
    params["max_completion_tokens"] = max_tokens
    if temperature is not None:
        params["temperature"] = temperature
    try:
        resp = await client(0 if model != GROQ_FAST_MODEL else 2).chat.completions.create(
            model=model, messages=messages, **params)
    except groq.RateLimitError:
        if model == GROQ_FAST_MODEL:
            raise LLMUnavailable("The assistant is busy (rate limit reached). Please try again in a minute.")
        log.warning("rate limited on %s; falling back to %s", model, GROQ_FAST_MODEL)
        return await complete(messages, GROQ_FAST_MODEL, max_tokens, temperature)
    return (resp.choices[0].message.content or "").strip()
