"""Outgoing webhook delivery, as a workflow.

`emit_webhook` records a `webhook.deliver` event; the worker POSTs it to
`settings.webhook_url`. Running delivery through the event engine gives it the
engine's retries with backoff, dead-lettering and crash recovery, so a
receiver that is briefly down still gets every event.

Event types sent: `document.ready`, `document.failed`, `answer.completed`.
Payloads carry ids and metadata only, never document text or answer content;
the receiver fetches what it needs through the API.
"""

import json
import time
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.node import Node
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow
from app.security.webhooks import sign


def emit_webhook(
    db: Session,
    event_type: str,
    data: dict,
    *,
    user_id: uuid.UUID | None,
    dedupe: str,
) -> None:
    """Queue a webhook for delivery. No-op when no webhook URL is configured.

    `dedupe` makes the delivery idempotent: re-running the step that emits it
    (a retried ingestion, say) does not send the same event twice.
    """
    if not settings.webhook_url:
        return
    from app.core.intake import create_event

    create_event(
        db,
        type="webhook.deliver",
        payload={
            "type": event_type,
            "data": data,
            "created_at": datetime.now(UTC).isoformat(),
        },
        user_id=user_id,
        idempotency_key=f"webhook:{event_type}:{dedupe}",
    )


class Deliver(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        if not settings.webhook_url:
            ctx.nodes[self.name] = {"skipped": "no webhook_url"}
            return ctx
        if not settings.webhook_secret:
            # Never send unsigned: the receiver could not tell it came from us.
            raise RuntimeError("webhook_secret is required when webhook_url is set")

        body = json.dumps({"id": str(ctx.event_id), **ctx.payload}, separators=(",", ":")).encode()
        timestamp = int(time.time())
        response = httpx.post(
            settings.webhook_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "Webhook-Id": str(ctx.event_id),
                "Webhook-Timestamp": str(timestamp),
                "Webhook-Signature": sign(settings.webhook_secret, body, timestamp),
            },
            timeout=settings.webhook_timeout_seconds,
        )
        # Any non-2xx raises, so the engine retries with backoff.
        response.raise_for_status()
        ctx.nodes[self.name] = {"status_code": response.status_code}
        return ctx


@register("webhook.deliver")
class WebhookDeliveryWorkflow(Workflow):
    nodes = [Deliver()]
