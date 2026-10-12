from unittest.mock import Mock, patch

import pytest
import requests

from app.services.openstack import OpenStackClient, OpenStackError


def config():
    return {
        "name": "cluster-a", "auth_url": "https://keystone.example/v3",
        "auth_method": "password", "username": "user", "password": "secret",
        "app_cred_id": "", "app_cred_secret": "", "project_name": "project",
        "project_id": "project-id", "user_domain": "Default",
        "project_domain": "Default", "region": "RegionOne", "verify_ssl": True,
    }


@patch("app.services.openstack.requests.post")
def test_keystone_network_error_is_retryable(post):
    post.side_effect = requests.Timeout("timed out")
    with pytest.raises(OpenStackError) as error:
        OpenStackClient(config()).authenticate()
    assert error.value.code == "keystone_network"
    assert error.value.retryable is True


@patch("app.services.openstack.requests.request")
def test_cinder_503_is_structured_and_retryable(request):
    response = Mock(status_code=503, text="unavailable")
    request.return_value = response
    client = OpenStackClient(config())
    client._token = "token"
    client._cinder_endpoint = "https://cinder.example/v3/project-id"
    with pytest.raises(OpenStackError) as error:
        client.list_volumes()
    assert error.value.http_status == 503
    assert error.value.code == "cinder_http"
    assert error.value.retryable is True


@patch("app.services.openstack.requests.request")
def test_create_incremental_backup_sends_incremental_flag(request):
    response = Mock(status_code=202, text="")
    response.json.return_value = {"backup": {"id": "backup-1"}}
    response.url = "https://cinder.example/v3/project-id/backups"
    request.return_value = response
    client = OpenStackClient(config())
    client._token = "token"
    client._cinder_endpoint = "https://cinder.example/v3/project-id"

    result = client.create_backup("volume-1", incremental=True)

    assert result["id"] == "backup-1"
    assert request.call_args.kwargs["json"]["backup"]["incremental"] is True


@patch("app.services.openstack.requests.request")
@patch("app.services.openstack.requests.post")
def test_inspect_connection_returns_detailed_metadata(post, request):
    auth_resp = Mock(status_code=201)
    auth_resp.headers = {"X-Subject-Token": "test-token"}
    auth_resp.json.return_value = {
        "token": {
            "project": {"id": "proj-123", "name": "production"},
            "user": {"id": "user-456", "name": "admin-user"},
            "expires_at": "2026-10-12T18:00:00Z",
            "catalog": [
                {
                    "type": "block-storage",
                    "endpoints": [{"interface": "public", "url": "https://cinder.example/v3", "region": "RegionOne"}],
                }
            ],
        }
    }
    auth_resp.url = "https://keystone.example/v3/auth/tokens"
    post.return_value = auth_resp

    cinder_resp = Mock(status_code=200)
    cinder_resp.json.return_value = {"volumes": []}
    cinder_resp.url = "https://cinder.example/v3/proj-123/volumes?limit=1"
    request.return_value = cinder_resp

    client = OpenStackClient(config())
    details = client.inspect_connection()

    assert details["ok"] is True
    assert details["project_id"] == "proj-123"
    assert details["project_name"] == "production"
    assert details["cinder_endpoint"] == "https://cinder.example/v3"
    assert "block-storage" in details["catalog_services"]
    assert details["latency_ms"] >= 1
