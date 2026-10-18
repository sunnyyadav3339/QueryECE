# QueryECE

A research assistant for students of the ECE Department, IIT Roorkee. It answers
questions using the department website, which it scrapes on a schedule, and
personalises everything to the student's research interests.

**Features**

- **Home dashboard:** professors matched to your interests (with the reason for each match), personalised starter questions, your outreach pipeline and openings.
- **Ask QueryECE:** chat with cited sources, separate chat histories, a "For you" next step and suggested follow-up questions.
- **Professors:** all faculty with photos, ranked by match, plus details and sponsored projects for each.
- **Outreach:** AI-drafted emails to professors built only from verified data, plus a status tracker with follow-up reminders.
- **Accounts:** email + password with a 6-digit email verification code at sign-up.

## Architecture

```
iitr.ac.in (ECE pages, PDFs, career pages)
        │  weekly crawl (APScheduler) — httpx + BeautifulSoup, no browser needed
        ▼
  pages table (cleaned text + hash) ── unchanged pages are skipped
        │
        ├─► chunker (heading-aware, ~300 tokens, "Title > Section" headers)
        │       ├─► Chroma (bge-small-en-v1.5 embeddings, local/free)
        │       └─► SQLite FTS5 (BM25 keywords)
        │
        └─► structured tables: faculty, projects, startups, opportunities
                                   │
  Groq gpt-oss-120b agent ◄────────┘  tools: search_department_info (hybrid RRF),
        │                                    find_faculty, list_sponsored_projects,
        │                                    list_opportunities
        ▼
  FastAPI (SSE streaming) ──► Next.js UI (home, chat, professors, outreach, profile)
```

**Personalisation.** Each professor's research interests are embedded with the
same local model and compared with the student's interests (`rag/personal.py`).
The best matches cover every interest, each with the specific topic that caused
it (e.g. *VLSI Design ↔ VLSI device physics*). These go into the agent's system
prompt, which tells it to put matching people first, mark them with ★, fit
advice to the student's programme, and end with a "For you" step. A fast model
then suggests three follow-up questions.

**Context window.** Groq's free tier allows about 8K tokens per minute, so each call is budgeted:

| Part | Budget |
|---|---|
| System prompt + profile | ~600 tokens |
| Rolling chat summary | ≤300 tokens |
| Recent turns (verbatim) | ≤1500 tokens |
| Each tool result | ≤1500 tokens, max 3 rounds |

- Only final answers are stored in history, never tool output.
- Older turns are folded into the summary by `gpt-oss-20b`.
- On a 429 the agent switches to `gpt-oss-20b`, which has its own separate quota.

## Layout

```
backend/app/
  config.py            settings from backend/.env
  auth.py              bcrypt + JWT
  mailer.py            SMTP for verification codes (falls back to the server log)
  db/                  SQLAlchemy models (users, chats, messages, pages, chunks, faculty, ...)
  ingest/              crawler, html→text, structured extractors, pipeline
  rag/                 chunker, embeddings, hybrid index, personal (interest matching)
  agent/               Groq client, tools, agent loop + context management
  routers/             auth (+ OTP), chats, data, discover (home, ranked faculty), outreach
frontend/app/          /login, / (home), /chat, /professors, /outreach, /profile
data/                  queryece.db, chroma/, models/  (generated, gitignored)
```

## Running locally

```bash
cp backend/.env.example backend/.env      # then set GROQ_API_KEY
cd backend && python -m venv venv && venv/Scripts/pip install -r requirements.txt
venv/Scripts/python -m app.ingest.pipeline          # first crawl + index (~4 min)
venv/Scripts/python -m uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev        # http://localhost:3000
```

**Email verification.** To send codes by email, set `SMTP_*` in `backend/.env`.
With Gmail, turn on 2-Step Verification, create an App Password and use it as
`SMTP_PASSWORD`. Without SMTP settings, codes are printed in the backend log,
which is enough for a local demo.

**Faculty photos.** Photos are hosted on channeli.in, which is reachable only from
the IIT Roorkee network. Each crawl saves small copies in `data/photos/`, and the
backend serves them, so they show up anywhere afterwards. Off campus the crawl
keeps the saved copies. To refresh just the photos (on campus Wi-Fi or VPN), run
`python -m app.ingest.photos` from `backend/`, with the Docker backend stopped, since
SQLite can't be shared between Windows and a container.

With Docker, run `docker compose up --build`. If the database is empty, the backend crawls on first start.

To trigger a re-crawl from the API, add your email to `ADMIN_EMAILS` and call `POST /api/admin/crawl`.

## Known gaps

- Timetable PDFs are scanned images, so their text isn't extracted (that would need OCR).
- The Former Faculty page has photos only, with no names in its HTML.
- The M.Tech VLSI site (vlsimtech.iitr.ac.in) is outside the crawl.
