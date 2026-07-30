# ops-dras

## 1. About the Application

**ops-dras** (OpenStack Disaster Recovery as a Service) is a web app for
managing Cinder volume disaster recovery on OpenStack. From a single
portal, an operator can:

1. Register **any number of OpenStack clusters** (not limited to a fixed
   source/destination pair) from the **Clusters** page — each cluster can
   authenticate with either Username & Password or an **Application
   Credential**.
2. Pick a cluster, browse its Cinder volumes, and trigger a **backup**
   (forced) on any volume.
3. **Restore** that backup onto **any registered cluster** (including the
   same cluster) — chosen at restore time, not hardcoded. For cross-cluster
   restores, ops-dras automatically orchestrates Cinder's `export_record` →
   `import_record` → `restore` flow in the background, so the UI never
   blocks waiting for it to finish.

Cluster credentials are **not** configured via environment variables.
Everything is entered from the **Clusters** page and stored encrypted in
PostgreSQL using the Fernet key supplied through `CLUSTER_CREDENTIALS_KEY`.

## 2. Requirements

These specifications cover the complete ops-dras stack: the Flask/Gunicorn
web service, persistent queue worker, and PostgreSQL 16 database. They do not
include the OpenStack clusters or Cinder backup storage managed by ops-dras.

| | Minimum | Recommended |
|---|---|---|
| vCPU | 2 | 4 |
| RAM | 2 GB | 4 GB |
| Disk | 10 GB free | 20 GB+ free |
| OS | Linux with Docker Engine 24+ (or macOS/Windows with Docker Desktop) | same |
| Architecture | x86_64 (amd64) or arm64 | same |
| Network | Outbound HTTPS to each registered Keystone and Cinder endpoint; inbound to port `8080` or a TLS reverse proxy | Restrict inbound access to trusted CIDRs and expose the application through HTTPS |

Disk is used by container images, PostgreSQL data, task/audit history, and
scheduled database dumps. ops-dras does not copy Cinder backup payloads, so
actual volume-backup data remains in the configured Cinder backup backend.
The default PostgreSQL directory is `/opt/data/ops-dras-postgres`, while the
documented backup job writes compressed dumps under
`$OPS_DRAS_DIR/backups`. Monitor both locations and increase disk
capacity according to retention and task-history growth.

## 3. OpenStack Cluster Requirements

ops-dras only orchestrates existing Cinder APIs — the OpenStack cluster(s)
themselves must already be:

- **Running** and reachable (Keystone + Cinder public endpoint reachable
  from wherever ops-dras is deployed).
- **Cinder Backup service enabled** (`cinder-backup`), with a backup
  backend already configured (NFS, Ceph, or S3). Without this, the
  `backups`, `export_record`, `import_record`, and `restore` endpoints
  won't be available. *(How to enable it depends on how your OpenStack
  cluster was deployed — kolla-ansible, Kayobe, OpenStack-Ansible, TripleO,
  etc. — so it's not covered here; check your deployment tool's
  documentation for enabling `cinder-backup` and its backend.)*
- For **cross-cluster restores**, the source and destination clusters'
  backup backends must be able to see the same storage (e.g. the same Ceph
  backup pool, or the same S3 bucket/NFS share) — ops-dras only moves the
  metadata pointer, not the backup data itself.
- The user/Application Credential used needs the Cinder volume & backup
  permissions (roles) on the relevant project (`list volumes`,
  `create/get backup`, `export/import backup record`, `restore backup`).

## 4. Running the Application

```bash
cd ops-dras
cp .env.example .env
# edit .env: change SECRET_KEY, DEFAULT_ADMIN_PASSWORD, and set
# CLUSTER_CREDENTIALS_KEY (see .env.example for the generator command).
# OpenStack cluster credentials are NOT set here — add them from the UI.

docker compose up --build
```

Open `http://localhost:8080`, log in with `DEFAULT_ADMIN_USERNAME` /
`DEFAULT_ADMIN_PASSWORD` from `.env` (defaults to `admin` / `change-me` —
**must be changed** before using this outside a lab), then:

1. Go to **Clusters** → add each OpenStack cluster (more than one is fine):
   enter the Auth URL, pick an authentication method (Username & Password
   or Application Credential), then click **Test connection** to confirm
   Keystone/Cinder connectivity.
2. Go to **Volumes** → pick a cluster from the dropdown to browse its
   volumes → click **Backup** on the volume you want to back up.
3. Go to **Backups & Restores** → watch the backup progress. Once it's
   `succeeded`, pick a destination cluster from the dropdown and click
   **Restore**.

Cluster passwords and application-credential secrets are encrypted with
Fernet before being stored in PostgreSQL. The encryption key comes from
`CLUSTER_CREDENTIALS_KEY` in `.env`; credentials are never written to source
files or committed to the repository. Keep database backups and the `.env`
file protected and stored separately, because both are required to decrypt
the credentials.

