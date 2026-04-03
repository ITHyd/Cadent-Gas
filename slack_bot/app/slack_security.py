import hashlib
import hmac
import time


def verify_slack_signature(
    signing_secret: str,
    timestamp: str | None,
    signature: str | None,
    raw_body: bytes,
    max_age_seconds: int = 60 * 5,
) -> bool:
    if not signing_secret or not timestamp or not signature:
        return False

    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(int(time.time()) - request_time) > max_age_seconds:
        return False

    basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
