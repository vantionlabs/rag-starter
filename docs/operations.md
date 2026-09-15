# Operations

The production layer: health, tracing, rate limits and cost visibility.
Everything optional is env-gated and no-ops when unset, so the starter runs
locally with nothing configured.

## Health checks

- `GET /health`: cheap liveness (the process is up).
- `GET /health/ready`: readiness: checks Postgres **and** Redis, returns
  **503** if either is down. Point the platform healthcheck (Railway) here so
  a broken dependency stops traffic. Body: `{"status", "checks": {...}}`.

## Correlation IDs

Every request gets an `X-Request-ID` (from the inbound header or generated),
bound to structlog so every log line for that request (API, SQL, LLM,
workflow) carries the same id, and echoed back in the response header. Quote
it in a bug report to pull the whole trace.

## Error tracking (Sentry)

Set `SENTRY_DSN` and install the extra (`uv sync --extra sentry`). Captures
unhandled exceptions in the API and worker. `send_default_pii=False`: no
request bodies or user data leave your infra by default. No DSN → no-op.

## Rate limiting

`app/security/ratelimit.py` is a Redis fixed-window limiter applied to
`/chat/stream` (the costly path): `CHAT_RATE_LIMIT` requests per
`CHAT_RATE_WINDOW_SECONDS` per user, `429` when exceeded (with `Retry-After`).
It **fails open** if Redis blips (a limiter outage shouldn't take down the
API). To protect another route, add `Depends(RateLimiter(limit, window,
"scope"))`.

## LLM usage + cost

Every model call (chat, embedding, grounding) writes an `llm_usage` row with
token counts and a computed cost. Prices live in
`app/observability/usage.py` (`PRICES`, USD per 1M tokens). **Update them
when rates change or you add a model**; unknown models log at cost 0.

```
GET /usage?days=30   → { total_cost_usd, by_operation: [...] }
```

Use it for a spend view, or as the basis for per-user quotas
(query the table in a rate-limit-style dependency).

## Tracing (Langfuse)

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (and `LANGFUSE_HOST` for a
self-hosted or EU instance). `app/observability/tracing.py` instruments every
pydantic-ai agent once and exports the spans over OTLP, so each chat turn shows
the agent run, its tool calls, the grounding judge and the reranker with
prompts, completions and token counts. No keys, no tracing.
