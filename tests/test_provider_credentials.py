import pytest

from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider import call_e
from provider.call_e import CallEProvider
from utils.client import CalleApiError


def test_validate_credentials_uses_non_mutating_call_probe(monkeypatch):
    called = {}

    def fake_validate_credentials(self):
        called["api_key"] = self.api_key
        called["base_url"] = self.base_url
        return {"authenticated": True}

    monkeypatch.setattr(call_e.CalleClient, "validate_credentials", fake_validate_credentials)

    CallEProvider()._validate_credentials(
        {
            "api_key": "test_key",
            "base_url": "https://api.heycall-e.com",
        }
    )

    assert called == {
        "api_key": "test_key",
        "base_url": "https://api.heycall-e.com",
    }


def test_validate_credentials_requires_api_key():
    with pytest.raises(ToolProviderCredentialValidationError):
        CallEProvider()._validate_credentials(
            {
                "api_key": "",
                "base_url": "https://api.heycall-e.com",
            }
        )


def test_validate_credentials_wraps_call_e_api_errors(monkeypatch):
    def fake_validate_credentials(self):
        raise CalleApiError("CALL-E API key is invalid or missing.")

    monkeypatch.setattr(call_e.CalleClient, "validate_credentials", fake_validate_credentials)

    with pytest.raises(
        ToolProviderCredentialValidationError,
        match="CALL-E API key is invalid or missing",
    ):
        CallEProvider()._validate_credentials(
            {
                "api_key": "bad_key",
                "base_url": "https://api.heycall-e.com",
            }
        )
