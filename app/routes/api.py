from flask import Blueprint, jsonify, current_app, request, session

from app import db
from app.auth_utils import login_required, roles_required
from app.openstack_client import OpenStackClient, OpenStackError

bp = Blueprint("api", __name__)


@bp.route("/healthz")
def health():
    return jsonify({"status": "ok"})


@bp.route("/readyz")
def readiness():
    try:
        db.ping()
    except Exception:  # noqa: BLE001
        current_app.logger.exception("readiness database check failed")
        return jsonify({"status": "not_ready", "database": "unavailable"}), 503
    return jsonify({"status": "ready", "database": "ok"})


@bp.route("/api/audit-logs")
@roles_required("admin")
def audit_logs():
    return jsonify(db.list_audit_logs())


@bp.route("/api/users")
@roles_required("admin")
def users_list():
    return jsonify([
        {"id": user["id"], "username": user["username"], "role": user["role"], "created_at": str(user["created_at"])}
        for user in db.list_users()
    ])


@bp.route("/api/users/<username>/role", methods=["POST"])
@roles_required("admin")
def user_role(username):
    role = request.form.get("role", "")
    try:
        changed = db.update_user_role(username, role)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not changed:
        return jsonify({"error": "user not found"}), 404
    db.create_audit_log(session.get("username"), "user.role_updated", "user", username, role, request.remote_addr)
    return jsonify({"username": username, "role": role})


@bp.route("/api/tasks")
@login_required
def tasks_status():
    return jsonify(db.list_tasks())


@bp.route("/api/clusters/<int:cluster_id>/volumes")
@login_required
def cluster_volumes(cluster_id):
    """Used by the restore form to populate "restore into an existing
    volume" as an alternative to the default "create a new volume"."""
    cfg = db.get_cluster(cluster_id)
    if not cfg:
        return jsonify({"error": "cluster not found"}), 404

    try:
        client = OpenStackClient(cfg, timeout=current_app.config["OPENSTACK_TIMEOUT"])
        volumes = client.list_volumes()
    except OpenStackError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify([
        {
            "id": v.get("id"),
            "name": v.get("name") or v.get("id"),
            "size": v.get("size"),
            "status": v.get("status"),
        }
        for v in volumes
    ])
