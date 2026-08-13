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
    "cpe:2.3:a:rockwellautomation:factorytalk_linx:6.11:*:*:*:*:*:*:*",
]


def _dictionary() -> LocalDictionary:
    d = LocalDictionary()
    from cpegen.dictionary import VendorAliases
    from cpegen.nvd import DictEntry
    from cpegen.wfn import split_formatted_string
    parts: dict[tuple[str, str], set[str]] = {}
    vendor_cpes: dict[str, int] = {}
    for i, cpe in enumerate(DICT_CPES):
        entry = DictEntry(cpe_name=cpe, cpe_name_id=f"id-{i}", title="t",
                          deprecated=False)
        comps = split_formatted_string(cpe)
        vendor, product = comps[3], comps[4]
        bucket = d.by_pair.setdefault((vendor, product), [])
        if not bucket:
            d.vendor_reps.setdefault(vendor, []).append(entry)
            d.product_reps.setdefault(product, []).append(entry)
            parts[(vendor, product)] = set()
        bucket.append(entry)
        parts[(vendor, product)].add(comps[2])
        vendor_cpes[vendor] = vendor_cpes.get(vendor, 0) + 1
        d.size += 1
    for pair, entries in d.by_pair.items():
        d.index.add(pair[0], pair[1], tuple(sorted(parts[pair])),
                    len(entries), all_deprecated=False)
    d.aliases = VendorAliases.build(vendor_cpes)
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


# ------------------------------------------------- WP1 canonicalization


LEGACY_FIELDS = [
    "title", "vendor", "product", "version", "update", "target_sw",
    "confidence", "cpe", "valid", "validation_errors", "rule", "rule_name",
    "match_similarity", "matched_cpe", "error", "stage", "fast_rule",
    "agent_turns", "note", "latency_ms", "tokens_in", "tokens_out",
]


def _write_legacy(path: Path, rows: list[dict]) -> None:
    """A results.csv exactly as written before WP1 (no new columns)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LEGACY_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def test_reclassify_canonicalizes_a_legacy_results_file(tmp_path):
    # The 10k RAW pilot file predates every canonicalization column: the
    # pass must add them instead of crashing, and the row whose only
    # problem was the naming convention must reach M1x.
    results = tmp_path / "results.csv"
    _write_legacy(results, [
        _row("Rockwell Automation FactoryTalk Linx CommDTM V1.4.0",
             "rockwell automation", "factorytalk linx commdtm", "1.4.0",
             rule="M4"),
    ])
    stats = reclassify_results(results, tmp_path / "out", _dictionary())
    assert stats["cpe_mismatch"] == 0 and stats["canonicalized"] == 1
    with open(tmp_path / "out" / "results.csv", newline="",
              encoding="utf-8") as fh:
        row = next(iter(csv.DictReader(fh)))
    assert row["rule"] == "M1B"
    assert row["canonical_vendor"] == "rockwellautomation"
    assert row["canonical_product"] == "factorytalk_linx"
    assert row["cpe"].startswith(
        "cpe:2.3:a:rockwellautomation:factorytalk_linx:1.4.0:")
    assert row["lookup_source"] == "dice"
    assert float(row["dice"]) > 0.85
    # the reader's own words are preserved: the NER evaluation reads them
    assert row["vendor"] == "rockwell automation"


def test_reclassify_is_idempotent_after_canonicalizing(tmp_path):
    # A canonicalized CPE no longer rebuilds from the stored entities.
    # That must not be mistaken for corruption on the next pass, or a
    # second reclassify would silently freeze every improved row.
    results = tmp_path / "results.csv"
    _write_legacy(results, [
        _row("Rockwell Automation FactoryTalk Linx CommDTM V1.4.0",
             "rockwell automation", "factorytalk linx commdtm", "1.4.0",
             rule="M4"),
        _row("7-Zip 25.00", "7-zip", "7-zip", "25.00", rule="M3"),
    ])
    first = reclassify_results(results, tmp_path / "one", _dictionary())
    second = reclassify_results(tmp_path / "one" / "results.csv",
                                tmp_path / "two", _dictionary())
    assert second["cpe_mismatch"] == 0
    assert second["reclassified"] == first["reclassified"]
    assert second["canonicalized"] == 0      # nothing left to canonicalize
    assert second["transitions"] == {}       # and no rule moved again
    one = list(csv.DictReader((tmp_path / "one" / "results.csv").open(
        encoding="utf-8")))
    two = list(csv.DictReader((tmp_path / "two" / "results.csv").open(
        encoding="utf-8")))
    assert one == two
