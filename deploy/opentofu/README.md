# Test VM for ops-dras (OpenTofu)

Provisions a single VM in the OpenStack lab dedicated to trying out the
`ops-dras` app, following the lab conventions already in use (see
`.agents/skills/opentofu-openstack-lab`):

- Network: `internal0`
- Flavor: `m1.small`
- Image: `Ubuntu 24.04 ARM64`
- Keypair: `sulaiman`
- Base security group: `sg-learn` (+ a new `sg-ops-dras-test` security group
  dedicated to opening SSH and the app port `8080`)

This VM only provisions Docker + the Docker Compose plugin via cloud-init.
The ops-dras app source is synced separately (see `deploy.sh`) so testing
iterations don't require re-creating the VM every time the source changes.

## Prerequisites

- `tofu` (OpenTofu) or `terraform` CLI installed.
- `~/.config/openstack/clouds.yaml` already has a valid `openstack` entry
  (used by `provider.tf`).
- SSH access to the lab network (the floating IP must be reachable from
  your machine).

## 1. Provision the VM

```bash
cd deploy/opentofu
tofu init
tofu plan
tofu apply
```

Once done, check the outputs:

```bash
tofu output
# floating_ip, internal_ip, ssh_command, app_url
```

## 2. Deploy & run the application

From this folder, run:

```bash
./deploy.sh
```

This script will:
1. Wait for cloud-init to finish provisioning (`cloud-init status --wait`)
   — important so it doesn't race with the Docker install that's still
   running right after `tofu apply` completes.
2. Rsync the entire `ops-dras` source (project root, two levels above this
   folder) to `/home/ubuntu/ops-dras` on the VM (the `ubuntu` user's home
   directory, so no root permissions are needed like `/opt` would require).
3. Copy `.env.example` → `.env` on the VM if it doesn't exist yet (**edit
   `SECRET_KEY`/`DEFAULT_ADMIN_PASSWORD` before using it for real** —
   OpenStack cluster credentials themselves are entered from the app's
   **Clusters** page, not `.env` — see the root [README.md](../../README.md),
   section "Running the Application").
4. Run `docker compose up -d --build` on the VM.

Open `http://<floating_ip>:8080` (see `tofu output app_url`).

To redeploy after changing local code, just run `./deploy.sh` again —
rsync + `docker compose up -d --build` rebuilds the image with the latest
source.

## 3. Tear down

```bash
tofu destroy
```

## Sizing note

This VM uses the `m1.small` flavor per the historical lab default — on
most OpenStack labs that's roughly ±1 vCPU / 2 GB RAM, more than enough for
`docker compose up` with 2 gunicorn workers (see the "Requirements" section
in the root README). If `m1.small` on your lab turns out to be smaller
than 512 MB RAM, bump it via `-var flavor_name=<other_flavor>` when running
`tofu apply`/`tofu plan`.
