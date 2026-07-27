from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request

from app import db, tasks
from app.auth_utils import login_required

bp = Blueprint("backups", __name__)


@bp.route("/backups")
@login_required
def list_backups():
    task_rows = db.list_tasks()
    clusters = db.list_clusters()
    return render_template("backups.html", tasks=task_rows, clusters=clusters)


@bp.route("/backups/<int:task_id>/restore", methods=["POST"])
@login_required
def restore_backup(task_id):
    source_task = db.get_task(task_id)
    if not source_task or source_task["task_type"] != "backup":
        flash("Original backup task not found", "error")
        return redirect(url_for("backups.list_backups"))

    if source_task["status"] != "success" or not source_task["source_backup_id"]:
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

    restore_task_id = db.create_task(
        task_type="restore",
        volume_id=source_task["volume_id"],
        volume_name=source_task["volume_name"],
        source_backup_id=source_task["source_backup_id"],
        source_cluster_id=source_task["source_cluster_id"],
        dest_cluster_id=dest_cluster_id,
        created_by=session.get("username"),
        status="pending",
        message="Queued",
    )
    tasks.submit_restore(
        current_app._get_current_object(), restore_task_id,
        source_task["source_cluster_id"], dest_cluster_id, source_task["source_backup_id"],
        dest_volume_id,
    )
    flash(f"Cross-cluster restore to {dest_cluster['name']} started (task #{restore_task_id})", "success")
    return redirect(url_for("backups.list_backups"))


@bp.route("/backups/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = db.get_task(task_id)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("backups.list_backups"))

    if task["status"] in ("pending", "running"):
        flash("Can't delete a task while it's still in progress", "error")
        return redirect(url_for("backups.list_backups"))

    db.delete_task(task_id)
    flash(f"Task #{task_id} removed from history", "success")
    return redirect(url_for("backups.list_backups"))
