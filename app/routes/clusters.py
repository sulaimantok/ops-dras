from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session

from app import db
from app.auth_utils import login_required, roles_required
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


def _validate_cluster_fields(fields, existing=None):
    errors = []
    if not fields.get("name") or len(fields["name"]) > 120:
        errors.append("Cluster name is required and must be 120 characters or fewer")

    parsed = urlparse(fields.get("auth_url", ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("Auth URL must be a complete HTTP or HTTPS URL")
    elif len(fields["auth_url"]) > 2048:
        errors.append("Auth URL is too long")
    elif current_app.config["REQUIRE_HTTPS_AUTH_URL"] and parsed.scheme != "https":
        errors.append("Auth URL must use HTTPS in production mode")
    elif not parsed.path.rstrip("/").endswith("/v3"):
        errors.append("Auth URL must point to the Keystone v3 endpoint")

    if fields["auth_method"] == "password":
        if not fields.get("username"):
            errors.append("Username is required for password authentication")
        if not fields.get("project_id") and not fields.get("project_name"):
            errors.append("Project ID or Project Name is required for password authentication")
        current_secret = existing and existing.get("auth_method") == "password" and existing.get("password")
        if not fields.get("password") and not current_secret:
            errors.append("Password is required for password authentication")
    else:
        if not fields.get("app_cred_id"):
            errors.append("Application Credential ID is required")
        current_secret = existing and existing.get("auth_method") == "application_credential" and existing.get("app_cred_secret")
        if not fields.get("app_cred_secret") and not current_secret:
            errors.append("Application Credential Secret is required")
    return errors


@bp.route("/clusters")
@login_required
def list_clusters():
    clusters = db.list_clusters()
    return render_template("clusters.html", clusters=clusters)


@bp.route("/clusters", methods=["POST"])
@roles_required("admin")
def create_cluster():
    fields = _fields_from_form(existing=None)
    errors = _validate_cluster_fields(fields)
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("clusters.list_clusters"))

    try:
        cluster_id = db.create_cluster(**fields)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("clusters.list_clusters"))
    flash(f"Cluster '{fields['name']}' added", "success")
    db.create_audit_log(session.get("username"), "cluster.created", "cluster", cluster_id, fields["name"], request.remote_addr)
    return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))


@bp.route("/clusters/<int:cluster_id>", methods=["POST"])
@roles_required("admin")
def update_cluster(cluster_id):
    existing = db.get_cluster(cluster_id)
    if not existing:
        flash("Cluster not found", "error")
        return redirect(url_for("clusters.list_clusters"))

    fields = _fields_from_form(existing=existing)
    errors = _validate_cluster_fields(fields, existing)
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))

    try:
        db.update_cluster(cluster_id, **fields)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))
    flash(f"Cluster '{fields.get('name', existing['name'])}' saved", "success")
    db.create_audit_log(session.get("username"), "cluster.updated", "cluster", cluster_id, fields.get("name"), request.remote_addr)
    return redirect(url_for("clusters.list_clusters", _anchor=f"cluster-{cluster_id}"))


@bp.route("/clusters/<int:cluster_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_cluster(cluster_id):
    existing = db.get_cluster(cluster_id)
    if existing:
        if db.has_active_tasks_for_cluster(cluster_id):
            flash("Cluster cannot be deleted while it is used by an active task", "error")
            return redirect(url_for("clusters.list_clusters"))
        db.delete_cluster(cluster_id)
        db.create_audit_log(session.get("username"), "cluster.deleted", "cluster", cluster_id, existing["name"], request.remote_addr)
        flash(f"Cluster '{existing['name']}' deleted", "success")
    return redirect(url_for("clusters.list_clusters"))


@bp.route("/clusters/<int:cluster_id>/test", methods=["POST"])
@roles_required("admin", "operator")
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
