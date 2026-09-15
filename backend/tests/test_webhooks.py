"""Outgoing webhook signing and delivery (no network, no DB)."""

import json
import uuid

import httpx
import pytest

from app.core.task_context import TaskContext
from app.security.webhooks import sign, verify_signature
from app.workflows import webhook_delivery

SECRET = "whsec_test"
BODY = b'{"type":"document.ready"}'
NOW = 1_800_000_000


def test_signature_round_trip():
    signature = sign(SECRET, BODY, NOW)
    assert signature.startswith("v1=")
    assert verify_signature(SECRET, BODY, str(NOW), signature, now=NOW)


def test_tampered_body_is_rejected():
    signature = sign(SECRET, BODY, NOW)
    assert not verify_signature(SECRET, b'{"type":"document.failed"}', str(NOW), signature, now=NOW)


def test_wrong_secret_is_rejected():
    signature = sign("other", BODY, NOW)
    assert not verify_signature(SECRET, BODY, str(NOW), signature, now=NOW)


def test_old_timestamp_is_rejected_as_a_replay():
    signature = sign(SECRET, BODY, NOW)
    assert not verify_signature(SECRET, BODY, str(NOW), signature, now=NOW + 301)


def test_timestamp_is_part_of_the_signature():
    signature = sign(SECRET, BODY, NOW)
    assert not verify_signature(SECRET, BODY, str(NOW + 1), signature, now=NOW)


@pytest.mark.parametrize(
    ("secret", "timestamp", "signature"),
    [
        ("", str(NOW), "v1=x"),
        (SECRET, None, "v1=x"),
        (SECRET, str(NOW), None),
        (SECRET, "soon", "v1=x"),
    ],
)
def test_missing_or_malformed_input_fails_closed(secret, timestamp, signature):
    assert not verify_signature(secret, BODY, timestamp, signature, now=NOW)


def _ctx() -> TaskContext:
    return TaskContext(
        event_id=uuid.uuid4(),
        event_type="webhook.deliver",
        payload={"type": "document.ready", "data": {"document_id": "d1"}},
        user_id=None,
        db=None,  # type: ignore[arg-type]
    )


def test_delivery_is_skipped_without_a_url(monkeypatch):
    monkeypatch.setattr(webhook_delivery.settings, "webhook_url", "")
    ctx = webhook_delivery.Deliver().process(_ctx())
    assert ctx.nodes["Deliver"] == {"skipped": "no webhook_url"}


def test_delivery_refuses_to_send_unsigned(monkeypatch):
    monkeypatch.setattr(webhook_delivery.settings, "webhook_url", "https://example.com/hook")
    monkeypatch.setattr(webhook_delivery.settings, "webhook_secret", "")
    with pytest.raises(RuntimeError):
        webhook_delivery.Deliver().process(_ctx())


def test_delivery_sends_a_verifiable_signed_request(monkeypatch):
    monkeypatch.setattr(webhook_delivery.settings, "webhook_url", "https://example.com/hook")
    monkeypatch.setattr(webhook_delivery.settings, "webhook_secret", SECRET)
    sent = {}

    def fake_post(url, *, content, headers, timeout):
        sent.update(url=url, content=content, headers=headers)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(webhook_delivery.httpx, "post", fake_post)
    ctx = _ctx()
    webhook_delivery.Deliver().process(ctx)

    headers = sent["headers"]
    assert headers["Webhook-Id"] == str(ctx.event_id)
    assert verify_signature(
        SECRET,
        sent["content"],
        headers["Webhook-Timestamp"],
        headers["Webhook-Signature"],
        now=int(headers["Webhook-Timestamp"]),
    )
    assert json.loads(sent["content"])["type"] == "document.ready"


def test_non_2xx_raises_so_the_engine_retries(monkeypatch):
    monkeypatch.setattr(webhook_delivery.settings, "webhook_url", "https://example.com/hook")
    monkeypatch.setattr(webhook_delivery.settings, "webhook_secret", SECRET)
    monkeypatch.setattr(
        webhook_delivery.httpx,
        "post",
        lambda url, **_: httpx.Response(503, request=httpx.Request("POST", url)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        webhook_delivery.Deliver().process(_ctx())


def test_emit_is_a_no_op_without_a_url(monkeypatch):
    monkeypatch.setattr(webhook_delivery.settings, "webhook_url", "")
    webhook_delivery.emit_webhook(None, "document.ready", {}, user_id=None, dedupe="x")  # type: ignore[arg-type]
