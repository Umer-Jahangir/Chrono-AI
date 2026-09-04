# Chrono authenticated frontend

This is the existing React 19 + Vite frontend for Chrono. It uses Google Identity
Services only to obtain a one-time Google ID credential, exchanges that credential
with FastAPI, and uses the returned short-lived Chrono token for protected APIs.

## Configuration

Copy `.env.example` to `.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
```

Both values are public browser configuration. Never put a Google client secret,
`CHRONO_JWT_SECRET`, Gemini key, n8n secret, database URL, Drive credential, or
`CHRONO_N8N_OWNER_USER_ID` in a `VITE_` variable or frontend file.

Use these exact local values together:

```text
Browser frontend URL:             http://localhost:5173
Google authorized JS origin:      http://localhost:5173
FastAPI FRONTEND_ORIGINS:          http://localhost:5173
Frontend VITE_API_BASE_URL:        http://localhost:8000
```

Origins must not have a trailing slash. Create/reuse a Google OAuth Web client;
the Google Identity Services callback flow used here does not require a redirect
URI. Production must use HTTPS.

## Start and verify

From `frontend`:

```powershell
npm ci
npm run dev
```

Vite serves the application at <http://localhost:5173>. Do not open `index.html`
with `file://`.

Quality checks:

```powershell
npm test
npm run lint
npm run build
```

Tests mock Google Identity Services and FastAPI; normal tests do not perform a
live Google login or call Gemini.

## Session behavior

- Signed-out users see only the Google login screen.
- The Google credential is posted to `POST /auth/google` and is never stored.
- Only `access_token` from the Chrono response is stored under
  `chrono_access_token` in `localStorage`.
- `GET /auth/me` must succeed before the application becomes visible.
- Protected requests receive `Authorization: Bearer <Chrono token>` centrally.
- A `401` removes the token and returns to login; network/server errors preserve a
  potentially valid token and offer retry.
- Logout removes the token and calls Google Identity Services' auto-select reset.

`localStorage` is acceptable for the hackathon MVP but is accessible to any
JavaScript running on the origin. A production version should prefer short-lived
sessions in Secure, HttpOnly, SameSite cookies, deploy a strong Content Security
Policy, and minimize third-party scripts.

## Actual backend contracts

Login request:

```json
{"credential":"<Google ID token>"}
```

Login response:

```json
{
  "access_token": "<Chrono access token>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "<Chrono UUID>",
    "email": "user@example.com",
    "display_name": "Example User",
    "picture_url": null
  }
}
```

`GET /auth/me` returns only the `user` object above. Search submits:

```json
{"question":"Show my PDF files","limit":10}
```

No protected browser request contains `user_id`. `/ask` renders content answers,
citations, content/file searches, current timelines, event history, counts, empty
results, and unsupported explanations. Answers use `react-markdown`, GFM, and a
strict `rehype-sanitize` allowlist; arbitrary HTML and executable URLs are not
enabled. Titles, excerpts, and filenames remain untrusted React text. Raw Drive
metadata and internal record identifiers are not rendered.

Sanitized file, source, timeline, and recent-activity objects may contain
`open_url`. FastAPI returns it only for credential-free HTTPS URLs whose hostname
is exactly `drive.google.com` or `docs.google.com`; the browser never constructs a
Drive URL. API excerpts and generated answers redact common phone numbers,
email addresses, and obvious credentials without changing stored content.

The dashboard loads `GET /integrations/google-drive/status` and
`GET /dashboard/summary?range=this_week|last_7_days|last_30_days`. Its chart is a
bounded aggregation of the authenticated user's immutable Drive events using the
backend application timezone. “Recent Memories” intentionally means the six most
recent immutable Drive activity events, optionally enriched from the matching
current-memory record. It does not mix in invented integrations or sample data.

## Manual end-to-end verification

1. From `backend`, start PostgreSQL and n8n with `docker compose up -d`.
2. Start FastAPI with `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.
3. Confirm backend `.env` has the Web client ID, a strong Chrono JWT secret, and
   `FRONTEND_ORIGINS=http://localhost:5173`.
4. From `frontend`, start `npm run dev` and open <http://localhost:5173>.
5. Confirm protected navigation/data is hidden and the Google button appears.
6. Sign in with an OAuth test user. In browser Network tools, confirm
   `POST /auth/google` succeeds, then `GET /auth/me` succeeds.
7. Confirm the existing Chrono interface and sanitized signed-in user appear.
8. Confirm PostgreSQL contains the new user without printing its Google subject:
   `docker exec chrono-postgres psql -U chrono -d chrono -c "SELECT id, email, is_active FROM users;"`
9. Search for “What technical skills and experience does Umer Jahangir have?”
10. Search for “Show files created on August 29, 2026.”
11. Search for “How many PDF files do I have?”
12. Open Timeline and switch between Current and History.
13. Confirm dashboard status/counts, activity bars, and Recent Memories match the
    authenticated PostgreSQL records; change all three range options.
14. Confirm a result with a validated Drive URL opens from both its title and
    “Open in Google Drive” control in a new tab.
15. Confirm Markdown headings/lists render and duplicate passages appear under
    one source-document card, with contact details redacted from excerpts.
16. Confirm every protected browser request has a Chrono bearer token and none
    contains `user_id` or `user_id=default`.
17. Logout and confirm protected data disappears.
18. Sign in, reload, and confirm `/auth/me` restores the session.
19. Replace the stored token with an invalid value and reload; confirm it is
    removed and the login screen returns.

The frontend never runs the administrative ownership claim. After first login,
back up PostgreSQL and run the backend claim command separately with `--dry-run`;
use `--apply` only after explicit review and authorization. Then configure
`CHRONO_N8N_OWNER_USER_ID`, restart FastAPI, and reactivate n8n.
