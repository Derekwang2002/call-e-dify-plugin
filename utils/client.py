from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import requests


DEFAULT_BASE_URL = "https://api.heycall-e.com"
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
PLACEHOLDER_PHONES = {"+15555550101", "+15555550102", "+14155550123"}
TERMINAL_STATUSES = {
    "completed",
    "failed",
    "canceled",
    "cancelled",
    "no_answer",
    "declined",
    "voicemail",
    "busy",
    "expired",
}


class CalleApiError(Exception):
    pass


def normalize_base_url(value: Any) -> str:
    base_url = str(value or DEFAULT_BASE_URL).strip().rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3].rstrip("/")
    return base_url or DEFAULT_BASE_URL


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_json_object(value: Any, *, field_name: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{field_name} must be a valid JSON object string.") from error
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"{field_name} must be a JSON object.")


def mask_phone(phone: Any) -> str:
    value = str(phone or "").strip()
    if not value:
        return ""
    if len(value) <= 5:
        return "****"
    return value[:3] + "****" + value[-2:]


def validate_e164(phone: Any) -> str:
    value = str(phone or "").strip()
    if not E164_RE.match(value):
        raise ValueError("phone_number must be in E.164 format, for example +15555550123.")
    return value


def ensure_live_phone_allowed(phone: str) -> None:
    if phone in PLACEHOLDER_PHONES:
        raise ValueError(
            "Replace the placeholder phone number with a number you own or are explicitly authorized to call."
        )


def redact_phone_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [redact_phone_fields(item) for item in value]
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"phone", "phones"} or "phone_number" in lowered:
                output[key] = [mask_phone(v) for v in item] if isinstance(item, list) else mask_phone(item)
            else:
                output[key] = redact_phone_fields(item)
        return output
    return value


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def latest(values: list[Any]) -> Any:
    return values[-1] if values else None


def result_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["call_completed", "outcome", "summary", "next_action"],
        "properties": {
            "call_completed": {"type": "string", "enum": ["yes", "no", "partial", "unknown"]},
            "outcome": {
                "type": "string",
                "enum": ["completed", "partial", "no_answer", "voicemail", "busy", "failed", "unknown"],
            },
            "summary": {"type": "string"},
            "next_action": {"type": "string", "enum": ["none", "follow_up", "retry_later", "manual_review"]},
            "language_detected": {"type": "string"},
            "participant_response": {"type": "string"},
            "key_points": {"type": "string"},
            "issues": {"type": "string"},
            "audio_or_connection_notes": {"type": "string"},
        },
    }


