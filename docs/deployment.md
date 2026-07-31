# Deployment and Operations

## Run with Docker Compose

```bash
cp .env.example .env
# Set SECRET_KEY, DEFAULT_ADMIN_PASSWORD, CLUSTER_CREDENTIALS_KEY,
# and POSTGRES_PASSWORD in .env.
docker compose up --build
```

The application runs Alembic migrations before Gunicorn starts. The Compose
stack contains PostgreSQL, the web service, and a persistent queue worker.

## Health checks

- `GET /healthz` reports that the web process is alive.
- `GET /readyz` verifies database connectivity and returns HTTP 503 when the
  application is not ready.

## PostgreSQL backups

```bash
scripts/backup_postgres.sh $OPS_DRAS_DIR
```

The default destination is `$OPS_DRAS_DIR/backups` with 14-day retention.
Protect database dumps together with `.env`; both are required to decrypt
cluster credentials.

## Private OpenStack CA (temporary injection)

Installing an internal CA on the Docker host does not automatically update the
Python `certifi` bundle inside existing containers. Use a generic CA file path:

```bash
OPENSTACK_CA_FILE=/absolute/path/to/openstack-private-ca.crt
docker compose cp "$OPENSTACK_CA_FILE" ops-dras:/tmp/openstack-private-ca.crt
docker compose exec -T ops-dras sh -c \
  'cat /tmp/openstack-private-ca.crt >> "$(python -m certifi)"'
docker compose cp "$OPENSTACK_CA_FILE" worker:/tmp/openstack-private-ca.crt
docker compose exec -T worker sh -c \
  'cat /tmp/openstack-private-ca.crt >> "$(python -m certifi)"'
```

Reload web workers and recreate the worker from a temporary image:

```bash
docker compose exec -T ops-dras python -c \
  'import os, signal; os.kill(1, signal.SIGHUP)'
worker_id=$(docker compose ps -q worker)
docker commit "$worker_id" ops-dras-worker:latest
docker compose up -d --force-recreate --no-build worker
```

Verify against your own Keystone URL:

```bash
OPENSTACK_IDENTITY_URL=https://identity.example.internal/v3
docker compose exec -T ops-dras python -c \
  "import requests; print(requests.get('$OPENSTACK_IDENTITY_URL', timeout=15).status_code)"
```

This temporary injection is lost after image rebuild. A permanent CA mount or
image-build integration is preferred for production.

## SQLite migration

Legacy SQLite installations can be migrated to PostgreSQL:

```bash
alembic upgrade head
python scripts/migrate_sqlite_to_postgres.py \
  --source sqlite:////absolute/path/to/ops-dras.sqlite3 \
  --target "$DATABASE_URL"
```

Back up the SQLite file first and verify users, clusters, and task history
before retiring it.
