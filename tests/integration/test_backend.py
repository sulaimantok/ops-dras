from unittest.mock import patch

from app import db
from app.version import __version__
from tests.conftest import csrf_token


def test_health_and_readiness_are_public(client):
    health = client.get("/healthz").get_json()
    assert health == {"status": "ok", "version": __version__}
    readiness = client.get("/readyz").get_json()
    assert readiness["database"] == "ok"
    assert readiness["version"] == __version__


def test_authenticated_pages_render(client):
    token = csrf_token(client)
    client.post("/login", data={"username": "admin", "password": "test-password", "csrf_token": token})
    assert client.get("/dashboard").status_code == 200
    assert client.get("/backups?status=queued&q=volume").status_code == 200
    assert client.get("/volumes").status_code == 200
    assert client.get("/clusters").status_code == 200
    assert client.get("/admin").status_code == 200
    assert client.get("/protection").status_code == 200


@patch("app.routes.protection.OpenStackClient")
def test_protection_hides_backups_deleted_from_cinder(openstack_client, client):
    token = csrf_token(client)
    client.post("/login", data={"username": "admin", "password": "test-password", "csrf_token": token})
    with client.application.app_context():
        cluster_id = db.create_cluster(
            name="source", auth_url="https://keystone.example/v3", auth_method="password",
            username="user", password="secret", project_name="project", project_id="",
            user_domain="Default", project_domain="Default", region="RegionOne", verify_ssl=True,
        )
        task_id, _ = db.create_task("backup", volume_id="vol-1", source_cluster_id=cluster_id)
        db.update_task(task_id, source_backup_id="deleted-backup", status="succeeded")

    from app.services.openstack import OpenStackError
    openstack_client.return_value.get_backup.side_effect = OpenStackError("not found", http_status=404)

    response = client.get("/protection")

    assert response.status_code == 200
    assert b"deleted-backup" not in response.data


@patch("app.routes.protection.OpenStackClient")
def test_protection_filters_available_recovery_points(openstack_client, client):
    token = csrf_token(client)
    client.post("/login", data={"username": "admin", "password": "test-password", "csrf_token": token})
    with client.application.app_context():
        cluster_id = db.create_cluster(
            name="source", auth_url="https://keystone.example/v3", auth_method="password",
            username="user", password="secret", project_name="project", project_id="",
            user_domain="Default", project_domain="Default", region="RegionOne", verify_ssl=True,
        )
        for name in ("database", "webserver"):
            task_id, _ = db.create_task("backup", volume_id=f"vol-{name}", volume_name=name, source_cluster_id=cluster_id)
            db.update_task(task_id, source_backup_id=f"backup-{name}", status="succeeded")
    openstack_client.return_value.get_backup.return_value = {"status": "available"}

    response = client.get("/protection?recovery_q=database")

    assert b"database" in response.data
    assert b"webserver" not in response.data


def test_admin_can_create_operator(client):
    token = csrf_token(client)
    client.post("/login", data={"username": "admin", "password": "test-password", "csrf_token": token})
    token = csrf_token(client, "/admin")
    response = client.post(
        "/admin/users",
        data={"username": "operator", "password": "long-test-password", "role": "operator", "csrf_token": token},
    )
    assert response.status_code == 302
    with client.application.app_context():
        assert db.get_user_by_username("operator")["role"] == "operator"


def test_login_requires_csrf_and_sets_role(client):
    assert client.post("/login", data={"username": "admin", "password": "test-password"}).status_code == 400
    token = csrf_token(client)
    response = client.post(
        "/login", data={"username": "admin", "password": "test-password", "csrf_token": token}
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["role"] == "admin"


def test_persistent_queue_claim_and_idempotency(app):
    with app.app_context():
        first_id, created = db.create_task(
            "backup", volume_id="vol-1", source_cluster_id=None,
            idempotency_key="backup:1:vol-1",
        )
        duplicate_id, duplicate_created = db.create_task(
            "backup", volume_id="vol-1", source_cluster_id=None,
            idempotency_key="backup:1:vol-1",
        )
        assert created is True
        assert duplicate_created is False
        assert duplicate_id == first_id

        claimed = db.claim_next_task()
        assert claimed["id"] == first_id
        assert claimed["status"] == "running"
        assert claimed["attempts"] == 1


def test_backup_mode_is_persisted(app):
    with app.app_context():
        task_id, created = db.create_task(
            "backup", volume_id="vol-incremental", source_cluster_id=None,
            backup_mode="automatic", idempotency_key="backup:1:vol-incremental",
        )

        assert created is True
        task = db.get_task(task_id)
        assert task["backup_mode"] == "automatic"
        assert task["is_incremental"] is None
        assert task["parent_backup_id"] is None


def test_login_rate_limit_is_persisted(client):
    for _ in range(3):
        token = csrf_token(client)
        response = client.post(
            "/login", data={"username": "admin", "password": "wrong", "csrf_token": token}
        )
        assert response.status_code == 200
    token = csrf_token(client)
    response = client.post(
        "/login", data={"username": "admin", "password": "wrong", "csrf_token": token}
    )
    assert response.status_code == 429
