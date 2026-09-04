# Chrono

Chrono is an authenticated personal knowledge timeline that synchronizes Google
Drive through n8n, stores current files and immutable change history in
PostgreSQL, and provides structured search, hybrid retrieval, and
citation-grounded answers through FastAPI and React.

The application works without an AI API key: PostgreSQL full-text search,
metadata filters, extractive answers, citations, dashboards, and timelines remain
available. Gemini is the primary optional provider for embeddings and answer
generation, with OpenAI as an optional fallback.

## Why Chrono

People accumulate useful knowledge across files but struggle to rediscover what
they saved, when it changed, and why it matters. Chrono turns Google Drive into
an authenticated memory timeline that supports natural questions, structured
file discovery, change history, and citation-grounded answers.

## Who Chrono is for

Chrono is designed for people whose working knowledge lives in Drive—students,
researchers, builders, and independent professionals—who need to find both
current documents and the history behind them without exposing one user’s
memories to another.

## Solution, impact, and innovation

### Solution

Chrono combines a resumable Google Drive change feed, immutable event history,
content extraction, structured natural-language planning, and grounded retrieval
behind one authenticated interface.

### Impact

Users can spend less time reconstructing filenames, dates, and folder locations;
they can search by meaning or metadata, open the original Drive file, and inspect
the evidence used for an answer.

### Innovation

Chrono treats memory as both content and time. It combines deterministic schema-
aware queries with lexical and semantic retrieval, preserves source citations,
and continues to provide useful search when no external AI provider is
configured.

## Architecture

```text
Google Drive
    │ Drive Changes API + file downloads
    ▼
   n8n ── signed event/content requests ──▶ FastAPI
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     ▼                       ▼                       ▼
              PostgreSQL + pgvector   Retrieval/RAG services   Google auth + JWT
                     │                       │                       │
                     └───────────────────────┴───────────────────────┘
                                             │ authenticated JSON API
                                             ▼
                                      React + Vite frontend
```

### Main capabilities

- Google Identity Services login with server-side ID-token verification.
- Short-lived Chrono JWT sessions and owner-scoped API access.
- Drive lifecycle handling for creation, modification—including renames—moves,
  trash, restore, and permanent deletion.
- One-time Drive baseline import plus resumable Changes API synchronization.
- Text extraction and chunking for PDF, DOCX, JSON, CSV, and text-based files;
  downloadable Google Workspace files are exported by the n8n Drive node first.
- PostgreSQL full-text search and pgvector semantic retrieval.
- Hybrid metadata + lexical + semantic ranking.
- Citation-grounded `/ask` responses with a conservative no-evidence fallback.
- Dynamic activity dashboard, current timeline, and immutable event history.
- Sanitized authenticated API responses, privacy-safe excerpts, and validated
  Drive links.

## Demo flow

```text
Sign in with Google
→ view real Drive activity
→ find files using natural dates and metadata
→ open the original Drive file
→ ask a semantic content question
→ receive a citation-grounded answer
→ inspect immutable change history
```

## Repository layout

```text
Chrono/
├── backend/
│   ├── app/                    FastAPI application and domain services
│   ├── n8n/                    Importable baseline and live-sync workflows
│   ├── scripts/                Schema, ownership, and reindex commands
│   ├── tests/                  Backend unit and integration tests
│   ├── docker-compose.yml      PostgreSQL/pgvector and n8n services
│   └── GOOGLE_DRIVE_SYNC.md    Detailed synchronization runbook
├── frontend/
│   ├── src/                    React application
│   ├── public/                 Static browser assets
│   └── README.md               Frontend authentication and UI notes
└── README.md                   Project-wide guide
```

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, Vite, Tailwind CSS, React Router, Vitest |
| API | FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL 16 with pgvector and HNSW indexing |
| Synchronization | n8n and Google Drive API |
| Authentication | Google Identity Services, `google-auth`, Chrono JWT |
| AI providers | Google Gemini, optional OpenAI fallback |

## Prerequisites

- Python 3.10 or newer; the current environment is verified on Python 3.12
- Node.js `^20.19.0` or `>=22.12.0`, as required by the locked Vite 8 release
- Docker Desktop or Docker Engine with Compose
- A Google Cloud project with the Drive API enabled
- A Google OAuth Web client for browser login
- An n8n Google Drive OAuth credential
- Optional: Gemini or OpenAI API credentials

## Quick start

### 1. Configure the backend

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Linux or macOS, activate the environment with:

```bash
source .venv/bin/activate
```

Set one local PostgreSQL password consistently in both `POSTGRES_PASSWORD` and
`DATABASE_URL`, then configure the authentication and webhook values:

```dotenv
POSTGRES_USER=chrono
POSTGRES_PASSWORD=replace-with-a-strong-local-password
POSTGRES_DB=chrono
DATABASE_URL=postgresql+psycopg://chrono:replace-with-a-strong-local-password@localhost:5432/chrono
APP_TIMEZONE=Asia/Karachi
N8N_WEBHOOK_SECRET=replace-with-a-long-random-value
GOOGLE_AUTH_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
CHRONO_JWT_SECRET=replace-with-at-least-32-random-characters
CHRONO_N8N_OWNER_USER_ID=your-internal-chrono-user-uuid
FRONTEND_ORIGINS=http://localhost:5173
```

