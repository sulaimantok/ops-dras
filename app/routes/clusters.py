from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from app import db
from app.auth_utils import login_required
from app.openstack_client import OpenStackClient, OpenStackError

bp = Blueprint("clusters", __name__)

FIELDS = [
    "name", "auth_url", "username", "password", "app_cred_id", "app_cred_secret",
    "project_name", "project_id", "user_domain", "project_domain", "region",
]
SECRET_FIELDS = {"password", "app_cred_secret"}
AUTH_METHODS = {"password", "application_credential"}


def _fields_from_form(existing=None):
    updates = {}
    for field in FIELDS:
        value = request.form.get(field, "")
        if field in SECRET_FIELDS and not value:
            if existing is None:
                updates[field] = ""
            continue  # keep existing secret if left blank on edit
        updates[field] = value.strip() if field not in SECRET_FIELDS else value
    updates["verify_ssl"] = 1 if request.form.get("verify_ssl") == "on" else 0
    auth_method = request.form.get("auth_method", "password")
    updates["auth_method"] = auth_method if auth_method in AUTH_METHODS else "password"
    return updates


@bp.route("/clusters")
@login_required
def list_clusters():
    clusters = db.list_clusters()
    return render_template("clusters.html", clusters=clusters)


@bp.route("/clusters", methods=["POST"])
@login_required
def create_cluster():
    fields = _fields_from_form(existing=None)
    if not fields.get("name") or not fields.get("auth_url"):
        flash("Cluster name and Auth URL are required", "error")
        return redirect(url_for("clusters.list_clusters"))

    cluster_id = db.create_cluster(**fields)
    flash(f"Cluster '{fields['name']}' added", "success")
    return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))


@bp.route("/clusters/<int:cluster_id>", methods=["POST"])
@login_required
def update_cluster(cluster_id):
    existing = db.get_cluster(cluster_id)
    if not existing:
        flash("Cluster not found", "error")
        return redirect(url_for("clusters.list_clusters"))

    fields = _fields_from_form(existing=existing)
    db.update_cluster(cluster_id, **fields)
    flash(f"Cluster '{fields.get('name', existing['name'])}' saved", "success")
    return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))


@bp.route("/clusters/<int:cluster_id>/delete", methods=["POST"])
@login_required
def delete_cluster(cluster_id):
    existing = db.get_cluster(cluster_id)
    if existing:
        db.delete_cluster(cluster_id)
        flash(f"Cluster '{existing['name']}' deleted", "success")
    return redirect(url_for("clusters.list_clusters"))


@bp.route("/clusters/<int:cluster_id>/test", methods=["POST"])
@login_required
def test_connection(cluster_id):
    cfg = db.get_cluster(cluster_id)
    if not cfg:
        flash("Cluster not found", "error")
        return redirect(url_for("clusters.list_clusters"))

    try:
        client = OpenStackClient(cfg, timeout=current_app.config["OPENSTACK_TIMEOUT"])
        client.authenticate()
        flash(f"Connection to {cfg['name']} succeeded", "success")
    except OpenStackError as exc:
        flash(f"Connection to {cfg['name']} failed: {exc}", "error")

    return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))
