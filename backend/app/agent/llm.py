"""Thin async wrapper over Groq chat completions (OpenAI-compatible)."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

import groq

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, GROQ_FAST_MODEL, GROQ_MODEL

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
            if GEMINI_API_KEY:  # a different provider with its own free quota
                try:
                    return await _stream_gemini(messages, tools, tool_choice, on_token)
                except GeminiFailed as gexc:
                    log.warning("Gemini backup failed: %s", gexc)
                    if gexc.streamed:  # part of an answer is already on screen
                        raise LLMUnavailable(BUSY)
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


# --- Gemini backup -----------------------------------------------------------

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# The student's own CV text stays with Groq: free-tier Gemini content may be used by Google.
CV_EXCERPT = re.compile(
    r"\n?CV excerpt \(written by the student\):\n.*?(?=\nProfessors whose listed research|\n\(No research interests|\Z)", re.S)


class GeminiFailed(Exception):
    def __init__(self, message: str, streamed: bool = False):
        super().__init__(message)
        self.streamed = streamed  # True once text reached the student


def without_cv(messages: list[dict]) -> list[dict]:
    return [{**m, "content": CV_EXCERPT.sub("", m["content"])} if isinstance(m.get("content"), str) else m
            for m in messages]


def for_gemini(messages: list[dict]) -> list[dict]:
    """Gemini's OpenAI-compatible endpoint reads only the first system message, but the
    agent passes tool results and the "answer now" instruction as later ones: send those
    as user turns, merged with any neighbouring plain user turn."""
    out: list[dict] = []
    for i, m in enumerate(without_cv(messages)):
        if m["role"] == "system" and i > 0:
            m = {"role": "user", "content": m["content"]}
        prev = out[-1] if out else None
        if (prev and m["role"] == "user" and prev["role"] == "user"
                and isinstance(prev.get("content"), str) and isinstance(m.get("content"), str)):
            out[-1] = {"role": "user", "content": prev["content"] + "\n\n" + m["content"]}
        else:
            out.append(m)
    return out


async def _stream_gemini(messages, tools, tool_choice, on_token) -> RoundResult:
    """One streamed completion from Gemini's OpenAI-compatible endpoint."""
    payload = {"model": GEMINI_MODEL, "messages": for_gemini(messages), "stream": True,
               "temperature": 0.1, "max_tokens": 1200}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    result = RoundResult(model=GEMINI_MODEL)
    calls: dict[int, ToolCall] = {}
    log.info("answering with the Gemini backup (%s)", GEMINI_MODEL)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10)) as http:
            async with http.stream("POST", GEMINI_URL, json=payload,
                                   headers={"Authorization": f"Bearer {GEMINI_API_KEY}"}) as resp:
                if resp.status_code != 200:
                    raise GeminiFailed(f"HTTP {resp.status_code}: {(await resp.aread())[:300]!r}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if not chunk.get("choices"):
                        continue
                    delta = chunk["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        result.content += delta["content"]
                        if on_token:
                            await on_token(delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        # Gemini sends each call whole and may leave out the index.
                        idx = tc["index"] if "index" in tc else len(calls)
                        call = calls.setdefault(idx, ToolCall(id="", name=""))
                        call.id = tc.get("id") or call.id or f"call_{idx}"
                        fn = tc.get("function") or {}
                        call.name = fn.get("name") or call.name
                        call.arguments += fn.get("arguments") or ""
    except GeminiFailed as exc:
        exc.streamed = bool(result.content)
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise GeminiFailed(f"{exc.__class__.__name__}: {exc}", streamed=bool(result.content)) from exc
    result.tool_calls = [calls[i] for i in sorted(calls)]
    if not result.content and not result.tool_calls:
        raise GeminiFailed("empty response")
    return result