def build_create_payload(
    *,
    phone_number: str,
    task: str,
    region: str,
    locale: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    schema = result_schema()
    return {
        "task": task,
        "recipients": [
            {
                "phones": [phone_number],
                "region": region or "US",
                "locale": locale or "en-US",
            }
        ],
        "result_schema": schema,
        "recipient_result_schema": schema,
        "metadata": {**metadata, "source": "dify_call_e_plugin"},
    }


def extract_call_id(call: dict[str, Any]) -> str:
    candidates = [
        call.get("id"),
        call.get("call_id"),
        call.get("callId"),
        call.get("uuid"),
        as_object(call.get("data")).get("id"),
        as_object(call.get("data")).get("call_id"),
        as_object(call.get("data")).get("callId"),
        as_object(call.get("call")).get("id"),
        as_object(call.get("result")).get("id"),
    ]
    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    return ""


def parse_call_result(call: dict[str, Any], *, metadata_sent: dict[str, Any] | None = None) -> dict[str, Any]:
    recipient = as_object(latest(as_list(call.get("recipients"))))
    attempts = [as_object(attempt) for attempt in as_list(recipient.get("attempts"))]
    latest_attempt = as_object(latest(attempts))
    transcript_turns = []
    for attempt in attempts:
        transcript_turns.extend(as_list(attempt.get("transcript_turns")))

    structured_result = as_object(recipient.get("structured_result")) or as_object(call.get("structured_result"))
    raw_failure_code = latest_attempt.get("failure_code") or call.get("failure_code")
    failure_code = normalize_status(raw_failure_code)
    call_status = call.get("status")
    recipient_status = recipient.get("status")
    latest_attempt_status = latest_attempt.get("status")
    failed_statuses = {"failed", "canceled", "cancelled", "no_answer", "declined", "busy", "expired"}
    failed = (
        normalize_status(call_status) in failed_statuses
        or normalize_status(recipient_status) in failed_statuses
        or normalize_status(latest_attempt_status) in failed_statuses
    )
    answered = latest_attempt_status == "completed" or recipient_status == "completed"
    metadata_returned = as_object(call.get("metadata"))
    metadata_sent = metadata_sent or {}
    metadata_keys = sorted(set(metadata_sent.keys()) | {"lead_id", "notion_page_id", "company", "property", "campaign"})
    missing_or_different = [key for key in metadata_keys if metadata_sent.get(key) != metadata_returned.get(key)]

    return {
        "call_id": extract_call_id(call),
        "call_status": call_status,
        "recipient_status": recipient_status,
        "latest_attempt_status": latest_attempt_status,
        "failure_code": raw_failure_code,
        "failure_message": latest_attempt.get("failure_message") or call.get("failure_message"),
        "answered": answered,
        "no_answer": failure_code == "no_answer",
        "busy": failure_code == "busy",
        "failed": failed,
        "metadata_returned": metadata_returned,
        "metadata_round_trip": {
            "requested_keys": metadata_keys,
            "all_requested_keys_returned": len(missing_or_different) == 0,
            "missing_or_different_keys": missing_or_different,
        },
        "summary": structured_result.get("summary")
        or recipient.get("summary")
        or call.get("summary")
        or latest_attempt.get("summary"),
        "transcript": redact_phone_fields(transcript_turns),
        "structured_result": structured_result,
        "task_completed": call.get("task_completed"),
        "completion_confidence": call.get("completion_confidence"),
        "evidence": as_list(call.get("evidence")),
        "raw_call_result": redact_phone_fields(call),
    }


class CalleClient:
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = str(api_key or "").strip()
        self.base_url = normalize_base_url(base_url)
        if not self.api_key:
            raise CalleApiError("CALL-E API key is required.")

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as error:
            raise CalleApiError(f"CALL-E API request failed: {error}") from error

        if response.status_code < 200 or response.status_code >= 300:
            text = response.text[:1000]
            raise CalleApiError(f"CALL-E API request failed: HTTP {response.status_code}: {text}")

        if not response.text:
            return {}
        try:
            payload = response.json()
        except ValueError as error:
            raise CalleApiError("CALL-E API returned non-JSON response.") from error
        return payload if isinstance(payload, dict) else {"data": payload}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", timeout=10)

    def create_call(self, payload: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/v1/calls"
        try:
            response = requests.post(
                url,
                headers=self._headers(idempotency_key=idempotency_key),
                json=payload,
                timeout=60,
            )
        except requests.RequestException as error:
            raise CalleApiError(f"CALL-E create call request failed: {error}") from error

        if response.status_code < 200 or response.status_code >= 300:
            raise CalleApiError(f"CALL-E create call failed: HTTP {response.status_code}: {response.text[:1000]}")
        try:
            body = response.json()
        except ValueError as error:
            raise CalleApiError("CALL-E create call returned non-JSON response.") from error
        return body if isinstance(body, dict) else {"data": body}

    def get_call(self, call_id: str) -> dict[str, Any]:
        call_id = str(call_id or "").strip()
        if not call_id:
            raise CalleApiError("call_id is required.")
        return self._request("GET", f"/v1/calls/{call_id}", timeout=60)

    def create_and_wait(
        self,
        payload: dict[str, Any],
        *,
        poll_interval_seconds: int,
        wait_timeout_seconds: int,
        idempotency_key: str | None = None,
    ) -> tuple[dict[str, Any], int, bool]:
        call = self.create_call(payload, idempotency_key=idempotency_key)
        call_id = extract_call_id(call)
        if not call_id:
            raise CalleApiError("CALL-E create response did not include a recognized call ID.")

        poll_count = 0
        started = time.monotonic()
        latest_call = call

        while normalize_status(latest_call.get("status")) not in TERMINAL_STATUSES:
            if time.monotonic() - started >= wait_timeout_seconds:
                latest_call = dict(latest_call)
                latest_call["_dify_poll_timeout"] = True
                return latest_call, poll_count, True
            time.sleep(max(1, poll_interval_seconds))
            poll_count += 1
            latest_call = self.get_call(call_id)

        return latest_call, poll_count, False


def new_idempotency_key(prefix: str = "dify") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
