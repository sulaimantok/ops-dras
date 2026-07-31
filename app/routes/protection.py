from flask import Blueprint, current_app, render_template, request

from app import db
from app.security.auth import login_required
from app.services.openstack import OpenStackClient, OpenStackError

bp = Blueprint("protection", __name__, url_prefix="/protection")


@bp.route("")
@login_required
def index():
    clusters = db.list_clusters()
    cluster_id = request.args.get("cluster_id", type=int)
    selected_cluster = db.get_cluster(cluster_id) if cluster_id else None
    volumes = []
    error = None
    if cluster_id and not selected_cluster:
        error = "Selected cluster not found."
    elif selected_cluster:
        try:
            client = OpenStackClient(selected_cluster, timeout=current_app.config["OPENSTACK_TIMEOUT"])
            volumes = client.list_volumes()
        except OpenStackError as exc:
            error = str(exc)

    recovery_query = request.args.get("recovery_q", "").strip()
    recovery_cluster_id = request.args.get("recovery_cluster_id", type=int)
    recovery_page = max(1, request.args.get("recovery_page", 1, type=int))
    recovery_per_page = 10
    restore_candidates = _available_recovery_points(clusters)
    if recovery_query:
        needle = recovery_query.lower()
        restore_candidates = [
            task for task in restore_candidates
            if needle in (task.get("volume_name") or "").lower()
            or needle in (task.get("volume_id") or "").lower()
            or needle in (task.get("source_backup_id") or "").lower()
        ]
    if recovery_cluster_id:
        restore_candidates = [
            task for task in restore_candidates
            if task.get("source_cluster_id") == recovery_cluster_id
        ]
    recovery_total = len(restore_candidates)
    recovery_pages = max(1, (recovery_total + recovery_per_page - 1) // recovery_per_page)
    recovery_page = min(recovery_page, recovery_pages)
    recovery_start = (recovery_page - 1) * recovery_per_page
    restore_candidates = restore_candidates[recovery_start:recovery_start + recovery_per_page]
    return render_template(
        "protection.html",
        clusters=clusters,
        selected_cluster=selected_cluster,
        volumes=volumes,
        error=error,
        restore_candidates=restore_candidates,
        recovery_filters={"q": recovery_query, "cluster_id": recovery_cluster_id},
        recovery_page=recovery_page,
        recovery_pages=recovery_pages,
        recovery_total=recovery_total,
    )


def _available_recovery_points(clusters):
    """Return successful local backups that still exist in source Cinder."""
    cluster_by_id = {cluster["id"]: cluster for cluster in clusters}
    clients = {}
    candidates = []
    for task in db.list_tasks(limit=100, status="succeeded", task_type="backup"):
        backup_id = task.get("source_backup_id")
        cluster = cluster_by_id.get(task.get("source_cluster_id"))
        if not backup_id or not cluster:
            continue
        try:
            client = clients.setdefault(
                cluster["id"],
                OpenStackClient(cluster, timeout=current_app.config["OPENSTACK_TIMEOUT"]),
            )
            backup = client.get_backup(backup_id)
        except OpenStackError as exc:
            if exc.http_status == 404:
                continue
            current_app.logger.warning("Unable to reconcile backup %s: %s", backup_id, exc)
            task["live_status"] = "unverified"
            candidates.append(task)
            continue
        if backup.get("status") != "available":
            continue
        task["live_status"] = backup["status"]
        task["live_backup"] = backup
        candidates.append(task)
    return candidates
