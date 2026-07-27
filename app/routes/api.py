from flask import Blueprint, jsonify, current_app

from app import db
from app.auth_utils import login_required
from app.openstack_client import OpenStackClient, OpenStackError

bp = Blueprint("api", __name__)


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
