# Complete Google Drive synchronization

Chrono uses two n8n workflows:

1. `google-drive-initial-import.json` scans every current Drive file and folder once, stores the metadata baseline, and indexes supported content.
2. `google-drive-complete-sync.json` polls the Drive Changes API every minute and applies creation, modification (including renames), move, trash, restore, and permanent-deletion events.

Run the baseline before the live workflow. It lets Chrono compare old and new parent IDs so the first move of an existing item is classified correctly.

## 1. Configure and start

From `backend`, copy `.env.example` to `.env` and set a long shared secret. The default n8n URLs use `host.docker.internal` because n8n runs in Docker while FastAPI runs on the Windows host.

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open the API documentation at <http://localhost:8000/docs>.

## Google login and Chrono access tokens

Google login identifies the person using Chrono. It is separate from the existing
Google Drive OAuth grant stored in n8n, which authorizes the synchronization job
to read one personal Drive.

Create or reuse a **Web application** OAuth client in Google Cloud Console and set:

```dotenv
GOOGLE_AUTH_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
GOOGLE_AUTH_REQUIRE_VERIFIED_EMAIL=true
CHRONO_JWT_SECRET=replace-with-at-least-32-random-secret-characters
CHRONO_JWT_ALGORITHM=HS256
CHRONO_ACCESS_TOKEN_MINUTES=60
ALLOW_LEGACY_DEFAULT_USER=false
CHRONO_N8N_OWNER_USER_ID=your-internal-chrono-user-uuid
FRONTEND_ORIGINS=http://localhost:5173
```

The existing React/Vite frontend runs at `http://localhost:5173`. Add that exact
origin—with no trailing slash—to the OAuth client's authorized JavaScript origins
and to `FRONTEND_ORIGINS`. Add production origins later as a comma-separated
list. A redirect URI is not required for the Google Identity Services credential
callback flow; add one only if the selected frontend flow actually redirects.

The Google client ID is public and may be present in frontend configuration. A
Google client secret, `CHRONO_JWT_SECRET`, n8n secret, Drive credentials, and AI
provider keys must remain server-side. Production login and authenticated API
traffic must use HTTPS. Wildcard CORS origins are rejected.

The frontend sends the Google Identity Services ID token once:

```http
POST /auth/google
Content-Type: application/json

{"credential":"<Google ID token>"}
```

FastAPI verifies its signature, audience, issuer, expiration, stable `sub`, and
verified-email policy with Google's official `google-auth` library. Chrono stores
the stable `sub` as the external identity, never the Google token or a Google
password. It returns a short-lived Chrono bearer token. Subsequent calls use:

```http
Authorization: Bearer <Chrono access token>
```

The client no longer sends `user_id`. For example:

```json
{
  "question": "Show my PDF files",
  "limit": 10
}
```

To test in Swagger, first sign in through the frontend or submit a real Google ID
token to `/auth/google`, copy only the returned Chrono access token, click
**Authorize**, and enter that bearer token. Then call `/ask` without `user_id`.
Never paste a Google password, OAuth client secret, JWT secret, or n8n secret into
Swagger.

### Additive schema and one-time ownership claim

Apply the additive schema once. This creates `users` and adds a nullable ownership
column/index to Drive events; it does not re-import, re-extract, re-chunk, embed,
or claim any record:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_auth_schema
```

Sign in with Google once so the target Chrono user exists. Before any ownership
claim, create and verify a PostgreSQL backup:

```powershell
docker exec chrono-postgres pg_dump -U chrono -d chrono -Fc --file=/tmp/chrono-before-auth.dump
docker cp chrono-postgres:/tmp/chrono-before-auth.dump .\chrono-before-auth.dump
Get-Item .\chrono-before-auth.dump
```

Preview the claim without writes, using the account that just signed in:

```powershell
.\.venv\Scripts\python.exe -m scripts.claim_default_user_data --email your-account@example.com --dry-run
```

Review the before/updated/after counts, then apply explicitly:

```powershell
.\.venv\Scripts\python.exe -m scripts.claim_default_user_data --email your-account@example.com --apply
```

The command matches email only for this administrative operation, resolves the
stable internal user UUID, and updates ownership on legacy memories and Drive
events in one transaction. Chunks inherit ownership through `memory_id`; their
IDs, vectors, provider signatures, content, and relationships are unchanged. The
operation is idempotent, refuses ambiguous targets and conflicting source rows,
rolls back on failure, and never deletes data.

After the claim, copy the user's internal ID from `/auth/me` into the server-only
`CHRONO_N8N_OWNER_USER_ID` setting and restart FastAPI. This is a single-user MVP
mapping: FastAPI validates `X-N8N-Secret`, confirms the configured user exists and
is active, ignores payload `user_id`, and assigns every future n8n event/content
upload to that user. Leave `ALLOW_LEGACY_DEFAULT_USER=false`; enable it only for
a short, explicit local transition. The n8n workflow itself does not need to be
changed or rerun.

## 2. Run the one-time baseline

1. Import `n8n/google-drive-initial-import.json`.
2. Select your existing Drive credential in **List every current Drive item** and **Download or export current file**.
3. Run it manually once and wait for completion.
4. Do not activate this workflow. Re-running it is safe because baseline event IDs are idempotent.

## 3. Activate live synchronization

Import `n8n/google-drive-complete-sync.json` as a new workflow, or replace the earlier version. Select the Drive credential in:

- **Get initial page token**
- **Get Drive changes**
- **Download or export file**

Activate it. The first scheduled execution saves the current cursor; later executions poll each minute. Keep only one copy active.

The credential should include the `https://www.googleapis.com/auth/drive` scope.

