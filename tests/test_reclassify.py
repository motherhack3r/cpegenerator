"""Tests for `cpegen reclassify` — reclassification without re-extraction.

Motivation (2026-08-11, 10k RAW pilot): a fix in the dictionary lookup
or the matcher must be appliable to an existing results.csv in minutes,
not by re-running hours of GPU extraction. The stored extractions are
reused verbatim; the WFN is rebuilt deterministically and must match the
stored CPE (the validator's output remains the source of truth).
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from cpegen.dictionary import LocalDictionary
from cpegen.extractor import Extraction
from cpegen.pipeline import RowResult, build_wfn, reclassify_results

DICT_CPES = [
    "cpe:2.3:a:hp:deskjet_taplugin:60.0.196.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:7-zip:7-zip:25.00:*:*:*:*:*:*:*",
]


def _dictionary() -> LocalDictionary:
    d = LocalDictionary()
    from cpegen.nvd import DictEntry
    from cpegen.wfn import split_formatted_string
    for i, cpe in enumerate(DICT_CPES):
        entry = DictEntry(cpe_name=cpe, cpe_name_id=f"id-{i}", title="t",
                          deprecated=False)
        comps = split_formatted_string(cpe)
        vendor, product = comps[3], comps[4]
        bucket = d.by_pair.setdefault((vendor, product), [])
        if not bucket:
            d.vendor_reps.setdefault(vendor, []).append(entry)
            d.product_reps.setdefault(product, []).append(entry)
        bucket.append(entry)
        d.size += 1
    return d


def _row(title, vendor=None, product=None, version=None,
         rule="M3", valid=True) -> dict:
    row = RowResult(title=title)
    ext = Extraction(title=title, vendor=vendor, product=product,
                     version=version)
    row.vendor = vendor or ""
    row.product = product or ""
    row.version = version or ""
    if valid:
        wfn = build_wfn(ext)
        row.cpe = wfn.bind()
        row.valid = True
    row.rule = rule
    return {k: str(v) for k, v in asdict(row).items()}


def _write_results(path: Path, rows: list[dict]) -> None:
    fieldnames = list(asdict(RowResult(title="")).keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def test_reclassify_moves_catchall_rows_to_honest_buckets(tmp_path):
    results = tmp_path / "results.csv"
    _write_results(results, [
        # The DropBoxPlugin case: vendor known, product new. Was mislabeled
        # M3 by the old catch-all; must become M2 with the fixed lookup.
        _row("HP DropBoxPlugin 28.11", "hp", "dropboxplugin", "28.11",
             rule="M3"),
        # Nothing known to the dictionary: was M3 catch-all, must be M4.
        _row("Against the Odds 1.0", "cogent", "against_the_odds", "1.0",
             rule="M3"),
        # Exact formatted string in dictionary: must be M1 (pair index path).
        _row("7-Zip 25.00", "7-zip", "7-zip", "25.00", rule="M3"),
        # Row without a valid CPE passes through untouched.
        _row("garbage", valid=False, rule=""),
    ])
    stats = reclassify_results(results, tmp_path / "out", _dictionary())
    assert stats["rows"] == 4
    assert stats["reclassified"] == 3
    assert stats["unchanged_invalid"] == 1
    assert stats["cpe_mismatch"] == 0

    with open(tmp_path / "out" / "results.csv", newline="",
              encoding="utf-8") as fh:
        out = {r["title"]: r for r in csv.DictReader(fh)}
    assert out["HP DropBoxPlugin 28.11"]["rule"] == "M2"
    assert out["HP DropBoxPlugin 28.11"]["matched_cpe"] == ""  # under threshold
    assert float(out["HP DropBoxPlugin 28.11"]["match_similarity"]) > 0.0
    assert out["Against the Odds 1.0"]["rule"] == "M4"
    assert out["7-Zip 25.00"]["rule"] == "M1"
    assert out["garbage"]["rule"] == ""
    assert stats["transitions"]["M3 -> M2"] == 1
    assert stats["transitions"]["M3 -> M4"] == 1
    assert stats["transitions"]["M3 -> M1"] == 1


def test_reclassify_preserves_extra_columns(tmp_path):
    # A results_merged.csv from the cascade carries extra columns
    # (escalated_by, ...); reclassify must keep the file schema intact.
    results = tmp_path / "results.csv"
    base = _row("7-Zip 25.00", "7-zip", "7-zip", "25.00", rule="M3")
    base["escalated_by"] = "qwen3-8b"
    fieldnames = list(base.keys())
    with open(results, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerow(base)
    stats = reclassify_results(results, tmp_path / "out", _dictionary())
    assert stats["reclassified"] == 1
    with open(tmp_path / "out" / "results.csv", newline="",
              encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["escalated_by"] == "qwen3-8b"
    assert rows[0]["rule"] == "M1"
