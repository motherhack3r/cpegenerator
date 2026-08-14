"""Tests for cpegen.review_web (WP3 Fase A — annotation web UI).

Offline by design: the HTTP layer is exercised through the pure handler
functions (handle_state / handle_verdict), never through sockets.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from cpegen import goldset
from cpegen.review_web import (
    CSV_FIELDS,
    ENTITY_RE,
    UI_ASSET,
    ReviewState,
    VerdictError,
    bind_components,
    handle_state,
    handle_verdict,
)
from cpegen.sampling import QUEUE_FIELDS


def make_queue(tmp_path: Path, titles=("7-Zip 25.00 (x64)", "Steam 2.10")) -> Path:
    path = tmp_path / "gold-test_queue.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        for t in titles:
            row = {f: "" for f in QUEUE_FIELDS}
            row.update(title=t, origin="rawTest", stratum="random")
            writer.writerow(row)
    return path


def test_load_requires_identity(tmp_path):
    q = make_queue(tmp_path)
    with pytest.raises(VerdictError):
        ReviewState.load(q, identity="  ")


def test_load_rejects_non_queue_csv(tmp_path):
    bad = tmp_path / "results.csv"
    bad.write_text("title,rule\nfoo,M1\n", encoding="utf-8")
    with pytest.raises(VerdictError):
        ReviewState.load(bad, identity="humbert")


def test_annotated_verdict_roundtrips_through_goldset(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    annotated = "[7-Zip](cpe_vendor) [7-Zip](cpe_product) [25.00](cpe_version) (x64)"
    row = state.apply_verdict(0, "annotated", annotated)
    assert row["verdict"] == "annotated"
    assert row["annotator"] == "humbert"
    assert row["timestamp"]  # stamped
    # a frozen queue row must parse as gold with no conversion
    rec = goldset.parse_annotation(row["title"], row["annotated_title"])
    assert rec.vendor == "7-zip"
    assert rec.product == "7-zip"
    assert rec.version == "25.00"


def test_annotated_requires_brackets_and_vendor_or_product(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.apply_verdict(0, "annotated", "no brackets at all")
    with pytest.raises(VerdictError):
        state.apply_verdict(0, "annotated", "[25.00](cpe_version)")


def test_not_software_clears_brackets(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(1, "not_software",
                              "[stale](cpe_vendor) leftover")
    assert row["annotated_title"] == ""
    assert row["verdict"] == "not_software"


def test_unknown_verdict_and_bad_index(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.apply_verdict(0, "maybe", "")
    with pytest.raises(VerdictError):
        state.apply_verdict(99, "skipped", "")


def test_incremental_save_and_resume(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    state.apply_verdict(
        0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)")
    # a fresh load (new session) resumes with the verdict on disk
    resumed = ReviewState.load(q, identity="humbert")
    assert resumed.rows[0]["verdict"] == "annotated"
    assert resumed.rows[1]["verdict"] == ""
    assert resumed.progress() == {
        "total": 2, "done": 1, "annotated": 1,
        "not_software": 0, "skipped": 0,
    }


def test_save_preserves_all_queue_columns(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    state.apply_verdict(0, "skipped", "")
    with open(q, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == list(CSV_FIELDS)
        rows = list(reader)
    assert rows[0]["title"] == "7-Zip 25.00 (x64)"
    assert rows[0]["origin"] == "rawTest"


def test_separate_output_path_leaves_queue_untouched(tmp_path):
    q = make_queue(tmp_path)
    out = tmp_path / "annotations.csv"
    state = ReviewState.load(q, identity="humbert", output_path=out)
    state.apply_verdict(0, "not_software", "")
    original = ReviewState.load(q, identity="humbert")
    assert original.rows[0]["verdict"] == ""
    assert ReviewState.load(out, identity="humbert").rows[0]["verdict"] == \
        "not_software"


def test_http_handlers_are_thin_wrappers(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    payload = handle_state(state)
    assert payload["identity"] == "humbert"
    assert len(payload["rows"]) == 2

    ok = handle_verdict(state, {
        "index": 0, "verdict": "annotated",
        "annotated_title": "[Steam](cpe_vendor) [Steam](cpe_product)",
    })
    assert ok["ok"] is True
    assert ok["progress"]["done"] == 1

    bad = handle_verdict(state, {"index": 0, "verdict": "nope"})
    assert bad["ok"] is False and "verdict" in bad["error"]


def test_entity_regex_stays_in_sync_with_goldset():
    # review_web validates with its own copy of the pattern; if goldset's
    # private regex ever changes shape, this must fail loudly.
    assert ENTITY_RE.pattern == goldset._ENTITY_RE.pattern


def test_ui_asset_exists_and_is_self_contained():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "/api/state" in html and "/api/verdict" in html
    # no external script/resource dependencies (fonts degrade gracefully
    # and are the single allowed external reference)
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == [], f"unexpected external resources: {external}"


def test_bind_components_notary_path():
    out = bind_components({"part": "a", "vendor": "Microsoft",
                           "product": "Visual C++", "version": "2013"})
    assert out["ok"] is True
    assert out["cpe"] == "cpe:2.3:a:microsoft:visual_c\\+\\+:2013:*:*:*:*:*:*:*"
    assert out["wfn"].startswith("wfn:[")
    # normalization is the notary's, echoed back
    assert out["components"]["product"] == "visual_c++"


def test_bind_components_na_and_invalid_part():
    ok = bind_components({"part": "o", "vendor": "fortinet",
                          "product": "fortios", "update": "-"})
    assert ok["ok"] and ":o:fortinet:fortios:" in ok["cpe"] and ":-:" in ok["cpe"]
    bad = bind_components({"part": "x", "vendor": "acme", "product": "thing"})
    assert bad["ok"] is False and bad["cpe"] == "" and bad["errors"]


def test_annotated_verdict_stores_validated_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(
        0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)",
        components={"part": "a", "vendor": "7-Zip", "product": "7-Zip",
                    "version": "25.00"})
    assert row["cpe"] == "cpe:2.3:a:7-zip:7-zip:25.00:*:*:*:*:*:*:*"
    # persisted and resumable
    resumed = ReviewState.load(state.queue_path, identity="humbert")
    assert resumed.rows[0]["cpe"] == row["cpe"]


def test_annotated_verdict_rejects_unbindable_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.apply_verdict(
            0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)",
            components={"part": "zz", "vendor": "7-Zip", "product": "7-Zip"})
    # nothing was written for that row
    assert state.rows[0]["verdict"] == ""


def test_untouched_builder_defaults_store_no_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(
        0, "annotated", "[Steam](cpe_vendor) [Steam](cpe_product)",
        components={"part": "a", "target_sw": "confluence"})  # defaults only
    assert row["cpe"] == ""


def test_not_software_clears_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.apply_verdict(0, "annotated", "[Steam](cpe_vendor) [Steam](cpe_product)",
                        components={"vendor": "valve", "product": "steam"})
    row = state.apply_verdict(0, "not_software", "")
    assert row["cpe"] == "" and row["annotated_title"] == ""


def test_legacy_queue_without_cpe_column_loads_and_upgrades(tmp_path):
    q = make_queue(tmp_path)  # written with QUEUE_FIELDS only (no cpe)
    state = ReviewState.load(q, identity="humbert")
    assert all(r["cpe"] == "" for r in state.rows)
    state.apply_verdict(0, "skipped", "")
    with open(q, newline="", encoding="utf-8") as fh:
        assert csv.DictReader(fh).fieldnames == list(CSV_FIELDS)
