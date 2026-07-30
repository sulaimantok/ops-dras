from app import db
from tests.conftest import csrf_token


def test_health_and_readiness_are_public(client):
    health = client.get("/healthz").get_json()
    assert health == {"status": "ok", "version": "0.1.0"}
    readiness = client.get("/readyz").get_json()
    assert readiness["database"] == "ok"
    assert readiness["version"] == "0.1.0"


def test_authenticated_pages_render(client):
    token = csrf_token(client)
    client.post("/login", data={"username": "admin", "password": "test-password", "csrf_token": token})
    assert client.get("/dashboard").status_code == 200
    assert client.get("/backups?status=queued&q=volume").status_code == 200
    assert client.get("/volumes").status_code == 200
    assert client.get("/clusters").status_code == 200
    assert client.get("/admin").status_code == 200


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
