# Architecture

Three flows carry the whole product: auth, ingestion, and chat.

## Auth flow

Auth lives in the FastAPI backend (fastapi-users). One database, one
migration system; the token never touches JavaScript.

```
Browser                               FastAPI (fastapi-users)
   │  POST /auth/register {email,pw} ──> creates users row (argon2 hash)
   │  POST /auth/jwt/login  ───────────> sets httpOnly cookie (JWT, HS256)
   │<── Set-Cookie: auth=<jwt>; HttpOnly; SameSite=Lax; Secure ──┘
   │
   │  every request: credentials:include (browser attaches the cookie)
   └────────────────────────────────────> get_current_user verifies the JWT
                                           locally → CurrentUser{id, email}
```

- The token is an httpOnly cookie: XSS cannot read it. `SameSite=Lax` blocks
  CSRF as long as the frontend and API share a registrable domain (see
  setup-auth.md).
- `CurrentUser{id: UUID, email}` from `app/auth/dependencies.py` is the only
  auth contract the rest of the backend sees, and the single seam to swap
  when a project escalates to enterprise SSO / OIDC (setup-auth.md).

## Ingestion flow (the event engine)

```
POST /documents/presign  ->  row (pending_upload) + presigned PUT URL
browser PUT -> R2            (Content-Type must match the presigned one)
POST /documents/{id}/confirm -> status=uploaded + Event(document.ingest)
Celery worker: run_event(event_id)
  └─ WorkflowRegistry["document.ingest"] = DocumentIngestWorkflow
     MarkProcessing -> FetchFromR2 -> ParseDocument -> ChunkDocument
       -> EmbedChunks -> StoreChunks         (status: processing -> ready)
     on_failure: document.status = failed (+ error), event.status = failed
frontend polls GET /documents until settled
```

The engine ("workflows execute nodes that pass data through a TaskContext")
is generic: any background job = an event type + a registered workflow.
The event row doubles as the job's audit trail (`status`, `attempts`,
`result`, `error`), with retries and backoff, dead-lettering, idempotency and
crash recovery. Outgoing webhooks run on the same engine. See
[background-jobs-and-webhooks.md](background-jobs-and-webhooks.md).

## Chat flow (synchronous SSE, deliberately not queued)

```
POST /chat/stream {thread_id, messages, collection?}
  ├─ require_thread_access (404 on foreign threads)
  ├─ status: analyzing
  ├─ agent run (worker thread): PydanticAI + tools
  │    └─ search_documents -> hybrid retrieval -> TurnRegistry.record(...)
  ├─ status: verifying -> grounding validator (retry once on failure)
  │    ├─ structural: markers <-> citations, registry allowlist, verbatim excerpts
  │    └─ LLM judge: does each excerpt support its claim? (fail-closed)
  ├─ stream: text-delta word-by-word + data-citation parts
  ├─ persist thread turn + citations (ONLY after validation)
  └─ answer.completed webhook (when WEBHOOK_URL is set)
```

Retrieval = pgvector cosine (HNSW) and Postgres FTS (generated tsvector,
GIN) in parallel, fused with Reciprocal Rank Fusion (k=60), optional
reranking, ±1 neighbor expansion by chunk_index. All retrieval filters on
`user_id`, and on `collection` when the chat request names one. The agent,
judge, and reranker are provider-agnostic (OpenAI, Anthropic, Azure or
OpenRouter via config); see [ai-quality.md](ai-quality.md).

## Non-goals (v1)

Organisations and teams, OAuth social logins, queue-backed chat, file types
beyond md/txt/pdf, row-level security (ownership is app-layer by design).
[setup-auth.md](setup-auth.md) covers adding SSO or multi-tenancy.
