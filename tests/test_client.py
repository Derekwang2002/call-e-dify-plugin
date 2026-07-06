import pytest

from utils.client import (
    build_create_payload,
    mask_phone,
    normalize_base_url,
    parse_json_object,
    validate_e164,
)


def test_normalize_base_url_strips_v1_suffix():
    assert normalize_base_url("https://api.example.com/v1") == "https://api.example.com"
    assert normalize_base_url("https://api.example.com/") == "https://api.example.com"


def test_validate_e164_accepts_valid_number():
    assert validate_e164("+15555550123") == "+15555550123"


def test_validate_e164_rejects_local_number():
    with pytest.raises(ValueError):
        validate_e164("555-0101")


def test_mask_phone_hides_middle_digits():
    assert mask_phone("+15555550123") == "+15****23"


def test_parse_json_object_requires_object():
    assert parse_json_object('{"lead_id":"lead_1"}', field_name="metadata_json") == {
        "lead_id": "lead_1"
    }
    with pytest.raises(ValueError):
        parse_json_object("[1, 2]", field_name="metadata_json")


def test_build_create_payload_adds_source_metadata():
    payload = build_create_payload(
        phone_number="+15555550123",
        task="Call an authorized test number.",
        region="US",
        locale="en-US",
        metadata={"lead_id": "lead_1"},
    )
    assert payload["recipients"][0]["phones"] == ["+15555550123"]
    assert payload["metadata"]["lead_id"] == "lead_1"
    assert payload["metadata"]["source"] == "dify_call_e_plugin"
