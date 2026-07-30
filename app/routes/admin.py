from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from app import db
from app.security.auth import roles_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("")
@roles_required("admin")
def index():
    return render_template("admin.html", users=db.list_users(), audit_logs=db.list_audit_logs())


@bp.route("/users", methods=["POST"])
@roles_required("admin")
def create_user():
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "viewer")
    try:
        user_id = db.create_user(username, request.form.get("password", ""), role)
    except (ValueError, IntegrityError):
        flash("Unable to create user: username may already exist or the input is invalid", "error")
        return redirect(url_for("admin.index"))
    db.create_audit_log(session.get("username"), "user.created", "user", user_id, f"{username}:{role}", request.remote_addr)
    flash(f"User '{username}' created", "success")
    return redirect(url_for("admin.index"))


@bp.route("/users/<username>/role", methods=["POST"])
@roles_required("admin")
def update_role(username):
    role = request.form.get("role", "")
    if username == session.get("username") and role != "admin":
        flash("You cannot remove your own admin role", "error")
        return redirect(url_for("admin.index"))
    try:
        changed = db.update_user_role(username, role)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.index"))
    if changed:
        db.create_audit_log(session.get("username"), "user.role_updated", "user", username, role, request.remote_addr)
        flash(f"Role for '{username}' updated", "success")
    return redirect(url_for("admin.index"))