## Indexed content

Chrono extracts text from PDF, DOCX, Google Docs, Google Sheets, Google Slides, TXT, Markdown, HTML, XML, YAML, logs, JSON, and CSV. Unsupported binary formats still retain metadata. Image-only PDFs require OCR, which is not included.

Files above `MAX_INGEST_FILE_BYTES` are rejected with HTTP 413.

## Lifecycle behavior

- Create: creates an event and searchable memory.
- Modify or rename: refreshes metadata and content.
- Move: records the old and new parent IDs.
- Trash or delete: removes the searchable memory while preserving event history.
- Restore: recreates metadata and content.
- Retry: `(drive_id, change_id)` prevents duplicate event records.

## Verify

```powershell
$headers = @{ Authorization = 'Bearer your-chrono-access-token' }
Invoke-RestMethod http://localhost:8000/integrations/google-drive/status -Headers $headers
Invoke-RestMethod 'http://localhost:8000/integrations/google-drive/events?limit=20' -Headers $headers
Invoke-RestMethod 'http://localhost:8000/search?q=search-term' -Headers $headers
Invoke-RestMethod 'http://localhost:8000/timeline' -Headers $headers
```

Each event includes `event_type`, file/folder metadata, current and previous parent IDs, timestamps, links, owners, and the raw Drive change JSON.

## Timeline, chunks, semantic search, and RAG

Gemini is the primary optional AI provider. Add a Gemini API key and explicitly
choose the chat model available to your account:

```dotenv
GEMINI_API_KEY=your-key
GEMINI_CHAT_MODEL=your-supported-gemini-chat-model
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=1536
GEMINI_EMBEDDING_INPUT_TOKEN_LIMIT=2048
GEMINI_EMBEDDING_BATCH_TOKEN_LIMIT=18000
GEMINI_EMBEDDING_BATCH_SIZE=20
GEMINI_TIMEOUT_SECONDS=15
GEMINI_MAX_ATTEMPTS=2
GEMINI_GENERATION_BUDGET_SECONDS=35
GEMINI_RETRY_INITIAL_DELAY_SECONDS=0.5
GEMINI_RETRY_MAX_DELAY_SECONDS=4.0
```

Chrono requests exactly 1536 dimensions for both document and query embeddings,
matching the existing PostgreSQL `Vector(1536)` column and HNSW index. Gemini's
truncated embeddings are L2-normalized before storage and search.

OpenAI remains an optional fallback when Gemini is missing or temporarily
unavailable:

```dotenv
OPENAI_API_KEY=your-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-5.4-mini
```

Restart FastAPI. Existing vectors must not be regenerated merely because login was
added. Reindex only when content or the configured embedding signature actually
requires it:

```powershell
.\.venv\Scripts\python.exe -m scripts.reindex_memories
```

The backfill is safe to repeat. It preserves matching embeddings and commits
new vectors after each bounded batch.
Every chunk records its embedding provider, model, and dimensions. Semantic
queries only compare a query vector with chunks bearing the exact same signature;
vectors from different models are never silently mixed.

After changing `GEMINI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_DIMENSIONS`, or the
selected provider, run the backfill before relying on semantic retrieval. The
status endpoint reports `embedding_regeneration_required: true` while stored
vectors do not match the active signature. Lexical search remains available
during regeneration and provider outages.

The reindex command is resumable and defaults to `--missing-only`. It retains
matching vectors, processes missing or stale chunks in bounded batches, and
commits every successful batch:

```powershell
.\.venv\Scripts\python.exe -m scripts.reindex_memories --missing-only
```

