# Background jobs and webhooks

Anything that does not have to answer within a request runs on the event
engine: document ingestion and outgoing webhook delivery today, and whatever
you add next.

## How the engine works

```
create_event(type, payload, idempotency_key?) ──> events row (queued) ──> Celery
                                                                          │
                                   run_event ──> workflow_for(type) ──> nodes
                                        │
                                        ├─ success: status=done, result
                                        ├─ failure, attempts left: requeue with backoff
                                        └─ failure, attempts exhausted: status=failed, on_failure()
```

The `events` row is the durable record of every job: `status`, `attempts` and
`max_attempts`, `result`, `error`.

- **Retries.** A workflow that raises is retried with exponential backoff
  (`EVENT_RETRY_BASE_DELAY_SECONDS * 2^(attempt-1)`, capped at
  `EVENT_RETRY_MAX_DELAY_SECONDS`) up to `EVENT_MAX_ATTEMPTS`.
- **Dead letters.** Exhausted events stay as `failed` rows with the error, and
  the workflow's `on_failure` hook runs so nothing is left half-done (a
  document never stays stuck in `processing`). Query the `events` table to
  inspect them.
- **Idempotency.** Pass an `idempotency_key` to `create_event`; a second call
  with the same key returns the existing event instead of creating another.
- **Crash recovery.** `sweep_stale_events` runs on Celery beat every
  `STALE_SWEEP_INTERVAL_SECONDS` and requeues events a crashed worker left in
  `processing` for longer than `STALE_PROCESSING_MINUTES`.

## Adding a job

1. Write a `Workflow` of `Node`s in `app/workflows/`. Each node does one thing
   to the `TaskContext` and stores its output in `ctx.nodes[self.name]`.
2. Register it with `@register("your.event.type")` and import the module in
   `app/workflows/__init__.py`.
3. Create events with `app.core.intake.create_event(db, type=..., payload=...)`.

Nodes may run more than once when a later node fails and the event is retried,
so make side effects idempotent: write the row that records an outbound call,
with a unique key, before making the call.

Scheduled jobs go in `celery_app.beat_schedule` (`app/worker/celery_app.py`).

## Outgoing webhooks

Set `WEBHOOK_URL` and `WEBHOOK_SECRET` (on the API and the worker) and the app
POSTs these events to your endpoint:

| Event | When | `data` |
| --- | --- | --- |
| `document.ready` | Ingestion finished | `document_id`, `collection`, `chunks` |
| `document.failed` | Ingestion failed after its retries | `document_id`, `collection`, `error` |
| `answer.completed` | A chat turn finished and was saved | `thread_id`, `message_id`, `outcome` (`answered`, `insufficient_evidence` or `unverified`), `citations` |

Payloads carry ids and metadata, never document text or answer content: fetch
what you need through the API.

```json
{
  "id": "5d0c8a6e-...",
  "type": "document.ready",
  "data": { "document_id": "9f1e...", "collection": "default", "chunks": 42 },
  "created_at": "2026-09-15T12:00:00+00:00"
}
```

Delivery runs as a `webhook.deliver` event, so a receiver that is down or
returns a non-2xx status gets the same retries, backoff and dead-lettering as
any other job. `id` stays the same across retries: dedupe on it.

### Verifying a delivery

Every request carries:

```
Webhook-Id:        the event id
Webhook-Timestamp: unix seconds when this attempt was signed
Webhook-Signature: v1=<hex HMAC-SHA256 of "{timestamp}.{raw body}" with WEBHOOK_SECRET>
```

Verify against the raw request body, before parsing it, and reject old
timestamps so a captured request cannot be replayed. In Python, copy
`verify_signature` from `app/security/webhooks.py`:

```python
from app.security.webhooks import verify_signature

ok = verify_signature(
    secret,
    raw_body,
    request.headers.get("Webhook-Timestamp"),
    request.headers.get("Webhook-Signature"),
)  # False for a wrong secret, a changed body, or a timestamp older than 5 minutes
```
