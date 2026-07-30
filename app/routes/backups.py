from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request

from app import db
from app.auth_utils import login_required, roles_required
from app.openstack_client import OpenStackClient, OpenStackError

bp = Blueprint("backups", __name__)


@bp.route("/backups")
@login_required
def list_backups():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 20
    status = request.args.get("status", "").strip()
    task_type = request.args.get("type", "").strip()
    search = request.args.get("q", "").strip()
    total = db.count_tasks(status=status or None, task_type=task_type or None, search=search or None)
    task_rows = db.list_tasks(
        limit=per_page, offset=(page - 1) * per_page,
        status=status or None, task_type=task_type or None, search=search or None,
    )
    clusters = db.list_clusters()
    return render_template(
        "backups.html", tasks=task_rows, clusters=clusters, page=page,
        pages=max(1, (total + per_page - 1) // per_page), total=total,
        filters={"status": status, "type": task_type, "q": search},
    )


@bp.route("/backups/<int:task_id>/restore", methods=["POST"])
@roles_required("admin", "operator")
def restore_backup(task_id):
    source_task = db.get_task(task_id)
    if not source_task or source_task["task_type"] != "backup":
        flash("Original backup task not found", "error")
        return redirect(url_for("backups.list_backups"))

    if source_task["status"] != "succeeded" or not source_task["source_backup_id"]:
        flash("Backup must complete successfully before it can be restored", "error")
        return redirect(url_for("backups.list_backups"))

    dest_cluster_id = request.form.get("dest_cluster_id", type=int)
    dest_cluster = db.get_cluster(dest_cluster_id) if dest_cluster_id else None
    if not dest_cluster:
        flash("Pick a destination cluster to restore to", "error")
        return redirect(url_for("backups.list_backups"))

    # Blank/omitted means "create a new volume" (Cinder's default restore
    # behavior); a value here means "restore into this existing volume".
    dest_volume_id = request.form.get("dest_volume_id") or None
    if dest_volume_id:
        try:
            volume = OpenStackClient(dest_cluster, timeout=current_app.config["OPENSTACK_TIMEOUT"]).get_volume(dest_volume_id)
        except OpenStackError as exc:
            flash(f"Unable to validate destination volume: {exc}", "error")
            return redirect(url_for("backups.list_backups"))
        if volume.get("status") != "available":
            flash("Destination volume must be in available status", "error")
            return redirect(url_for("backups.list_backups"))

    restore_task_id, created = db.create_task(
        task_type="restore",
        volume_id=source_task["volume_id"],
        volume_name=source_task["volume_name"],
        source_backup_id=source_task["source_backup_id"],
        source_cluster_id=source_task["source_cluster_id"],
        dest_cluster_id=dest_cluster_id,
        created_by=session.get("username"),
        status="queued",
        message="Queued",
        dest_volume_id=dest_volume_id,
        idempotency_key=f"restore:{source_task['source_backup_id']}:{dest_cluster_id}:{dest_volume_id or 'new'}",
        max_attempts=current_app.config["TASK_MAX_ATTEMPTS"],
    )
    if created:
        db.create_audit_log(session.get("username"), "restore.queued", "task", restore_task_id, ip_address=request.remote_addr)
        flash(f"Restore to {dest_cluster['name']} queued (task #{restore_task_id})", "success")
    else:
        flash(f"An equivalent restore task already exists (task #{restore_task_id})", "info")
    return redirect(url_for("backups.list_backups"))


@bp.route("/backups/<int:task_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_task(task_id):
    task = db.get_task(task_id)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("backups.list_backups"))

    if task["status"] in ("queued", "running"):
        flash("Can't delete a task while it's still in progress", "error")
        return redirect(url_for("backups.list_backups"))

    db.delete_task(task_id)
    db.create_audit_log(session.get("username"), "task.deleted", "task", task_id, ip_address=request.remote_addr)
    flash(f"Task #{task_id} removed from history", "success")
    return redirect(url_for("backups.list_backups"))


@bp.route("/backups/<int:task_id>/cancel", methods=["POST"])
@roles_required("admin", "operator")
def cancel_task(task_id):
    if not db.cancel_task(task_id):
        flash("Only queued tasks can be cancelled", "error")
    else:
        db.create_audit_log(session.get("username"), "task.cancelled", "task", task_id, ip_address=request.remote_addr)
        flash(f"Task #{task_id} cancelled", "success")
    return redirect(url_for("backups.list_backups"))
