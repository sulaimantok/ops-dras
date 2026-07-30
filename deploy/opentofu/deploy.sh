#!/usr/bin/env bash
# Sync the ops-dras app source to the test VM (provisioned via `tofu apply`
# in this directory) and start it with docker compose.
set -euo pipefail

cd "$(dirname "$0")"

FLOATING_IP=$(tofu output -raw floating_ip 2>/dev/null || terraform output -raw floating_ip)
APP_DIR="../../"   # ops-dras project root, relative to this script
REMOTE_DIR="/home/ubuntu/ops-dras"

if [ ! -f "${APP_DIR}/docker-compose.yml" ]; then
  echo "docker-compose.yml not found at ${APP_DIR} — run this from deploy/opentofu/ inside the ops-dras repo." >&2
  exit 1
fi

if [ ! -f "${APP_DIR}/.env" ]; then
  echo "No .env found in ${APP_DIR} — copying .env.example. Edit cluster credentials before relying on backup/restore." >&2
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

echo "Waiting for cloud-init to finish provisioning (Docker install) on ${FLOATING_IP} ..."
ssh -t -o StrictHostKeyChecking=accept-new "ubuntu@${FLOATING_IP}" "cloud-init status --wait"

echo "Syncing ops-dras source to ubuntu@${FLOATING_IP}:${REMOTE_DIR} ..."
rsync -az --delete \
  --exclude ".git" \
  --exclude "data/" \
  --exclude "backups/" \
  --exclude "deploy/opentofu/.terraform" \
  --exclude "deploy/opentofu/terraform.tfstate*" \
  "${APP_DIR}/" "ubuntu@${FLOATING_IP}:${REMOTE_DIR}/"

echo "Starting docker compose on the test VM ..."
ssh "ubuntu@${FLOATING_IP}" "cd ${REMOTE_DIR} && docker compose up -d --build"

echo
echo "Done. Open: http://${FLOATING_IP}:8080"
