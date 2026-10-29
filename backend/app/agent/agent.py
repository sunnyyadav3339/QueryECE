"""Tool-using chat agent with a bounded context window.

Groq's free tier allows ~8K tokens/minute per model, so every call is budgeted:

    system prompt + student profile      ~600 tokens
    rolling summary of older turns       <=300 tokens
    recent turns, verbatim                <=1500 tokens (newest first until full)
    tool results (this turn only)         <=1500 tokens per call, max 3 rounds
    answer                                <=1200 tokens

Tool results are never persisted into history: only the final answers are,
which keeps later turns cheap. When un-summarised history grows past the
budget, older turns are folded into the summary by the fast model.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import date

import groq
from sqlalchemy.orm import Session

from app.agent import llm, tools
from app.config import GROQ_FAST_MODEL
from app.db.database import SessionLocal
from app.db.models import Chat, Faculty, Message, User, utcnow
from app.rag import personal

log = logging.getLogger(__name__)

HISTORY_TOKEN_BUDGET = 1500
PROMPT_TOKEN_CEILING = 6000  # beyond this, force a final answer without more tools
MAX_TOOL_ROUNDS = 3
KEEP_RECENT = 6  # messages always kept verbatim (never summarised away)
SUMMARY_TRIGGER_TOKENS = 1200
CITATION_RE = re.compile(r"【(\d+)[^】]*】")

SYSTEM_PROMPT = """You are QueryECE, the research and information assistant for students of the Department of Electronics & Communication Engineering (ECE), IIT Roorkee. Today is {today}.

Grounding rules (most important):
- State only facts that appear in tool results from this turn or earlier in this conversation. The data is scraped from the official iitr.ac.in ECE website and refreshed weekly.
- Never fill gaps from general knowledge: no invented paper titles, project names, grants, years, emails, phone numbers, deadlines or "typical" examples. If a tool result only gives a link (e.g. "complete list of publications available at <url>"), say that and share the link instead of listing items.
- If the tools don't contain the answer, say so plainly and suggest where to check (the faculty member, the department office, or the linked page).
- Copy dates, times, names and numbers exactly as written in the tool result; never shift or infer them. If a detail isn't shown, say "see the linked document". Point out when a date is already past (compare with today's date).
- Put a citation like [2] after every factual sentence or table row, using the numbers from tool results.

How to use tools:
- find_faculty: a person by name, or faculty matching a research topic.
- list_sponsored_projects: funded projects/grants by PI, keyword, agency or year.
- list_opportunities: open RA / JRF / project-staff / post-doc adverts.
- search_senior_insights: tips from IITR seniors that aren't on any website (what a professor looks for, how they reply, BTP/course/interview experiences). Call it, in addition to the official tools, for advice, "what is it like" or "how do I approach" questions. Present what it returns under a separate heading "**From seniors (unofficial)**", citing each tip, and never state it as an official fact or mix it into official details.
- search_department_info: everything else (programmes, admissions, courses, labs, research groups, contacts, faculty publications/students/patents/awards, news).
- Usually one tool call is enough; make another only if the first result is insufficient. Write self-contained queries (resolve "he", "the second one" from the conversation).

Answer exactly what was asked:
- First decide what kind of question it is. Factual questions (dates, deadlines, fees, courses, syllabus, admissions steps, contacts, labs, events, rules) get a direct, complete answer and nothing else: no professor recommendations, no ★, no research suggestions, no "For you" line.
- Keep the useful specifics from tool results (names, emails, links, project titles, dates); don't summarise them away.

Personalise only when the student asks for advice or discovery ("who should I approach", "suggest", "which lab fits me", "what can I do", "recommend") or asks about faculty/projects/openings in general:
- Put the ones that fit the student's interests first and mark each with ★ plus a few words on why (e.g. "★ fits your Signal Processing interest").
- For open-ended requests, start from the matched professors below, then use tools to back up the details you state. You may also draw on the student's CV excerpt.
- Fit advice to their stage: B.Tech students → BTP, summer internships, small projects; M.Tech → thesis topics; PhD → research groups and funding.
- You may end with one line starting "**For you:**" giving a concrete next step tied to their interests.

Use their first name occasionally, not in every answer.

Style: answer what was asked, concisely and skimmably (short paragraphs, bullets, bold names). Include emails and links when useful.
- People (recommendations, contacts): a bulleted list, one professor per bullet: **Prof. Name** (designation) — ★ why it fits — email. Not a table.
- Tables only for compact records such as projects, openings or schedules (4+ rows), with short cells (a few words each).

