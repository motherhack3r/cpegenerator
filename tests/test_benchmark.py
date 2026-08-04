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
