import pytest

from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.call_e import CallEProvider
from utils import client


def test_validate_credentials_does_not_call_network(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("credential validation must not call network health checks")

    monkeypatch.setattr(client.CalleClient, "health", fail_if_called)

    CallEProvider()._validate_credentials(
        {
            "api_key": "test_key",
            "base_url": "https://api.heycall-e.com",
        }
    )


def test_validate_credentials_requires_api_key():
    with pytest.raises(ToolProviderCredentialValidationError):
        CallEProvider()._validate_credentials(
            {
                "api_key": "",
                "base_url": "https://api.heycall-e.com",
            }
        )
