from typing import Any
from urllib.parse import urlparse

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.client import normalize_base_url


class CallEProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = str(credentials.get("api_key") or "").strip()
        base_url = normalize_base_url(credentials.get("base_url"))

        if not api_key:
            raise ToolProviderCredentialValidationError("CALL-E API key is required.")

        parsed_base_url = urlparse(base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ToolProviderCredentialValidationError(
                "CALL-E API base URL must be an HTTP(S) URL."
            )