Docker Compose starts PostgreSQL 16 by default. Its data persists on the
host at `/opt/data/ops-dras-postgres` (change `POSTGRES_DATA_DIR` in `.env`
if needed). The app runs `alembic upgrade head` before Gunicorn starts.

To use an existing PostgreSQL server instead, set `DATABASE_URL` in `.env`:

```bash
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

For Compose, start only the app without its local database dependency:

```bash
docker compose up --no-deps ops-dras
```

The database user must be allowed to create/update the ops-dras schema
through Alembic migrations.

The Compose stack also runs a separate persistent queue worker. Web requests
only enqueue backup/restore jobs in PostgreSQL; the worker claims and executes
them. Interrupted jobs are requeued when the worker restarts, and transient
Keystone/Cinder failures use exponential backoff.

### Health checks

- `GET /healthz` reports that the web process is alive.
- `GET /readyz` verifies database connectivity and returns HTTP 503 when the
  application is not ready to receive traffic.

### Roles and audit log

The initial user is an `admin`. Admins can create users and assign `admin`,
`operator`, or `viewer` roles from the **Admin** page. Operators can run
backups/restores and test cluster connectivity. Viewers have read-only access.
Security-sensitive operations and job results are recorded in the audit log.

### PostgreSQL backups

Run an on-demand compressed backup:

```bash
chmod +x scripts/backup_postgres.sh
scripts/backup_postgres.sh $OPS_DRAS_DIR
```

The default destination is `$OPS_DRAS_DIR/backups`, with 14-day
retention. Set `BACKUP_RETENTION_DAYS` to change it and schedule the command
using cron or a systemd timer. Test restores regularly on a separate database:

```bash
gunzip -c backups/ops-dras-TIMESTAMP.sql.gz | \
  docker compose exec -T postgres psql -U ops_dras -d ops_dras
```

### Production network exposure

Port 8080 is intended for a trusted network or a TLS reverse proxy. For public
deployment, terminate HTTPS with Nginx/Traefik, restrict inbound CIDRs, set
`SESSION_COOKIE_SECURE=1`, and set `REQUIRE_HTTPS_AUTH_URL=1`. Direct HTTP by
IP currently requires `SESSION_COOKIE_SECURE=0`.

### Private OpenStack certificate authorities (temporary injection)

Installing an internal CA on the Docker host does not automatically update the
Python `certifi` bundle inside existing containers. To inject a CA temporarily
without changing Compose, copy and append it to both the web and worker bundle:

```bash
cd $OPS_DRAS_DIR
docker compose cp /usr/local/share/ca-certificates/atmosphere-ca.crt \
  ops-dras:/tmp/atmosphere-ca.crt
docker compose exec -T ops-dras sh -c \
  'cat /tmp/atmosphere-ca.crt >> "$(python -m certifi)"'

docker compose cp /usr/local/share/ca-certificates/atmosphere-ca.crt \
  worker:/tmp/atmosphere-ca.crt
docker compose exec -T worker sh -c \
  'cat /tmp/atmosphere-ca.crt >> "$(python -m certifi)"'
```

Gunicorn can reload its workers without recreating the injected filesystem:

```bash
docker compose exec -T ops-dras python -c \
  'import os, signal; os.kill(1, signal.SIGHUP)'
```

The queue worker has no reload mechanism. Snapshot the injected worker
container and recreate it from that temporary local image so the CA is present
before `worker.py` starts:

```bash
worker_id=$(docker compose ps -q worker)
docker commit "$worker_id" ops-dras-worker:latest
docker compose up -d --force-recreate --no-build worker
```

Verify TLS from each container:

```bash
docker compose exec -T ops-dras python -c \
  'import requests; print(requests.get("https://identity.ops.sd.boer.id/v3", timeout=15).status_code)'
docker compose exec -T worker python -c \
  'import requests; print(requests.get("https://identity.ops.sd.boer.id/v3", timeout=15).status_code)'
```

This injection is lost whenever the application images are rebuilt, so repeat
the injection, Gunicorn reload, and worker snapshot after `docker compose
up --build`.

### Migrating an existing SQLite installation

This section is only for installations upgraded from an earlier ops-dras
version that still stored users, cluster configuration, and task history in
`data/ops-dras.sqlite3`. New installations already use PostgreSQL by default
and do not need this migration. The script performs a one-time copy from the
legacy SQLite database into an empty PostgreSQL schema while preserving IDs
and encrypted credential values.

1. Stop ops-dras and back up `data/ops-dras.sqlite3`.
2. Configure the target `DATABASE_URL` and run `alembic upgrade head`.
3. Copy data once, preserving the old SQLite file as rollback backup:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --source sqlite:////absolute/path/to/ops-dras.sqlite3 \
  --target "$DATABASE_URL"
```

4. Start the app against PostgreSQL and verify users, clusters, and task
   history before retiring the SQLite database.

**Running without Docker (development):**
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL to a reachable development PostgreSQL database.
export DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/ops_dras
set -a && . ./.env && set +a
alembic upgrade head
python wsgi.py
```
