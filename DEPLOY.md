# Deployment Guide – StudyRescue on Render

## Overview
StudyRescue is a FastAPI application with Jinja2 server-rendered templates, SQLite/PostgreSQL storage, and session-based authentication. This guide covers deployment to Render.

---

## 1. Prepare the Repository

Ensure these files are present and committed:

| File | Purpose |
|------|---------|
| `render.yaml` | Render infrastructure definition (web service + database) |
| `Procfile` | Process entry point (`uvicorn ... --port $PORT`) |
| `start.sh` | Local development start script |
| `requirements.txt` | Python dependencies |
| `.env.example` | Reference environment variables |

---

## 2. Environment Variables

Set these in the **Render Dashboard → Your Service → Environment**:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ENV` | Yes | Set to `production` | `production` |
| `DEBUG` | Yes | Set to `false` | `false` |
| `SECRET_KEY` | Yes | Random 32+ char signing key | `openssl rand -hex 32` |
| `DATABASE_URL` | Yes | Database connection string | `postgresql+psycopg://...` |
| `SESSION_COOKIE_SECURE` | Yes | `true` on HTTPS (Render) | `true` |
| `SESSION_COOKIE_SAMESITE` | Yes | `lax` for same-site, `none` for cross-origin | `lax` |
| `SESSION_COOKIE_DOMAIN` | No | Cookie domain (e.g. `.onrender.com`) | `.onrender.com` |
| `CORS_ENABLED` | No | Enable CORS if frontend is separate | `true` |
| `CORS_ALLOW_ORIGINS` | No | Comma-separated allowed origins | `https://studyrescue-vzhj.onrender.com` |
| `CORS_ALLOW_CREDENTIALS` | No | Allow cookies in CORS requests | `true` |
| `FRONTEND_URL` | No | Your app URL (used for CORS) | `https://studyrescue-vzhj.onrender.com` |
| `LLM_PROVIDER` | No | LLM provider | `gemini` |
| `LLM_MODEL` | No | Model name | `gemini-3.1-flash-lite` |
| `LLM_API_KEY` | Yes | LLM API key | `AIza...` |
| `GEMINI_API_KEY` | Yes | Gemini API key | `AIza...` |
| `PORT` | No | Render sets this automatically | `8000` |

### Generating a SECRET_KEY
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. Deploy on Render

### Option A: Using render.yaml (recommended)
1. Connect your GitHub repo to Render.
2. Create a new **Web Service** and select the repo.
3. Render auto-detects `render.yaml` and configures the service + database.
4. Add the remaining env vars (API keys, etc.) manually in the dashboard.
5. Click **Create Web Service**.

### Option B: Manual setup
1. Create a **Web Service** on Render from your repo.
2. Create a **PostgreSQL Database** on Render.
3. Copy the database connection string to `DATABASE_URL`.
4. Set all environment variables from the table above.
5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

---

## 4. Authentication & Cookie Configuration for Production

Render serves over HTTPS. The app configures session cookies automatically:

- `secure: true` — cookies only sent over HTTPS
- `samesite: lax` — CSRF protection while allowing normal navigation
- `httponly: true` — JavaScript cannot read the cookie
- `domain: null` — defaults to the Render host

If you use a custom domain, set `SESSION_COOKIE_DOMAIN` to your domain (e.g. `.studyrescue.com`) so cookies work across subdomains.

If your frontend is on a different origin than the API, enable CORS:
```
CORS_ENABLED=true
CORS_ALLOW_ORIGINS=https://your-frontend.onrender.com
CORS_ALLOW_CREDENTIALS=true
```

---

## 5. Database

The app uses SQLAlchemy with SQLite by default. For production on Render:

- **Use PostgreSQL** (Render managed database recommended).
- Set `DATABASE_URL` to the PostgreSQL connection string.
- Tables are created automatically on startup via `create_tables()` in the lifespan context.
- No migrations are needed; schema is defined in `app/models.py`.

---

## 6. LLM / AI Extraction

The extraction pipeline uses Gemini by default. Set:
```
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=<your-gemini-key>
GEMINI_API_KEY=<your-gemini-key>
```

If the LLM is unavailable, extraction fails gracefully:
- Batch status is set to `failed` with an `error_message`.
- Users see a toast notification: "AI extraction is temporarily unavailable."
- No infinite 409 conflicts — stale runs are reset after 5 minutes.

---

## 7. Verification After Deploy

1. Visit `https://studyrescue-vzhj.onrender.com/health` — should return `{"status": "ok", "database": "connected"}`.
2. Sign up a new account and verify the session cookie is set.
3. Log in and verify you're redirected to `/dashboard`.
4. Test dark mode toggle (persists in `localStorage`).
5. Import a chat and verify extraction runs without 409 errors.
6. Check Settings → profile updates persist.
7. Check Evaluation → baseline metrics show if labeled CSV exists.

---

## 8. Troubleshooting

| Issue | Fix |
|-------|-----|
| Login cookie not set | Ensure `SESSION_COOKIE_SECURE=true` and `ENV=production` |
| CORS errors | Enable `CORS_ENABLED=true` and set `CORS_ALLOW_ORIGINS` |
| 409 on extraction | Stale runs auto-reset after 5 minutes; retry |
| DB connection timeout | Use connection pooling; Render Postgres handles this |
| "SECRET_KEY missing" | Set `SECRET_KEY` in Render env vars |
