"""Small same-origin CSRF protection without a form framework dependency."""
import hmac
import secrets

from flask import abort, request, session


def token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def protect():
    """Reject unsafe form requests that do not carry the current token."""
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return
    supplied = request.form.get("csrf_token", "")
    if not hmac.compare_digest(supplied, token()):
        abort(400, "Invalid or missing CSRF token")
