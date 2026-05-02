"""Tests for .env read/write."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_free.env import read_env_key, resolve_api_key, write_env_key


@pytest.fixture
def envfile(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text(
        'NVIDIA_NIM_API_KEY="nvapi-test-123"\n'
        "MODEL_OPUS=\"nvidia_nim/foo/bar\"\n"
        "PLAIN=hello\n"
        "QUOTED='single-quoted'\n"
        "WITH_COMMENT=value  # this is a comment\n",
        encoding="utf-8",
    )
    return p


class TestReadEnvKey:
    def test_double_quoted(self, envfile):
        assert read_env_key(envfile, "NVIDIA_NIM_API_KEY") == "nvapi-test-123"

    def test_unquoted(self, envfile):
        assert read_env_key(envfile, "PLAIN") == "hello"

    def test_single_quoted(self, envfile):
        assert read_env_key(envfile, "QUOTED") == "single-quoted"

    def test_strips_trailing_comment(self, envfile):
        assert read_env_key(envfile, "WITH_COMMENT") == "value"

    def test_missing_key_returns_none(self, envfile):
        assert read_env_key(envfile, "NOT_THERE") is None

    def test_missing_file_returns_none(self, tmp_path):
        assert read_env_key(tmp_path / "nope.env", "ANY") is None


class TestWriteEnvKey:
    def test_replaces_existing_key(self, envfile):
        write_env_key(envfile, "MODEL_OPUS", "nvidia_nim/qwen/qwen3-coder-480b")
        assert read_env_key(envfile, "MODEL_OPUS") == "nvidia_nim/qwen/qwen3-coder-480b"

    def test_preserves_other_keys(self, envfile):
        write_env_key(envfile, "MODEL_OPUS", "x/y")
        assert read_env_key(envfile, "NVIDIA_NIM_API_KEY") == "nvapi-test-123"
        assert read_env_key(envfile, "PLAIN") == "hello"

    def test_appends_new_key(self, envfile):
        write_env_key(envfile, "MODEL_NEW", "nvidia_nim/new/model")
        assert read_env_key(envfile, "MODEL_NEW") == "nvidia_nim/new/model"

    def test_creates_file_if_missing(self, tmp_path):
        p = tmp_path / "fresh.env"
        write_env_key(p, "FOO", "bar")
        assert read_env_key(p, "FOO") == "bar"

    def test_value_with_special_chars_round_trips(self, envfile):
        # The free-claude-code .env uses simple double-quoting; we don't
        # need to escape internal quotes (that pattern doesn't show up
        # in real model ids).
        write_env_key(envfile, "MODEL_OPUS", "nvidia_nim/some/model-with.dots")
        assert read_env_key(envfile, "MODEL_OPUS") == "nvidia_nim/some/model-with.dots"


class TestResolveApiKey:
    def test_nvidia_from_env_var(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-from-env")
        assert resolve_api_key("nvidia-nim") == "nvapi-from-env"

    def test_nvidia_falls_back_to_secondary_env_var(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secondary")
        assert resolve_api_key("nvidia-nim") == "nvapi-secondary"

    def test_openrouter_from_env_var(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
        assert resolve_api_key("openrouter") == "sk-or-v1-test"

    def test_unknown_provider_returns_none(self, monkeypatch):
        # Defensive — caller should handle but resolve shouldn't blow up.
        assert resolve_api_key("not-a-real-provider") is None
