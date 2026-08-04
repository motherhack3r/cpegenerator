"""Offline tests for the Phase-7 benchmark harness."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cpegen.benchmark import run_benchmark
from cpegen.extractor import (
    FIELD_PROMPTS,
    MockProvider,
    extract_per_field,
)


class ScriptedChatProvider:
    """Provider stub with a chat() that answers per-field prompts."""

    name = "scripted"

    def __init__(self, answers: dict[str, str]):
        self.answers = answers
        self.calls: list[str] = []
        self.last_usage = None

    def chat(self, system: str, user: str, max_tokens: int = 300) -> str:
        field = next(f for f, p in FIELD_PROMPTS.items() if p == system)
        self.calls.append(field)
        self.last_usage = {"in": 10, "out": 2}
        return self.answers.get(field, "null")


def test_per_field_extraction_one_call_per_field():
    p = ScriptedChatProvider({"vendor": "7-zip", "product": "7-Zip",
                              "version": "26.01"})
    ext = extract_per_field(p, "7-Zip 26.01 (x64)")
    assert p.calls == list(FIELD_PROMPTS)  # 5 calls, one per field
    assert (ext.vendor, ext.product, ext.version) == ("7-zip", "7-zip",
                                                      "26.01")
    assert ext.update is None and ext.target_sw is None
    assert p.last_usage == {"in": 50, "out": 10}  # aggregated


def test_per_field_cleans_wrapping_and_null_variants():
    p = ScriptedChatProvider({"vendor": '"Microsoft"\nextra line',
                              "product": "  word  ", "version": "None",
                              "update": "N/A", "target_sw": "-"})
    ext = extract_per_field(p, "Microsoft Word")
    assert ext.vendor == "microsoft" and ext.product == "word"
    assert ext.version is None and ext.update is None
    assert ext.target_sw is None


def test_per_field_falls_back_to_single_shot_without_chat():
    ext = extract_per_field(MockProvider(), "acme tool 1.0 for node.js")
    assert ext.vendor == "acme" and ext.product == "tool"
    assert ext.version == "1.0" and ext.target_sw == "node.js"


GOLD = ("in2code femanager 5.5.1 for typo3,"
        "[in2code](cpe_vendor) [femanager](cpe_product) "
        "[5.5.1](cpe_version) for typo3\n"
        "gecad axigen mail server 3.0,"
        "[gecad](cpe_vendor) [axigen mail server](cpe_product) "
        "[3.0](cpe_version)\n")


def _bench(tmp_path, **kw):
    gold = tmp_path / "gold.csv"
    gold.write_text(GOLD, encoding="utf-8")
    out = tmp_path / "bench"
    defaults = dict(input_path=gold, output_dir=out,
                    models=["model-a", "model-b"], provider_name="mock",
                    offline=True, cache_path=tmp_path / "cache.json")
    defaults.update(kw)
    return run_benchmark(**defaults), out


def test_matrix_runs_all_combos_and_writes_outputs(tmp_path):
    summaries, out = _bench(tmp_path)
    assert len(summaries) == 4  # 2 models x 2 modes
    assert {(s["model"], s["mode"]) for s in summaries} == {
        ("model-a", "single"), ("model-a", "per-field"),
        ("model-b", "single"), ("model-b", "per-field")}
    assert all(s["n"] == 2 for s in summaries)
    assert (out / "bench_summary.csv").exists()
    report = (out / "bench_report.md").read_text(encoding="utf-8")
    assert "model-a" in report and "per-field" in report
    with open(out / "bench_summary.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4 and "product_f1_strict" in rows[0]


def test_results_carry_latency_and_token_columns(tmp_path):
    _, out = _bench(tmp_path, models=["model-a"], modes=["single"])
    with open(out / "model-a__single" / "results.csv", newline="",
              encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert "latency_ms" in row and "tokens_in" in row


def test_resume_skips_completed_combos(tmp_path):
    summaries1, out = _bench(tmp_path, models=["model-a"])
    marker = out / "model-a__single" / "summary.json"
    saved = json.loads(marker.read_text(encoding="utf-8"))
    saved["n"] = 999  # poison: if re-run, this value would be recomputed
    marker.write_text(json.dumps(saved), encoding="utf-8")
    logs: list[str] = []
    summaries2, _ = _bench(tmp_path, models=["model-a"],
                           log=logs.append)
    by_combo = {(s["model"], s["mode"]): s for s in summaries2}
    assert by_combo[("model-a", "single")]["n"] == 999  # reused, not rerun
    assert any("skip" in m for m in logs)


def test_unknown_mode_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown modes"):
        _bench(tmp_path, modes=["single", "telepathy"])


class _FakeResponse:
    def __init__(self, status_code=200, content="{}", usage=None):
        self.status_code = status_code
        self._content = content
        self._usage = usage or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}],
                "usage": self._usage}


def _openai_provider(monkeypatch, responses, env=None):
    import cpegen.extractor as ex
    for key in ("CPEGEN_OPENAI_EXTRA", "CPEGEN_SYSTEM_SUFFIX"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setattr(ex.requests, "post", fake_post)
    provider = ex.OpenAICompatProvider(model="m", base_url="http://x/v1")
    return provider, calls


def test_openai_extra_body_and_suffix_applied(monkeypatch):
    provider, calls = _openai_provider(
        monkeypatch, [_FakeResponse()],
        env={"CPEGEN_OPENAI_EXTRA": '{"reasoning": "off"}',
             "CPEGEN_SYSTEM_SUFFIX": " /no_think"})
    provider.chat("sys", "user")
    assert calls[0]["reasoning"] == "off"
    assert calls[0]["messages"][0]["content"].endswith(" /no_think")


def test_openai_400_drops_extras_and_retries(monkeypatch):
    provider, calls = _openai_provider(
        monkeypatch,
        [_FakeResponse(status_code=400), _FakeResponse(content="ok"),
         _FakeResponse(content="ok2")],
        env={"CPEGEN_OPENAI_EXTRA": '{"reasoning": "off"}'})
    assert provider.chat("sys", "user") == "ok"
    assert "reasoning" in calls[0] and "reasoning" not in calls[1]
    provider.chat("sys", "user")  # extras stay dropped for the instance
    assert "reasoning" not in calls[2]


def test_lmstudio_native_payload_and_parsing(monkeypatch):
    import cpegen.extractor as ex
    for key in ("CPEGEN_REASONING", "CPEGEN_TEMPERATURE"):
        monkeypatch.delenv(key, raising=False)
    calls = []

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"output": [
                {"type": "reasoning", "content": "hmm"},
                {"type": "message", "content": '{"vendor": "x"}'}],
                "stats": {"input_tokens": 60, "total_output_tokens": 20,
                          "reasoning_output_tokens": 0}}

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return R()

    monkeypatch.setattr(ex.requests, "post", fake_post)
    p = ex.LMStudioProvider(model="google/gemma-4-e4b",
                            base_url="http://127.0.0.1:1234/v1")
    text = p.chat("sys", "Title: 'x'")
    url, body = calls[0]
    assert url == "http://127.0.0.1:1234/api/v1/chat"  # /v1 stripped
    assert body["reasoning"] == "off" and body["store"] is False
    assert body["temperature"] == 0.0
    assert body["system_prompt"] == "sys" and body["input"] == "Title: 'x'"
    assert text == '{"vendor": "x"}'  # reasoning item ignored
    assert p.last_usage == {"in": 60, "out": 20, "reasoning": 0}


def test_lmstudio_requires_model():
    import cpegen.extractor as ex
    import os
    os.environ.pop("CPEGEN_MODEL", None)
    with pytest.raises(RuntimeError, match="model key"):
        ex.LMStudioProvider()


def test_openai_captures_reasoning_tokens(monkeypatch):
    provider, _ = _openai_provider(monkeypatch, [_FakeResponse(
        usage={"prompt_tokens": 634, "completion_tokens": 276,
               "completion_tokens_details": {"reasoning_tokens": 226}})])
    provider.chat("sys", "user")
    assert provider.last_usage == {"in": 634, "out": 276, "reasoning": 226}