Student profile:
{profile}"""


def _profile_text(user: User, db: Session) -> str:
    lines = [f"Name: {user.name}"]
    if user.program or user.year:
        lines.append(f"Programme: {' · '.join(x for x in (user.program, user.year) if x)}")
    if user.interests:
        lines.append(f"Research interests: {', '.join(user.interests)}")
    if user.bio:
        lines.append(f"About: {user.bio[:400]}")
    if user.cv_text:
        lines.append(f"CV excerpt (written by the student):\n{user.cv_text[:1200]}")
    if user.interests:
        matches = personal.profile_matches_text(db.query(Faculty).all(), user.interests)
        if matches:
            lines.append("Professors whose listed research best matches these interests "
                         "(from their faculty profiles):\n" + matches)
    else:
        lines.append("(No research interests set yet; you may suggest adding them on the Profile page.)")
    return "\n".join(lines)


def build_context(db: Session, chat: Chat, user: User) -> list[dict]:
    """System prompt + summary + as many recent messages as fit the budget."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(
        today=date.today().strftime("%d %B %Y"), profile=_profile_text(user, db))}]
    if chat.summary:
        messages.append({"role": "system", "content": f"Summary of the earlier conversation:\n{chat.summary}"})

    recent = (db.query(Message).filter(Message.chat_id == chat.id, Message.id > chat.summarized_upto)
              .order_by(Message.id.desc()).limit(30).all())
    picked, used = [], 0
    for i, msg in enumerate(recent):  # newest first
        content = msg.content if msg.role == "user" else msg.content[:2000]
        cost = llm.estimate_tokens(content)
        if i > 0 and used + cost > HISTORY_TOKEN_BUDGET:
            break
        picked.append({"role": msg.role, "content": content})
        used += cost
    messages.extend(reversed(picked))
    return messages


