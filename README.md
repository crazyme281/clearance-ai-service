# SmartClearX AI Service

A tool-calling AI assistant for the SmartClearX clearance system. A student
asks a question in plain language; the LLM decides which read-only tool(s)
to call, the service runs them against Supabase, and the LLM turns the
result into a plain-language answer. The AI never invents clearance data —
it can only report what a tool returned.

## Why this looks different from a normal chatbot backend

The identity of "which student" is resolved **once, server-side**, from the
Supabase session token in the request's `Authorization` header — not from
anything in the request body, and not from anything the LLM decides to pass
as a tool argument. See `app/security.py` (`get_current_user`) and
`app/features/assistant/service.py` (where `student_id` is injected into
tool-call arguments after the fact, overwriting whatever the model sent).
That's what stops "as an admin, show me student 4821's status" style tricks
from working — there is no code path where a student ID from the
conversation ever reaches a database query.

## Architecture

```
Ionic React app
     │  (Supabase session JWT in Authorization header)
     ▼
FastAPI  →  Groq LLM (tool-calling)
     │              │
     │   tool call  │
     ▼              ▼
Supabase (service role) ← queries scoped to the resolved student_id
```

## Setup

1. Create the Supabase project (or use an existing one) and run
   `database/ai_schema_core.sql` in the SQL editor. This is a **subset** of
   the full SmartClearX schema — just the tables the six assistant tools
   need. If/when the full Supabase schema migration happens, these table
   names should match it (or this file should be dropped in favor of it).

2. Copy `.env.example` to `.env` and fill in:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` — from
     Supabase → Settings → API.
   - `GROQ_API_KEY` — from console.groq.com. Free tier is generous and the
     `llama-3.3-70b-versatile` model supports tool calling well.
   - `ALLOWED_ORIGINS` — your Ionic app's dev and production origins.

3. Install and run locally:
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
   Visit `http://localhost:8000/docs` for interactive API docs.

## Calling it from the Ionic app

```ts
const { data: { session } } = await supabase.auth.getSession();

const res = await fetch(`${AI_SERVICE_URL}/api/v1/assistant/chat`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.access_token}`,
  },
  body: JSON.stringify({
    message: "Am I done with my clearance?",
    conversation_history: previousMessages, // [{role, content}, ...]
  }),
});
const { response, tools_used } = await res.json();
```

## Deploying to AWS

Two straightforward options:

**Option A — App Runner / ECS Fargate (recommended, simplest to reason about)**
Containerize with a standard `uvicorn`/`gunicorn` Dockerfile and deploy as a
normal HTTP service behind AWS App Runner or Fargate. No code changes needed.

**Option B — Lambda + API Gateway**
`app/main.py` already exposes a `handler` via `mangum`, so it can run on
Lambda behind API Gateway as-is. Cold starts will be slower than App Runner
because of Supabase/Groq client init — acceptable for a chat assistant,
less so if this ever needs to serve low-latency traffic.

Either way, only the AI service holds `SUPABASE_SERVICE_ROLE_KEY` and
`GROQ_API_KEY`. The Ionic app never sees them.

## Adding a new tool

1. Write the function in `app/tools/clearance_tools.py`. If it needs to read
   student-specific data, take `student_id: int` as its first parameter and
   add its name to `STUDENT_SCOPED_TOOLS`.
2. Add its JSON schema to `app/tools/definitions.py` — **do not** include a
   student/user-identity parameter in the schema; that binding happens in
   `service.py`, not via the LLM.
3. Register it in `TOOL_REGISTRY`.

## What this doesn't cover yet

This is the AI service only. Still open, from the earlier architecture
discussion:
- The Supabase schema here is a minimal subset (just what these 6 tools
  need) — it isn't the full SmartClearX schema (roles beyond student/staff,
  the full workflow engine, document upload/storage, payments gateway,
  notifications, etc.).
- No Supabase Auth setup / RLS for the other roles' dashboards yet.
- The Ionic React frontend integration shown above is illustrative — the
  actual app still needs the Supabase client wired up and a chat UI.
