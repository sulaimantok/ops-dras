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

Cluster credentials are **not** configured via environment variables —
everything is entered directly from the UI (Clusters page) and stored in
local SQLite.

## 2. Requirements

Minimum specs to run **ops-dras itself** (not the OpenStack clusters it
manages — see section 3 for that). The app is lightweight (Flask +
gunicorn + SQLite, no external database/broker), so the footprint is small:

| | Minimum | Recommended |
|---|---|---|
| vCPU | 1 | 2 |
| RAM | 512 MB | 2 GB |
| Disk | 2 GB free | 10 GB free |
| OS | Linux with Docker Engine 24+ (or macOS/Windows with Docker Desktop) | same |
| Architecture | x86_64 (amd64) or arm64 | same |
| Network | Outbound HTTPS to Keystone (`:5000`) and each registered cluster's public Cinder endpoint; inbound to the app's port (`8080` by default) | same |

Note: disk only needs to fit the container image (~150–200 MB) plus the
SQLite file (small — just users/cluster config/task history, not the
backup data itself, since ops-dras never moves backup bytes, only
metadata).

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
# edit .env: at minimum change SECRET_KEY and DEFAULT_ADMIN_PASSWORD.
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
   `success`, pick a destination cluster from the dropdown and click
   **Restore**.

The SQLite database persists at `./data/ops-dras.sqlite3` on the host via
the bind mount in `docker-compose.yml`.

**Running without Docker (development):**
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python wsgi.py
```
