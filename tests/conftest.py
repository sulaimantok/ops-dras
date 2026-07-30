import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from cryptography.fernet import Fernet


@pytest.fixture()
def app(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic = AlembicConfig("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic, "head")

    from app import create_app
    from config import Config

    class TestConfig(Config):
        TESTING = True
        DATABASE_URL = database_url
        SECRET_KEY = "test-secret"
        CLUSTER_CREDENTIALS_KEY = Fernet.generate_key().decode()
        SESSION_COOKIE_SECURE = False
        DEFAULT_ADMIN_USERNAME = "admin"
        DEFAULT_ADMIN_PASSWORD = "test-password"
        LOGIN_RATE_LIMIT_ATTEMPTS = 3
        LOGIN_RATE_LIMIT_WINDOW = 300

    return create_app(TestConfig)


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_token(client, path="/login"):
    response = client.get(path)
    marker = b'name="csrf_token" value="'
    return response.data.split(marker, 1)[1].split(b'"', 1)[0].decode()
