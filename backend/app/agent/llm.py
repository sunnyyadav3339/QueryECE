"""Thin async wrapper over Groq chat completions (OpenAI-compatible)."""

import json
import logging
from dataclasses import dataclass, field

import groq

from app.config import GROQ_API_KEY, GROQ_FAST_MODEL, GROQ_MODEL

log = logging.getLogger(__name__)
_clients: dict[int, groq.AsyncGroq] = {}


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


async def stream_round(messages, tools=None, tool_choice="auto", model=GROQ_MODEL, on_token=None) -> RoundResult:
    """One streamed completion. Text deltas go to on_token; tool calls are accumulated.

    On a rate limit for the main model, retries once on the fast model, which
    has its own separate quota on Groq.
    """
    try:
        try:
            return await _stream_once(messages, tools, tool_choice, model, on_token, retries=0)
        except (groq.APITimeoutError, groq.APIConnectionError) as exc:
            log.warning("transient Groq error on %s (%s); retrying once", model, exc.__class__.__name__)
            return await _stream_once(messages, tools, tool_choice, model, on_token, retries=0)
    except groq.RateLimitError:
        if model == GROQ_FAST_MODEL:
            raise LLMUnavailable("The assistant is busy (rate limit reached). Please try again in a minute.")
        log.warning("rate limited on %s; falling back to %s", model, GROQ_FAST_MODEL)
    try:
        return await _stream_once(messages, tools, tool_choice, GROQ_FAST_MODEL, on_token, retries=2)
    except groq.RateLimitError:
        raise LLMUnavailable("The assistant is busy (rate limit reached). Please try again in a minute.")
    except (groq.APITimeoutError, groq.APIConnectionError):
        raise LLMUnavailable("Couldn't reach the language model. Please try again.")


async def _stream_once(messages, tools, tool_choice, model, on_token, retries=2) -> RoundResult:
    kwargs = dict(model=model, messages=messages, stream=True, **_params(model))
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    stream = await client(retries).chat.completions.create(**kwargs)
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


async def complete(messages, model=GROQ_FAST_MODEL, max_tokens=400) -> str:
    """Non-streamed completion for housekeeping (summaries)."""
    params = _params(model)
    params["max_completion_tokens"] = max_tokens
    resp = await client().chat.completions.create(model=model, messages=messages, **params)
    return (resp.choices[0].message.content or "").strip()
