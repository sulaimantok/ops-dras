import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "data", "ops-dras.sqlite3"))

    DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")

    # Cluster-A/B connection details are intentionally NOT read from
    # environment variables. They live only in the cluster_config SQLite
    # table and are entered/edited at runtime from the app's Settings page.

    OPENSTACK_TIMEOUT = int(os.environ.get("OPENSTACK_TIMEOUT", "30"))
    BACKUP_POLL_INTERVAL = int(os.environ.get("BACKUP_POLL_INTERVAL", "5"))
    BACKUP_POLL_TIMEOUT = int(os.environ.get("BACKUP_POLL_TIMEOUT", "1800"))
