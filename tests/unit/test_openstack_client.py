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