Never commit `.env`. Do not put the Google client secret, Drive refresh token,
JWT secret, n8n secret, database password, or AI provider key in frontend files.
The Compose file retains its previous password only as a backward-compatible
local fallback for existing developer databases. New setups should copy
`.env.example` and set `POSTGRES_PASSWORD`; production must always override it.

### 2. Start PostgreSQL and n8n

The Compose file expects the n8n URLs and shared secret from `backend/.env`:

```powershell
docker compose up -d postgres n8n
docker compose ps
```

PostgreSQL is available at `localhost:5432`; n8n is available at
<http://localhost:5678>.

### 3. Start FastAPI

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- API root: <http://localhost:8000>
- OpenAPI/Swagger: <http://localhost:8000/docs>
- API status response: `GET /` (there is no separate `/health` route)

At startup, Chrono enables the pgvector extension and creates compatible tables
for a new database. For an existing pre-authentication database, follow the
additive migration and ownership instructions in
[`backend/GOOGLE_DRIVE_SYNC.md`](backend/GOOGLE_DRIVE_SYNC.md).

### 4. Configure and start the frontend

```powershell
cd ..\frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Set these public browser values in `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
```

Open <http://localhost:5173>. Add that exact origin, without a trailing slash,
to the OAuth client’s authorized JavaScript origins. The same client ID must be
configured in the backend so FastAPI can verify the ID-token audience.

When the Google OAuth consent screen is in **Testing** mode, add every Gmail
account that will test Chrono under **OAuth consent screen → Test users**. Chrono
login should request only basic identity scopes such as `openid`, `email`, and
`profile`. Google Drive authorization is separate and is currently handled by
the n8n Google Drive OAuth credential.

## Google authentication and ownership

Browser login and Drive synchronization use separate Google grants:

1. Google Identity Services gives the browser a one-time ID credential.
2. The browser sends it to `POST /auth/google`.
3. FastAPI verifies signature, issuer, audience, expiration, subject, and email
   verification status.
4. FastAPI returns a short-lived Chrono bearer token.
5. The frontend verifies the session through `GET /auth/me` and sends the Chrono
   token on protected requests.

The frontend never sends `user_id`; ownership always comes from the authenticated
session. The current n8n setup synchronizes one personal Drive and maps it to the
server-side `CHRONO_N8N_OWNER_USER_ID` value. Existing data must only be claimed
after a database backup and a successful `--dry-run` review. See the detailed
runbook before applying that operation.

`CHRONO_N8N_OWNER_USER_ID` is Chrono’s internal authenticated-user UUID. It is
available after that user signs in with Google once, must identify an active row
in the `users` table, and assigns future single-user n8n Drive events to that
user. It is server-only and must never appear in frontend configuration. Full
multi-user Drive synchronization requires owned connection records and per-user
credentials/cursors rather than one environment value.

## Google Drive synchronization

Chrono ships two workflows in `backend/n8n`:

1. `google-drive-initial-import.json` — run manually once to establish the
   current metadata/content baseline.
2. `google-drive-complete-sync.json` — activate once to poll Drive changes and
   process lifecycle events continuously.

Configure the existing Google Drive credential in each Google node and keep only
one live-sync workflow active. n8n sends authenticated requests using
`X-N8N-Secret`; FastAPI ignores any client-provided owner identity.

For import instructions, credential placement, verification commands, lifecycle
semantics, and ownership migration, read
[`backend/GOOGLE_DRIVE_SYNC.md`](backend/GOOGLE_DRIVE_SYNC.md).

## Retrieval and RAG

Retrieval remains useful without external AI credentials:

- PostgreSQL full-text/keyword search
- MIME type, source, event, owner, and date filters
- Structured file/folder discovery and aggregate counts
- Conservative extractive answers
- Numbered source citations

Optional Gemini configuration:

```dotenv
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=your-supported-gemini-chat-model
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=1536
```

No Gemini chat model is hardcoded or verified by the implementation. Set
`GEMINI_CHAT_MODEL` to a generate-content model available to your Google AI
project. Leaving either the key or chat model unconfigured disables Gemini
answer generation without disabling lexical search.

Optional OpenAI fallback configuration:

```dotenv
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-5.4-mini
```

Provider order is Gemini, OpenAI, then lexical/extractive fallback. Document and
query vectors always use the same provider, model, and 1536 dimensions. Chrono
stores the embedding signature and never silently compares vectors produced by
different models.

After intentionally changing the embedding provider, model, or dimensions, run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.reindex_memories --missing-only
```

The command is resumable, commits successful batches, skips matching vectors,
isolates permanent input failures, and does not print chunk content or secrets.
Do not use `--all` unless a complete regeneration is intentional.

## API overview

