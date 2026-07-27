from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request

from app import db, tasks
from app.auth_utils import login_required
from app.openstack_client import OpenStackClient, OpenStackError

bp = Blueprint("volumes", __name__)


@bp.route("/")
@login_required
def index():
    return redirect(url_for("volumes.list_volumes"))


@bp.route("/volumes")
@login_required
def list_volumes():
    clusters = db.list_clusters()
    cluster_id = request.args.get("cluster_id", type=int)
    selected_cluster = None
    volumes = []
    error = None

    if not clusters:
        error = "No clusters configured yet. Go to Clusters to add one."
    elif cluster_id:
        selected_cluster = db.get_cluster(cluster_id)
        if not selected_cluster:
            error = "Selected cluster not found."
        else:
            try:
                client = OpenStackClient(selected_cluster, timeout=current_app.config["OPENSTACK_TIMEOUT"])
                volumes = client.list_volumes()
            except OpenStackError as exc:
                error = str(exc)

    return render_template(
        "volumes.html",
        clusters=clusters,
        selected_cluster=selected_cluster,
        volumes=volumes,
        error=error,
    )


@bp.route("/volumes/backup", methods=["POST"])
@login_required
def backup_volume():
    cluster_id = request.form.get("cluster_id", type=int)
    volume_id = request.form.get("volume_id")
    volume_name = request.form.get("volume_name", volume_id)

    cluster = db.get_cluster(cluster_id) if cluster_id else None
    if not cluster or not volume_id:
        flash("Missing cluster or volume", "error")
        return redirect(url_for("volumes.list_volumes"))

    task_id = db.create_task(
        task_type="backup",
        volume_id=volume_id,
        volume_name=volume_name,
        source_cluster_id=cluster_id,
        created_by=session.get("username"),
        status="pending",
        message="Queued",
    )
    tasks.submit_backup(current_app._get_current_object(), task_id, cluster_id, volume_id, volume_name)
    flash(f"Backup started for volume {volume_name} on {cluster['name']} (task #{task_id})", "success")
    return redirect(url_for("backups.list_backups"))
