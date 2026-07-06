from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative_path: str):
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def test_plugin_author_is_lowercase_and_consistent():
    manifest = load_yaml("manifest.yaml")
    provider = load_yaml("provider/call_e.yaml")
    tool_paths = provider["tools"]

    author = manifest["author"]
    assert author == author.lower()
    assert provider["identity"]["author"] == author

    for tool_path in tool_paths:
        tool = load_yaml(tool_path)
        assert tool["identity"]["author"] == author
