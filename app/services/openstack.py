"""
Minimal Keystone + Cinder v3 REST client.

Deliberately avoids the heavyweight python-openstackclient / SDK stack and
talks to the Identity and Block Storage HTTP APIs directly with `requests`,
since the app only needs a handful of calls (auth, list volumes, create
backup, export/import record, restore).
"""
import logging
import time

import requests

logger = logging.getLogger(__name__)


class OpenStackError(Exception):
    def __init__(self, message, code="openstack_error", http_status=None, retryable=False):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


class OpenStackClient:
    def __init__(self, cluster_cfg, timeout=30):
        """cluster_cfg is a dict as returned by db.get_cluster()."""
        self.name = cluster_cfg["name"]
        self.auth_url = cluster_cfg["auth_url"].rstrip("/")
        self.auth_method = cluster_cfg.get("auth_method") or "password"
        self.username = cluster_cfg["username"]
        self.password = cluster_cfg["password"]
        self.app_cred_id = cluster_cfg.get("app_cred_id") or ""
        self.app_cred_secret = cluster_cfg.get("app_cred_secret") or ""
        self.project_name = cluster_cfg["project_name"]
        self.project_id = cluster_cfg["project_id"]
        self.user_domain = cluster_cfg["user_domain"] or "Default"
        self.project_domain = cluster_cfg["project_domain"] or "Default"
        self.region = cluster_cfg["region"] or None
        self.verify_ssl = bool(cluster_cfg["verify_ssl"])
        self.timeout = timeout

        self._token = None
        self._cinder_endpoint = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def _build_auth_payload(self):
        if self.auth_method == "application_credential":
            # Application credentials are pre-scoped to a single project on
            # creation, so a "scope" block must NOT be sent alongside them
            # (Keystone rejects the request if it is).
            return {
                "auth": {
                    "identity": {
                        "methods": ["application_credential"],
                        "application_credential": {
                            "id": self.app_cred_id,
                            "secret": self.app_cred_secret,
                        },
                    }
                }
            }

        if self.project_id:
            project_scope = {"id": self.project_id}
        else:
            project_scope = {"name": self.project_name, "domain": {"name": self.project_domain}}

        return {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.username,
                            "domain": {"name": self.user_domain},
                            "password": self.password,
                        }
                    },
                },
                "scope": {"project": project_scope},
            }
        }

    def authenticate(self):
        """Fetch a scoped Keystone token and locate the volumev3 endpoint."""
        url = f"{self.auth_url}/auth/tokens"
        try:
            resp = requests.post(
                url,
                json=self._build_auth_payload(),
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise OpenStackError(
                f"[{self.name}] failed to reach Keystone at {url}: {exc}",
                code="keystone_network", retryable=True,
            ) from exc

        if resp.status_code != 201:
            raise OpenStackError(
                f"[{self.name}] Keystone auth failed ({resp.status_code}) at {url}: {resp.text[:500]}",
                code="keystone_auth", http_status=resp.status_code, retryable=resp.status_code >= 500,
            )

        self._token = resp.headers.get("X-Subject-Token")
        token_data = self._json(resp, url)["token"]

        if not self.project_id:
            # Application credentials (and some password setups) are
            # implicitly scoped; pick up the resulting project id from the
            # token itself instead of requiring it to be typed in Settings.
            self.project_id = (token_data.get("project") or {}).get("id", "")

        catalog = token_data.get("catalog", [])
        self._cinder_endpoint = self._pick_endpoint(catalog)

        if not self._cinder_endpoint:
            raise OpenStackError(
                f"[{self.name}] no volumev3/block-storage endpoint found in catalog"
            )
        return self._token

    def _pick_endpoint(self, catalog):
        # Preference order matters: some clusters keep a stale/legacy
        # "volumev3" catalog entry around alongside the canonical
        # "block-storage" one (e.g. after an upgrade), sometimes pointing at
        # an endpoint that's no longer wired up correctly. keystoneauth1
        # (used by Horizon/Skyline/the openstack CLI) always resolves the
        # volume service via "block-storage" first, falling back to the
        # older aliases — mirror that instead of taking whichever entry
        # happens to appear first in the catalog's JSON order.
        for wanted_type in ("block-storage", "volumev3", "volumev2", "volume"):
            for service in catalog:
                if service.get("type") != wanted_type:
                    continue
                endpoints = service.get("endpoints", [])
                candidates = [e for e in endpoints if e.get("interface") == "public"]
                if self.region:
                    region_matches = [e for e in candidates if e.get("region") == self.region]
                    if region_matches:
                        candidates = region_matches
                if candidates:
                    return candidates[0]["url"].rstrip("/")
        return None

    def _base_url(self):
        """Cinder endpoint scoped with the project id in the path."""
        if not self._cinder_endpoint:
            self.authenticate()
        endpoint = self._cinder_endpoint
        project_id = self.project_id
        if project_id and not endpoint.endswith(project_id):
            endpoint = f"{endpoint}/{project_id}"
        return endpoint

    def _headers(self):
        if not self._token:
            self.authenticate()
        return {"X-Auth-Token": self._token, "Content-Type": "application/json"}

    def _json(self, resp, url):
        try:
            return resp.json()
        except ValueError as exc:
            raise OpenStackError(
                f"[{self.name}] expected JSON from {url} but got: {resp.text[:300]}"
            ) from exc

    def _request(self, method, path, retry_on_401=True, **kwargs):
        url = f"{self._base_url()}{path}"
        try:
            resp = requests.request(
                method, url, headers=self._headers(), timeout=self.timeout,
                verify=self.verify_ssl, **kwargs,
            )
        except requests.RequestException as exc:
            raise OpenStackError(
                f"[{self.name}] {method} {url} failed: {exc}",
                code="cinder_network", retryable=True,
            ) from exc

        if resp.status_code == 401 and retry_on_401:
            self._token = None
            self._cinder_endpoint = None
            return self._request(method, path, retry_on_401=False, **kwargs)
        if resp.status_code >= 400:
            raise OpenStackError(
                f"[{self.name}] {method} {url} -> {resp.status_code}: {resp.text[:500]}",
                code="cinder_http", http_status=resp.status_code,
                retryable=resp.status_code == 429 or resp.status_code >= 500,
            )
        return resp

    # ------------------------------------------------------------------
    # Cinder operations
    # ------------------------------------------------------------------
    def list_volumes(self):
        resp = self._request("GET", "/volumes/detail")
        return self._json(resp, resp.url).get("volumes", [])

    def get_volume(self, volume_id):
        resp = self._request("GET", f"/volumes/{volume_id}")
        return self._json(resp, resp.url).get("volume", {})

    def get_backup(self, backup_id):
        resp = self._request("GET", f"/backups/{backup_id}")
        return self._json(resp, resp.url).get("backup", {})

    def list_backups(self, volume_id=None):
        params = {"volume_id": volume_id} if volume_id else None
        resp = self._request("GET", "/backups/detail", params=params)
        return self._json(resp, resp.url).get("backups", [])

    def create_backup(self, volume_id, name=None, description=None, force=True, incremental=False):
        body = {
            "backup": {
                "volume_id": volume_id,
                "name": name or f"ops-dras-{volume_id[:8]}-{int(time.time())}",
                "description": description or "Created by ops-dras",
                "force": force,
                "incremental": incremental,
            }
        }
        resp = self._request("POST", "/backups", json=body)
        return self._json(resp, resp.url).get("backup", {})

    def wait_for_backup_status(self, backup_id, target_statuses=("available",),
                                fail_statuses=("error", "error_deleting"),
                                interval=5, timeout=1800):
        elapsed = 0
        while elapsed < timeout:
            backup = self.get_backup(backup_id)
            status = backup.get("status")
            if status in target_statuses:
                return backup
            if status in fail_statuses:
                raise OpenStackError(
                    f"[{self.name}] backup {backup_id} entered failure status '{status}'"
                )
            time.sleep(interval)
            elapsed += interval
        raise OpenStackError(
            f"[{self.name}] timed out waiting for backup {backup_id} to reach {target_statuses}"
        )

    def export_record(self, backup_id):
        resp = self._request("GET", f"/backups/{backup_id}/export_record")
        return self._json(resp, resp.url).get("backup-record", {})

    def import_record(self, backup_service, backup_url):
        body = {
            "backup-record": {
                "backup_service": backup_service,
                "backup_url": backup_url,
            }
        }
        resp = self._request("POST", "/backups/import_record", json=body)
        return self._json(resp, resp.url).get("backup", {})

    def restore_backup(self, backup_id, volume_id=None, name=None):
        body = {"restore": {}}
        if volume_id:
            body["restore"]["volume_id"] = volume_id
        if name:
            body["restore"]["name"] = name
        resp = self._request("POST", f"/backups/{backup_id}/restore", json=body)
        return self._json(resp, resp.url).get("restore", {})
