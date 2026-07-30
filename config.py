import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "data", "ops-dras.sqlite3"))
    # PostgreSQL is the supported production backend. DATABASE_URL also
    # accepts sqlite:///... for legacy data migration and local tests.
    DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DATABASE_PATH}"
    # A URL-safe Fernet key used to encrypt OpenStack passwords and
    # application-credential secrets at rest. New credentials cannot be
    # saved until this value is configured.
    CLUSTER_CREDENTIALS_KEY = os.environ.get("CLUSTER_CREDENTIALS_KEY", "")

    DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1").lower() not in {"0", "false", "no"}
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_LIFETIME_HOURS", "8")))

    # OpenStack connection details are intentionally NOT read from environment
    # variables. They are entered at runtime and stored encrypted in the
    # configured application database.

    OPENSTACK_TIMEOUT = int(os.environ.get("OPENSTACK_TIMEOUT", "30"))
    BACKUP_POLL_INTERVAL = int(os.environ.get("BACKUP_POLL_INTERVAL", "5"))
    BACKUP_POLL_TIMEOUT = int(os.environ.get("BACKUP_POLL_TIMEOUT", "1800"))
    TASK_MAX_ATTEMPTS = int(os.environ.get("TASK_MAX_ATTEMPTS", "3"))
    TASK_RETRY_BASE_SECONDS = int(os.environ.get("TASK_RETRY_BASE_SECONDS", "5"))
    WORKER_POLL_INTERVAL = float(os.environ.get("WORKER_POLL_INTERVAL", "2"))
    LOGIN_RATE_LIMIT_ATTEMPTS = int(os.environ.get("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
    LOGIN_RATE_LIMIT_WINDOW = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW", "300"))
    REQUIRE_HTTPS_AUTH_URL = os.environ.get("REQUIRE_HTTPS_AUTH_URL", "0").lower() not in {"0", "false", "no"}
