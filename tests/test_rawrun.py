"""Offline tests for the Phase-7 mass-run pieces: title prep,
pipeline resume, and the two-model cascade."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cpegen.cascade import escalate_results
from cpegen.pipeline import run
from cpegen.titles import compose_title, extract_titles


# ------------------------------------------------------------- titles

def _write_export(tmp_path, rows, header):
    path = tmp_path / "export.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def test_titles_compose_dedup_and_garbage(tmp_path):
    path = _write_export(tmp_path, [
        ["Hilscher GmbH", "netX Driver", "1.0.1"],
        ["-", "---", "2, 6, 700, 0"],            # all garbage -> dropped
        ["hilscher gmbh", "netx driver", "1.0.1"],  # case-dup
        ["Acme", "Tool", "-"],                    # garbage version ok
    ], header=["CompanyName", "ProductName", "ProductVersion"])
    out = tmp_path / "titles.csv"
    stats = extract_titles(path, out,
                           cols=["CompanyName", "ProductName"],
                           version_col="ProductVersion")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert stats["written"] == 2 and stats["garbage"] == 1
    assert stats["duplicates"] == 1
    assert lines[0] == "Hilscher GmbH netX Driver 1.0.1"
    assert lines[1] == "Acme Tool"
    assert (out.parent / "titles.csv.metrics.json").exists()


def test_titles_version_col_not_duplicated():
    row = {"ProductName00": "Hamilton TraceLevel library v2.7",
           "ProductVersion00": "2.7"}
    assert compose_title(row, ["ProductName00"],
                         version_col="ProductVersion00") == \
        "Hamilton TraceLevel library v2.7"
    row2 = {"ProductName00": "Acme Tool", "ProductVersion00": "3.1"}
    assert compose_title(row2, ["ProductName00"],
                         version_col="ProductVersion00") == "Acme Tool 3.1"


def test_titles_noise_filtered_unless_kept(tmp_path):
    path = _write_export(tmp_path, [
        ["Security Update for Microsoft Office (KB2837593)"],
        ["7-Zip 26.01"],
    ], header=["ProductName00"])
    out = tmp_path / "t.csv"
    stats = extract_titles(path, out, cols=["ProductName00"])
    assert stats["noise"] == 1 and stats["written"] == 1
    stats2 = extract_titles(path, tmp_path / "t2.csv",
                            cols=["ProductName00"], keep_noise=True)
    assert stats2["written"] == 2


def test_titles_missing_column_raises(tmp_path):
    path = _write_export(tmp_path, [["x"]], header=["A"])
    with pytest.raises(ValueError, match="missing columns"):
        extract_titles(path, tmp_path / "t.csv", cols=["Nope"])


# ------------------------------------------------------------- resume

TITLES = ["7-zip 26.01", "notepad++ 8.9", "acme tool 1.0", "beta thing 2.0"]


def _titles_csv(tmp_path):
    path = tmp_path / "titles.csv"
    path.write_text("".join(f'"{t}"\n' for t in TITLES), encoding="utf-8")
    return path


def test_run_resume_skips_processed_titles(tmp_path):
    inp = _titles_csv(tmp_path)
    out = tmp_path / "run"
    run(input_path=inp, output_dir=out, provider_name="mock", offline=True,
        cache_path=tmp_path / "c.json")
    results = out / "results.csv"
    with open(results, newline="", encoding="utf-8") as f:
        full = list(csv.DictReader(f))
    assert len(full) == 4

    # Simulate a crash after two rows: truncate and resume.
    lines = results.read_text(encoding="utf-8").splitlines(keepends=True)
    results.write_text("".join(lines[:3]), encoding="utf-8")  # header + 2
    rows, _ = run(input_path=inp, output_dir=out, provider_name="mock",
                  offline=True, cache_path=tmp_path / "c.json", resume=True)
    assert len(rows) == 2  # only the missing two were processed
    with open(results, newline="", encoding="utf-8") as f:
        merged = list(csv.DictReader(f))
    assert [r["title"] for r in merged] == TITLES  # complete, no dupes


def test_run_without_resume_overwrites(tmp_path):
    inp = _titles_csv(tmp_path)
    out = tmp_path / "run"
    run(input_path=inp, output_dir=out, provider_name="mock", offline=True,
        cache_path=tmp_path / "c.json")
    rows, _ = run(input_path=inp, output_dir=out, provider_name="mock",
                  offline=True, cache_path=tmp_path / "c.json")
    with open(out / "results.csv", newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 4
    assert len(rows) == 4


# ------------------------------------------------------------ cascade

def test_escalate_reruns_tail_and_merges(tmp_path):
    inp = _titles_csv(tmp_path)
    fast_dir = tmp_path / "fast"
    run(input_path=inp, output_dir=fast_dir, provider_name="mock",
        offline=True, cache_path=tmp_path / "c.json")
    with open(fast_dir / "results.csv", newline="", encoding="utf-8") as f:
        fast = list(csv.DictReader(f))
    resolved = sum(1 for r in fast
                   if r["rule"] in ("M1", "M1A", "M1B", "M1C"))
    tail = len(fast) - resolved

    esc_dir = tmp_path / "cascade"
    stats = escalate_results(
        fast_results=fast_dir / "results.csv", output_dir=esc_dir,
        model="big-model", provider_name="mock", offline=True,
        cache_path=tmp_path / "c.json")
    assert stats["rows"] == 4 and stats["tail"] == tail
    assert stats["escalated_done"] == tail
    assert stats["m1x_after"] >= stats["m1x_before"] == resolved

    with open(esc_dir / "results_merged.csv", newline="",
              encoding="utf-8") as f:
        merged = list(csv.DictReader(f))
    assert [r["title"] for r in merged] == TITLES  # order preserved
    for r in merged:
        if r["escalated_by"]:
            assert r["escalated_by"] == "big-model"
            assert r["fast_rule"] != "" or r["fast_rule"] == ""  # column present
        else:
            assert r["rule"] in ("M1", "M1A", "M1B", "M1C")
    assert sum(1 for r in merged if r["escalated_by"]) == tail


def test_escalate_is_resumable(tmp_path):
    inp = _titles_csv(tmp_path)
    fast_dir = tmp_path / "fast"
    run(input_path=inp, output_dir=fast_dir, provider_name="mock",
        offline=True, cache_path=tmp_path / "c.json")
    esc_dir = tmp_path / "cascade"
    s1 = escalate_results(fast_results=fast_dir / "results.csv",
                          output_dir=esc_dir, model="m",
                          provider_name="mock", offline=True,
                          cache_path=tmp_path / "c.json")
    # Second invocation: pipeline resume skips everything already done.
    s2 = escalate_results(fast_results=fast_dir / "results.csv",
                          output_dir=esc_dir, model="m",
                          provider_name="mock", offline=True,
                          cache_path=tmp_path / "c.json")
    assert s2["escalated_done"] == s1["escalated_done"]
    assert s2["m1x_after"] == s1["m1x_after"]


def test_escalate_empty_results_raises(tmp_path):
    empty = tmp_path / "results.csv"
    empty.write_text("title,rule\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no rows"):
        escalate_results(empty, tmp_path / "o", model="m",
                         provider_name="mock")


def test_titles_unescape_html_entities(tmp_path):
    # WP1 step 1 actionable 3, confirmed on 18 real rows of products.csv.
    # Without this the matcher's clean() key gets phantom letters:
    # clean("AT&amp;T") is "atampt", not "att".
    from cpegen.matcher import clean
    from cpegen.titles import unescape_entities

    assert unescape_entities("Comments Import &amp; Export Plugin") == \
        "Comments Import & Export Plugin"
    assert clean(unescape_entities("AT&amp;T")) == "att"
    # Real row with triple escaping and a filtered "<" marker read as a
    # version: "VPN Gateway &amp;amp;amp;lt;5.1.7".
    assert unescape_entities("VPN Gateway &amp;amp;amp;lt;5.1.7") == \
        "VPN Gateway <5.1.7"
    # A bare ampersand is not an entity and must survive untouched.
    assert unescape_entities("Tom & Jerry 100% pure") == "Tom & Jerry 100% pure"

    path = tmp_path / "in.csv"
    path.write_text("ProductName00\nEZ Media &amp; Backup\n", encoding="utf-8")
    out = tmp_path / "titles.csv"
    extract_titles(path, out, cols=["ProductName00"])
    assert out.read_text(encoding="utf-8").strip() == "EZ Media & Backup"