async def _run_tool(call: llm.ToolCall, reg: tools.SourceRegistry) -> str:
    fn = tools.REGISTRY.get(call.name)
    if fn is None:
        return f"Unknown tool {call.name}."
    try:
        args = json.loads(call.arguments or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        return "Invalid JSON arguments; retry with valid JSON."
    try:
        # Tools hit SQLite/Chroma/ONNX synchronously: keep the event loop free.
        return await asyncio.to_thread(fn, reg, **args)
    except TypeError as exc:
        return f"Bad arguments for {call.name}: {exc}"
    except Exception:
        log.exception("tool %s failed", call.name)
        return f"{call.name} failed due to an internal error."


async def respond(chat_id: str, user_id: int, text: str) -> AsyncIterator[dict]:
    """Run one user turn. Yields UI events: status | token | sources | done | error."""
    with SessionLocal() as db:
        chat = db.get(Chat, chat_id)
        user = db.get(User, user_id)
        user_msg = Message(chat_id=chat.id, role="user", content=text)
        db.add(user_msg)
        if chat.title == "New chat":
            chat.title = (text[:57] + "…") if len(text) > 60 else text
        chat.updated_at = utcnow()
        db.commit()
        user_msg_id = user_msg.id
        messages = build_context(db, chat, user)

    queue: asyncio.Queue = asyncio.Queue()

    async def on_token(delta: str):
        await queue.put({"type": "token", "text": delta})

    reg = tools.SourceRegistry()
    answer = ""

    async def agent_loop():
        nonlocal answer
        try:
            for round_no in range(MAX_TOOL_ROUNDS + 1):
                over_budget = llm.estimate_tokens(messages) > PROMPT_TOKEN_CEILING
                allow_tools = round_no < MAX_TOOL_ROUNDS and not over_budget
                try:
                    result = await llm.stream_round(
                        messages, tools=tools.TOOL_SCHEMAS,
                        tool_choice="auto" if allow_tools else "none", on_token=on_token,
                    )
                except groq.APIError as exc:
                    # gpt-oss occasionally emits malformed tool calls, which Groq
                    # rejects (sometimes mid-stream); degrade to classic RAG:
                    # retrieve on the raw question and answer without tools.
                    log.warning("tool round failed (%s); falling back to plain RAG", exc)
                    await queue.put({"type": "status", "text": tools.STATUS_TEXT["search_department_info"]})
                    context = await asyncio.to_thread(tools.search_department_info, reg, text)
                    fallback = messages + [{"role": "system", "content": f"Search results:\n{context}"}]
                    result = await llm.stream_round(fallback, on_token=on_token)
                answer += result.content
                if not result.tool_calls:
                    break
                messages.append({
                    "role": "assistant", "content": result.content or None,
                    "tool_calls": [{"id": c.id, "type": "function",
                                    "function": {"name": c.name, "arguments": c.arguments or "{}"}}
                                   for c in result.tool_calls],
                })
                for call in result.tool_calls:
                    await queue.put({"type": "status", "text": tools.STATUS_TEXT.get(call.name, "Working")})
                    output = await _run_tool(call, reg)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
        except llm.LLMUnavailable as exc:
            await queue.put({"type": "error", "text": str(exc)})
        except Exception as exc:  # surface, don't hang the stream
            log.exception("agent failed")
            await queue.put({"type": "error", "text": f"Something went wrong: {exc.__class__.__name__}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(agent_loop())
    while (event := await queue.get()) is not None:
        yield event
    await task

    # gpt-oss sometimes cites as 【1】 or 【1†source】; store the plain [1] form.
    answer = CITATION_RE.sub(lambda m: f"[{m.group(1)}]", answer).strip()
    if not answer:
        # Failed turn: drop the unanswered question so it doesn't linger in
        # the history and get answered in place of the next question.
        with SessionLocal() as db:
            db.query(Message).filter_by(id=user_msg_id).delete()
            db.commit()
        return
    # Cited sources first, then the rest of what was retrieved (capped).
    cited = [s for s in reg.sources if f"[{s['n']}]" in answer]
    cited += [s for s in reg.sources if s not in cited][: max(0, 6 - len(cited))]
    with SessionLocal() as db:
        msg = Message(chat_id=chat_id, role="assistant", content=answer, sources=cited)
        db.add(msg)
        chat = db.get(Chat, chat_id)
        chat.updated_at = utcnow()
        db.commit()
        yield {"type": "sources", "sources": cited}
        yield {"type": "done", "message_id": msg.id, "title": chat.title}
        user = db.get(User, user_id)
        profile = _profile_text(user, db) if user else ""

    suggestions = await suggest_followups(text, answer, profile)
    if suggestions:
        yield {"type": "suggestions", "items": suggestions}

    asyncio.create_task(maybe_summarize(chat_id))


FOLLOWUP_PROMPT = (
    "Suggest exactly 3 follow-up questions this student could ask the IIT Roorkee ECE department "
    "assistant next. Stay on the topic of the student's question: natural next questions about the same "
    "thing (e.g. after a deadline question, ask about documents or venue, not research). Bring in the "
    "student's interests only if the question was about faculty, projects or advice. At most 12 words "
    "each, answerable from the department website. "
    "Write them in the student's voice. Output one question per line, nothing else.")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


async def suggest_followups(question: str, answer: str, profile: str) -> list[str]:
    """Three short next questions tailored to the student (fast model, separate quota)."""
    prompt = [
        {"role": "system", "content": FOLLOWUP_PROMPT},
        {"role": "user", "content": f"Student:\n{profile[:900]}\n\nQuestion: {question}\n\nAnswer:\n{answer[:1500]}"},
    ]
    try:
        raw = await llm.complete(prompt, model=GROQ_FAST_MODEL, max_tokens=300)
    except Exception:
        log.warning("follow-up suggestions failed", exc_info=True)
        return []
    items = [LIST_MARKER_RE.sub("", line).strip().strip('"') for line in raw.splitlines()]
    return [q for q in items if 8 <= len(q) <= 120][:3]


async def maybe_summarize(chat_id: str):
    """Fold older messages into chat.summary once they exceed the trigger size."""
    try:
        with SessionLocal() as db:
            chat = db.get(Chat, chat_id)
            pending = (db.query(Message).filter(Message.chat_id == chat_id, Message.id > chat.summarized_upto)
                       .order_by(Message.id).all())
            older = pending[:-KEEP_RECENT]
            if not older or llm.estimate_tokens("".join(m.content for m in older)) < SUMMARY_TRIGGER_TOKENS:
                return
            transcript = "\n".join(f"{m.role.upper()}: {m.content[:1500]}" for m in older)
            prompt = [
                {"role": "system", "content": (
                    "You maintain a running memory of a chat between a student and the IIT Roorkee ECE "
                    "assistant. Merge the previous summary with the new messages into one summary of at "
                    "most 150 words. Keep: the student's goals, constraints, faculty/labs/projects discussed "
                    "(names, emails, key facts), and open questions. Drop pleasantries.")},
                {"role": "user", "content": f"Previous summary:\n{chat.summary or '(none)'}\n\nNew messages:\n{transcript}"},
            ]
            summary = await llm.complete(prompt, model=GROQ_FAST_MODEL, max_tokens=400)
            if summary:
                chat.summary = summary
                chat.summarized_upto = older[-1].id
                db.commit()
    except Exception:
        log.exception("summarisation failed for chat %s", chat_id)
