"""Tests for the static BENCHMARKS table and scoring helpers."""

from __future__ import annotations

import math

import pytest

from claude_free.benchmarks import (
    BENCHMARKS,
    CURATED,
    code_score_for,
    combined_score,
)


class TestBenchmarksTable:
    def test_every_curated_model_has_a_benchmark_entry(self):
        """A model in CURATED but not in BENCHMARKS would never score."""
        missing = [m for m in CURATED if m not in BENCHMARKS]
        assert not missing, f"CURATED entries missing from BENCHMARKS: {missing}"

    def test_every_benchmark_entry_has_a_code_score(self):
        for model, data in BENCHMARKS.items():
            assert "code_score" in data, f"{model} missing code_score"
            assert isinstance(data["code_score"], (int, float)), f"{model} code_score not numeric"
            assert 0 <= data["code_score"] <= 100, f"{model} code_score out of [0,100]"

    def test_every_benchmark_entry_has_a_source_tag(self):
        valid = {"swebench", "livecodebench", "humaneval", "estimate"}
        for model, data in BENCHMARKS.items():
            assert data.get("src") in valid, f"{model} src={data.get('src')!r} not in {valid}"

    def test_no_dupes_in_curated(self):
        assert len(CURATED) == len(set(CURATED)), "duplicate entries in CURATED"


class TestCodeScoreFor:
    def test_known_model_returns_dict(self):
        result = code_score_for("deepseek-ai/deepseek-v4-pro")
        assert result is not None
        assert result["score"] == 80.6
        assert result["src"] == "swebench"

    def test_unknown_model_returns_none(self):
        assert code_score_for("acme/totally-fake-model") is None

    def test_returns_secondary_benchmarks_when_present(self):
        result = code_score_for("nvidia/llama-3.3-nemotron-super-49b-v1")
        assert result["livecodebench"] == 83.6


class TestCombinedScore:
    def test_returns_none_for_missing_inputs(self):
        assert combined_score(None, 100, 3000) is None
        assert combined_score(50, None, 3000) is None
        assert combined_score(None, None, 3000) is None

    def test_zero_ttft_keeps_full_score(self):
        # exp(0) = 1, so combined == code
        assert combined_score(80, 0, 3000) == pytest.approx(80.0)

    def test_ttft_equal_to_tau_loses_about_63_percent(self):
        # exp(-1) ~= 0.368
        result = combined_score(80, 3000, 3000)
        assert result == pytest.approx(80 * math.exp(-1), rel=0.01)

    def test_higher_ttft_means_lower_combined(self):
        a = combined_score(80, 500, 3000)
        b = combined_score(80, 1500, 3000)
        c = combined_score(80, 5000, 3000)
        assert a > b > c

    def test_smaller_tau_penalizes_latency_harder(self):
        strict = combined_score(80, 1000, 1500)
        lenient = combined_score(80, 1000, 6000)
        assert lenient > strict
