"""Offline tests for product-disjoint splits (step 5)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from cpegen.splits import SPLIT_FIELDS, SPLIT_NAMES, split_catalog
from cpegen.tiering import CONTRAST_FIELDS
from cpegen.curate import OUTPUT_FIELDS

_ALIAS_SPLIT = re.compile(r"(?<!\\),")
CATALOG_FIELDS = list(OUTPUT_FIELDS) + list(CONTRAST_FIELDS)


def _row(key, cpes, title="t"):
    row = {f: "" for f in CATALOG_FIELDS}
    row.update({"key": key, "title": title, "cpes": cpes,
                "n_aliases": str(len(cpes.split(",")))})
    return row


def _cpe(vendor, product, version):
    return f"cpe:2.3:a:{vendor}:{product}:{version}:*:*:*:*:*:*:*"


def _write(path: Path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CATALOG_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _make_catalog(tmp_path, n_products=40, versions=4):
    rows_a, rows_b = [], []
    for i in range(n_products):
        for v in range(versions):
            row = _row(f"k{i}_{v}", _cpe(f"vendor{i}", f"product{i}",
                                         f"{v}.0"))
            (rows_a if i % 10 == 0 else rows_b).append(row)
    _write(tmp_path / "a.csv", rows_a)
    _write(tmp_path / "b.csv", rows_b)
    return tmp_path / "a.csv", tmp_path / "b.csv"


def _read_splits(out_dir: Path):
    splits = {}
    for name in SPLIT_NAMES:
        with open(out_dir / "splits" / f"{name}.csv", newline="",
                  encoding="utf-8") as f:
            splits[name] = list(csv.DictReader(f))
    return splits


def _pairs_of(row):
    out = set()
    for alias in _ALIAS_SPLIT.split(row["cpes"]):
        parts = alias.split(":")
        out.add((parts[3], parts[4]))
    return out


def test_no_product_pair_crosses_splits(tmp_path):
    a, b = _make_catalog(tmp_path)
    stats = split_catalog(a, b, tmp_path / "out")
    splits = _read_splits(tmp_path / "out")
    seen: dict = {}
    for name, rows in splits.items():
        for row in rows:
            for pair in _pairs_of(row):
                assert seen.setdefault(pair, name) == name, \
                    f"{pair} leaks between {seen[pair]} and {name}"
    assert sum(stats["counts"].values()) == stats["rows"] == 160


def test_versions_of_same_product_stay_together(tmp_path):
    a, b = _make_catalog(tmp_path, n_products=10, versions=6)
    split_catalog(a, b, tmp_path / "out")
    splits = _read_splits(tmp_path / "out")
    where = {}
    for name, rows in splits.items():
        for row in rows:
            product = row["key"].split("_")[0]
            assert where.setdefault(product, name) == name


def test_vendor_alias_families_merge_via_union_find(tmp_path):
    # row1 links (v1,p) & (v2,p); row2 only (v2,p); row3 only (v1,q)
    # via row4 (v1,p)+(v1,q): all four must land in the same split.
    rows = [
        _row("r1", ",".join([_cpe("v1", "p", "1"), _cpe("v2", "p", "1")])),
        _row("r2", _cpe("v2", "p", "2")),
        _row("r3", _cpe("v1", "q", "1")),
        _row("r4", ",".join([_cpe("v1", "p", "3"), _cpe("v1", "q", "3")])),
    ]
    _write(tmp_path / "a.csv", rows[:1])
    _write(tmp_path / "b.csv", rows[1:])
    split_catalog(tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "out")
    splits = _read_splits(tmp_path / "out")
    non_empty = [n for n in SPLIT_NAMES if splits[n]]
    assert len(non_empty) == 1 and len(splits[non_empty[0]]) == 4


def test_same_seed_is_deterministic_different_seed_differs(tmp_path):
    a, b = _make_catalog(tmp_path)
    split_catalog(a, b, tmp_path / "out1", seed=7)
    split_catalog(a, b, tmp_path / "out2", seed=7)
    r1 = (tmp_path / "out1" / "splits" / "benchmark_gold.csv").read_text()
    r2 = (tmp_path / "out2" / "splits" / "benchmark_gold.csv").read_text()
    assert r1 == r2
    split_catalog(a, b, tmp_path / "out3", seed=8)
    r3 = (tmp_path / "out3" / "splits" / "benchmark_gold.csv").read_text()
    assert r1 != r3


def test_fractions_roughly_honored_and_tier_kept(tmp_path):
    a, b = _make_catalog(tmp_path, n_products=100, versions=2)
    stats = split_catalog(a, b, tmp_path / "out")
    c = stats["counts"]
    assert abs(c["benchmark_gold"] - 20) <= 4 and abs(c["test"] - 20) <= 4
    splits = _read_splits(tmp_path / "out")
    tiers = {r["tier"] for rows in splits.values() for r in rows}
    assert tiers == {"A", "B"}


def test_manifest_written_with_seed_and_hashes(tmp_path):
    a, b = _make_catalog(tmp_path)
    stats = split_catalog(a, b, tmp_path / "out", seed=42)
    manifest = (tmp_path / "out" / "MANIFEST.md").read_text(encoding="utf-8")
    assert "`42`" in manifest and "sha256" in manifest
    for digest in stats["sources"].values():
        assert digest in manifest


def test_bad_fractions_raise(tmp_path):
    a, b = _make_catalog(tmp_path, n_products=2)
    with pytest.raises(ValueError, match="sum to 1"):
        split_catalog(a, b, tmp_path / "out",
                      fractions={"benchmark_gold": 0.5, "test": 0.2,
                                 "train": 0.2})
