<p align="center">
  <a href="https://vantion.co">
    <img src="https://raw.githubusercontent.com/vantionlabs/.github/main/profile/banner.png" alt="Vantion Labs" width="100%" />
  </a>
</p>

<h1 align="center">RAG starter</h1>

<p align="center">
  <b>Document Q&A that answers only from your documents.</b><br />
  Event-driven ingestion, hybrid retrieval, and citations checked before they reach a user.
</p>

<p align="center">
  <a href="https://github.com/vantionlabs/rag-starter/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/vantionlabs/rag-starter/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="https://www.python.org"><img alt="python 3.12" src="https://img.shields.io/badge/python_3.12-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="https://fastapi.tiangolo.com"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" /></a>
  <a href="https://github.com/pgvector/pgvector"><img alt="pgvector" src="https://img.shields.io/badge/pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white" /></a>
  <a href="https://nextjs.org"><img alt="Next.js 16" src="https://img.shields.io/badge/Next.js_16-000000?style=flat-square&logo=nextdotjs&logoColor=white" /></a>
  <a href="https://docs.celeryq.dev"><img alt="Celery + Redis" src="https://img.shields.io/badge/Celery_+_Redis-DC382D?style=flat-square&logo=redis&logoColor=white" /></a>
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/licence-MIT-f4f4f6?style=flat-square" /></a>
  <a href="https://vantion.co"><img alt="Vantion Labs" src="https://img.shields.io/badge/by-Vantion_Labs-2233f0?style=flat-square" /></a>
</p>

---

A production-shaped retrieval-augmented generation app from
[Vantion Labs](https://vantion.co). Users upload documents, a background
pipeline chunks and embeds them, and a chat answers **only** from those
documents, with citations that are checked before anything reaches the user.

It is built to be forked and owned: plain FastAPI, Postgres and Next.js, no
hosted RAG service, no framework you have to learn first.

## What you get

- **Hybrid retrieval.** pgvector (HNSW, cosine) and Postgres full-text search,
  fused with reciprocal rank fusion, filtered per user and per collection.
  Optional LLM reranking.
- **Citations that fail closed.** The agent may only cite chunks its tools
  returned in this turn. Every citation is checked verbatim against the chunk
  and then by an LLM judge. When a claim does not hold up, the user gets an
  honest "couldn't verify" instead of a confident guess.
- **Background ingestion.** Uploads go straight from the browser to R2 with a
  presigned URL. A Celery worker parses, chunks, embeds and stores them, with
  retries, backoff, dead-lettering, idempotency and crash recovery.
- **Signed outgoing webhooks.** `document.ready`, `document.failed` and
  `answer.completed`, HMAC-signed with replay protection, delivered with the
  same retries.
- **Evals that gate changes.** A CSV test set (the
  [eval test set template](https://github.com/vantionlabs/eval-test-set-template)
  format) scored for retrieval, required and forbidden content, and refusals.
  Any critical failure fails the run.
- **Costs and traces.** Every LLM call is written to an `llm_usage` table with
  its token cost. Optional OpenTelemetry tracing to Langfuse.
- **Swap providers by config.** OpenAI, Anthropic, Azure OpenAI or
  OpenRouter for chat, and OpenAI or Azure for embeddings.
- **Auth that stays out of your way.** fastapi-users with an httpOnly cookie
  session, and one seam to replace when you move to your own identity
  provider.

## Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12, FastAPI, uv |
| Background jobs | Celery on Redis, a small Workflow/Node event engine |
| Database | PostgreSQL with pgvector, SQLAlchemy 2, Alembic |
| Agent | PydanticAI, structured grounded answers |
| Storage | Cloudflare R2 (any S3-compatible store works) |
| Frontend | Next.js 16, Tailwind v4, shadcn/ui, TanStack Query and Form, AI SDK v5 |
| Ops | structlog, readiness checks, Redis rate limiting, optional Sentry and Langfuse |
| Tooling | ruff, pyright, pytest, GitHub Actions |

## Quickstart

You need Docker, [uv](https://docs.astral.sh/uv/), Node 22 with pnpm, an
OpenAI API key and an R2 bucket (see [docs/setup-r2.md](docs/setup-r2.md)).

```bash
# 1. Postgres (pgvector) and Redis
docker compose up -d postgres redis

# 2. API
cd backend
cp .env.example .env            # set OPENAI_API_KEY, AUTH_SECRET and R2_*
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# 3. Worker, in a second terminal
cd backend
uv run celery -A app.worker.celery_app worker --beat --loglevel=INFO

# 4. Frontend, in a third terminal
cd frontend
cp .env.example .env            # NEXT_PUBLIC_API_URL=http://localhost:8000
pnpm install
pnpm dev                        # http://localhost:3000
```

Sign up, upload a `.md` or `.txt` file (PDFs need `uv sync --extra docling`),
wait for it to show `ready`, and ask a question about it. The API reference
is at http://localhost:8000/docs.

## How it fits together

```
browser ──presigned PUT──> R2
   │
   ├─ POST /documents/{id}/confirm ──> document.ingest event ──> worker
   │                                    fetch → parse → chunk → embed → store
   │                                    └─> document.ready webhook
   │
   └─ POST /chat/stream (SSE) ──> hybrid search ──> agent ──> citation validator ──> stream
                                                                           └─> answer.completed webhook
```

1. **Auth** lives in the API. Login sets an httpOnly cookie holding a JWT, so
   no token is ever readable from JavaScript. Every query is scoped to the
   signed-in user. See [docs/setup-auth.md](docs/setup-auth.md).
2. **Ingestion** runs on the event engine, so a failed embedding call is
   retried instead of leaving a document half-indexed. See
   [docs/background-jobs-and-webhooks.md](docs/background-jobs-and-webhooks.md).
3. **Chat** streams synchronously. The agent's search tool records every
   chunk it retrieves in a per-turn registry, and the validator checks each
   citation against that registry before the answer is streamed or saved.
   See [docs/ai-quality.md](docs/ai-quality.md).

[docs/architecture.md](docs/architecture.md) has the full request flows.
[AGENTS.md](AGENTS.md) has the conventions for anyone, human or coding agent,
changing this code.

## Checks

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -m "not integration"      # offline, no database or network
uv run python -m evals.run_eval         # needs the stack running and an LLM key

cd ../frontend
pnpm typecheck && pnpm build
```

## Deploy

Railway runs it as five services: Postgres (pgvector), Redis, the API and the
worker (one image, two start commands), and the frontend. See
[docs/setup-railway.md](docs/setup-railway.md) and
[docs/operations.md](docs/operations.md).

## Licence

MIT. See [LICENSE](LICENSE). Built by [Vantion Labs](https://vantion.co);
if you want help putting it into production, [talk to the founder](https://vantion.co/book-a-call).