Use `--all` only when every matching vector must be regenerated. Final output
contains `total`, `already_embedded`, `newly_embedded`, `skipped`, `remaining`,
and `errors`. A rejected 400 response is isolated to individual chunks and
recorded for that exact provider/model, so later missing-only runs skip the
permanent rejection while continuing all other chunks. Error output contains
only the category, memory title, chunk index, character count, estimated token
count, and request batch size; it never prints content, credentials, raw Drive
metadata, or source identifiers.

Before submission, text is normalized to valid UTF-8, empty chunks are skipped,
and oversized chunks are split below Gemini's 2,048-token per-input limit. Each
request is also held below the configured 18,000-token aggregate safety ceiling.

Authenticated user APIs:

- `GET /auth/me` — sanitized current-user profile.
- `GET /timeline` — current synchronized Drive items.
- `GET /timeline/history` — immutable create/modify/move/trash/restore/delete history.
- `GET /search?q=...` — hybrid metadata, PostgreSQL full-text, and pgvector semantic search.
- `POST /ask` — retrieves relevant chunks and answers using only that context with numbered citations.
- `POST /integrations/google-drive/reindex` — authenticated remote reindex operation.
- `GET /integrations/google-drive/status` — includes memory, chunk, and embedding counts.

Example RAG request:

```json
POST /ask
{
  "question": "What changed in my Drive project files?",
  "limit": 8,
  "source": "google_drive"
}
```

Search and RAG filters include `source`, `event_type`, `mime_type`, `start`, and `end`. Timeline history additionally supports `file_id`, `limit`, and `offset`.

Vector top-K is candidate generation only. `RAG_MIN_SEMANTIC_CANDIDATE=0.45`, `RAG_MIN_SEMANTIC_ONLY=0.75`, `RAG_MIN_FINAL_RELEVANCE=0.45`, and `RAG_MIN_FILE_TERM_COVERAGE=0.60` provide absolute relevance gates before a passage can enter RAG context or a public result. Lexical evidence receives 70% of a hybrid passage score and semantic similarity 30%; semantic-only passages use 60% of cosine similarity and therefore need a genuinely strong vector match. A file is ranked by its best passage plus one bounded supporting-passage bonus, and at most `RAG_MAX_CHUNKS_PER_FILE=2` passages are retained. Provider order is Gemini, then OpenAI, then PostgreSQL lexical search and conservative extractive answers. If no generation provider is available, `/ask` returns an insufficient-evidence response when meaningful question terms are absent from the retrieved passages. Authenticated search and citation payloads expose short redacted excerpts and descriptive fields only. A source may include a server-validated `open_url` for the exact HTTPS hosts `drive.google.com` or `docs.google.com`; internal IDs, raw metadata, full chunks, API keys, and model context are omitted from responses and logs.

## Schema-aware natural `/ask` searches

`/ask` deterministically interprets common file, folder, MIME type, event, person-role,
count, and date phrases before considering Gemini planning. Relative dates use
`APP_TIMEZONE` (default `Asia/Karachi`) and are converted to inclusive UTC
boundaries. Gemini planning, when needed, may only propose the validated
`SearchPlan` schema; it cannot provide SQL or arbitrary database fields.

Supported from the currently synchronized data:

- Citation-grounded document questions and semantic content search.
- Current file and folder discovery, including metadata-only records.
- Drive creation and modification date filtering.
- PDF/file/folder counts that count distinct files, never chunks.
- Current-memory timeline and immutable Drive event history.
- Owner display-name and owner-email matching. Email values are never echoed.

The response keeps `answer`, `retrieval_mode`, and `sources`, and adds `intent`,
`interpreted_filters`, and sanitized `items`. Structured lists and counts do not
use answer generation. No IDs, source IDs, raw JSON, email addresses, Drive URLs,
or full chunks are returned.

The current n8n payload already includes `owners`, `createdTime`, and
`modifiedTime`. These role-specific fields are not currently synchronized:

- `sharingUser` and `sharedWithMeTime` for “shared/sent by …” and received-date searches.
- `lastModifyingUser` for “modified by …” searches.
- Drive Activity API actor data for “what actions did … perform?” searches.

An owner is never treated as a sender, sharer, modifier, or activity actor.
Adding these fields later affects future events only unless existing Drive files
and event history are explicitly backfilled.

## Single-user Drive limitation and future multi-user work

Google login does not grant Drive access. The present n8n credential remains one
personal Drive grant bound to one Chrono owner. Full multi-user Drive support
requires one Drive OAuth grant per user, encrypted refresh-token storage, an
owned connection table/non-secret connection key, per-user Drive change cursors,
revocation handling, and per-user sync jobs or a shared worker system. Until that
is built, do not map the one n8n credential to multiple users.
