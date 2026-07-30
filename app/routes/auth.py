from urllib.parse import urljoin, urlparse

from flask import Blueprint, current_app, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash

from app import db

bp = Blueprint("auth", __name__)


def _safe_next_url(value):
    if not value:
        return None
    host_url = urlparse(request.host_url)
    target_url = urlparse(urljoin(request.host_url, value))
    return value if target_url.scheme == host_url.scheme and target_url.netloc == host_url.netloc else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("volumes.list_volumes"))

    if request.method == "POST":
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        if db.count_recent_login_failures(client_ip, current_app.config["LOGIN_RATE_LIMIT_WINDOW"]) >= current_app.config["LOGIN_RATE_LIMIT_ATTEMPTS"]:
            db.create_audit_log(request.form.get("username", ""), "login.blocked", "session", ip_address=client_ip)
            flash("Too many failed login attempts. Try again later.", "error")
            return render_template("login.html"), 429
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user_by_username(username)

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session.permanent = True
            db.create_audit_log(username, "login.succeeded", "session", ip_address=client_ip)
            next_url = _safe_next_url(request.args.get("next")) or url_for("volumes.list_volumes")
            return redirect(next_url)

        db.create_audit_log(username, "login.failed", "session", ip_address=client_ip)
        flash("Invalid username or password", "error")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
