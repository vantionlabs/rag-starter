"""Signing for outgoing webhooks.

Every delivery carries three headers:

    Webhook-Id:        the event id, stable across retries (dedupe on it)
    Webhook-Timestamp: unix seconds when this attempt was signed
    Webhook-Signature: v1=<hex hmac_sha256(secret, f"{timestamp}.{body}")>

Signing the timestamp together with the body lets the receiver reject a
captured request replayed later: `verify_signature` refuses anything older
than the tolerance. Receivers can copy `verify_signature` as-is.
"""

import hashlib
import hmac
import time

SIGNATURE_VERSION = "v1"
DEFAULT_TOLERANCE_SECONDS = 300


def sign(secret: str, body: bytes, timestamp: int) -> str:
    message = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_VERSION}={digest}"


def verify_signature(
    secret: str,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """True only for a signature made with `secret` over this exact body, within
    the tolerance window. Fails closed on any missing or malformed input."""
    if not secret or not timestamp_header or not signature_header:
        return False
    try:
        timestamp = int(timestamp_header)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        return False
    expected = sign(secret, body, timestamp)
    return hmac.compare_digest(expected, signature_header.strip())
