from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.client import CalleApiError, CalleClient, normalize_base_url


class CallEProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = str(credentials.get("api_key") or "").strip()
        base_url = normalize_base_url(credentials.get("base_url"))

        if not api_key:
            raise ToolProviderCredentialValidationError("CALL-E API key is required.")

        try:
            CalleClient(api_key=api_key, base_url=base_url).health()
        except CalleApiError as error:
            raise ToolProviderCredentialValidationError(str(error))
        except Exception as error:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate CALL-E credentials: {error}"
            )