Except for the API root, Google login, and protected n8n ingestion endpoints,
user-facing endpoints require `Authorization: Bearer <Chrono token>`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/auth/google` | Exchange a Google ID token for a Chrono session |
| `GET` | `/auth/me` | Return the sanitized authenticated user |
| `GET` | `/dashboard/summary` | Activity for `this_week`, `last_7_days`, or `last_30_days` |
| `POST` | `/memories` | Create an authenticated owner-scoped memory |
| `GET` | `/memories` | Current owner-scoped synchronized items |
| `GET` | `/timeline` | Current-memory timeline |
| `GET` | `/timeline/history` | Immutable Drive event history |
| `GET` | `/search` | Hybrid lexical, semantic, and metadata search |
| `POST` | `/ask` | Structured search or citation-grounded RAG answer |
| `GET` | `/integrations/google-drive/status` | Sync and indexing health |
| `GET` | `/integrations/google-drive/events` | Sanitized recent Drive events |
| `POST` | `/integrations/google-drive/events` | Secret-authenticated n8n event ingestion |
| `POST` | `/integrations/google-drive/content` | Secret-authenticated n8n file ingestion |
| `POST` | `/integrations/google-drive/reindex` | Authenticated resumable reindex operation |

Example authenticated question:

```http
POST /ask
Authorization: Bearer <chrono-token>
Content-Type: application/json

{
  "question": "What changed in my Drive project files?",
  "limit": 8,
  "source": "google_drive"
}
```

## Response safety

- Search, timeline, dashboard, and citation responses omit internal IDs and raw
  Drive metadata.
- API excerpts and generated answers redact common phone numbers, email
  addresses, and obvious credentials without modifying stored chunks.
- `open_url` is returned only for credential-free HTTPS URLs whose exact host is
  `drive.google.com` or `docs.google.com`.
- AI Markdown is rendered without arbitrary raw HTML and is sanitized before
  display.
- Unsupported questions return an insufficient-evidence response rather than a
  fabricated answer.

## Tests and quality checks

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

The Gemini live smoke test is automatically skipped when `GEMINI_API_KEY` is not
configured. It uses a fixed non-private fixture and does not index user content.

Frontend:

```powershell
cd frontend
npm test
npm run lint
npm run build
```

Frontend tests mock Google Identity Services and backend responses. They do not
sign into a real Google account or call an AI provider.

## Production checklist

- Use HTTPS for the frontend and API.
- Generate strong, distinct JWT and n8n secrets.
- Use a non-default PostgreSQL password and restrict database exposure.
- Set explicit production `FRONTEND_ORIGINS`; wildcard CORS is rejected.
- Add the production frontend origin to the Google OAuth Web client.
- Keep all provider keys and OAuth secrets server-side.
- Back up PostgreSQL and verify restoration before ownership changes.
- Persist PostgreSQL and n8n volumes securely.
- Run only one baseline import and one active live-sync workflow per Drive.
- Run backend tests, frontend tests, lint, and the production build before
  deployment.
- Prefer Secure, HttpOnly, SameSite session cookies and a strict Content Security
  Policy for a hardened production release.

## Before making the repository public

Run a filename and history audit without displaying secret contents:

```powershell
git status
git ls-files | Select-String -Pattern '\.env|\.dump'
git log --all --oneline -- .env .env.local
git log --all --oneline -- 'backend/.env' 'frontend/.env.local'
```

The repository ignore rules must continue to include:

```gitignore
.env
.env.*
!.env.example
*.dump
```

Chrono intentionally uses a targeted `*_before_*.sql` rule for SQL backup files
instead of ignoring every `*.sql` file; future schema or migration SQL may be
source code that should be reviewed and committed.

- `.env.example` files must contain placeholders only.
- Database dumps must not be committed.
- API keys, OAuth secrets, JWT secrets, n8n secrets, and passwords must not be
  committed.
- If a real secret was ever committed, rotate or revoke it immediately. Deleting
  the current file does not remove it from Git history.
- Review history before making the repository public; do not rewrite history or
  rotate credentials automatically without an explicit recovery plan.

## Troubleshooting

- **Login button missing:** confirm `VITE_GOOGLE_CLIENT_ID`, the authorized
  JavaScript origin, network access to Google Identity Services, and browser
  content blockers.
- **Login succeeds but APIs return 401:** verify backend and frontend client IDs
  match, the JWT secret is stable across restarts, and the token is unexpired.
- **n8n receives 401/403:** verify `N8N_WEBHOOK_SECRET` matches on both sides and
  `CHRONO_N8N_OWNER_USER_ID` identifies an active Chrono user.
- **No semantic results:** check provider status and embedding-signature counts;
  lexical search should still work during provider outages.
- **Drive moves are misclassified:** ensure the initial baseline was completed
  before activating the live workflow.
- **Image-only PDFs contain no text:** OCR is not included in the current
  extraction pipeline.

## Project status

Chrono currently targets a secure single-user Drive synchronization MVP. Google
login supports multiple Chrono identities, but each Drive connection still needs
an explicitly owned n8n credential and synchronization cursor. A future
multi-user Drive architecture should add encrypted per-user refresh-token
storage, connection records, per-user cursors, revocation handling, and isolated
workers.

Chrono is distributed under the MIT License. See [`LICENSE`](LICENSE).
