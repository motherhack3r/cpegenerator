"""Offline tests for tiering + local dictionary contrast (steps 3-4)."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from cpegen.curate import OUTPUT_FIELDS
from cpegen.dictionary import LocalDictionary
from cpegen.tiering import (
    contrast_aliases,
    quarantine_reason,
    tier_file,
)

DICT_CPES = [
    ("cpe:2.3:a:clamav:clamav:0.101.1:*:*:*:*:*:*:*", False),
    ("cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*", False),
    ("cpe:2.3:a:7-zip:7-zip:9.20:*:*:*:*:*:*:*", True),   # deprecated
    ("cpe:2.3:a:cisco:nx-os:13.2:*:*:*:*:*:*:*", False),
    ("cpe:2.3:a:cisco:mds_9000:13.2:*:*:*:*:*:*:*", False),
]


def _dictionary(tmp_path) -> LocalDictionary:
    path = tmp_path / "dict.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for name, deprecated in DICT_CPES:
            f.write(json.dumps({"cpeName": name, "cpeNameId": "x",
                                "title": "", "deprecated": deprecated})
                    + "\n")
    return LocalDictionary.load(path)


def _catalog_row(key="k1", cpes="", has_override="0", created_by="system",
                 n_aliases=None):
    row = {f: "" for f in OUTPUT_FIELDS}
    row.update({"key": key, "key_source": "vulndb", "title": "t",
                "cpes": cpes, "has_override": has_override,
                "created_by": created_by,
                "n_aliases": str(n_aliases or len(cpes.split(",")))})
    return row


def _write_catalog(tmp_path, rows) -> Path:
    path = tmp_path / "catalog_parsed.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def _run(tmp_path, rows, with_dict=True):
    catalog = _write_catalog(tmp_path, rows)
    dict_path = None
    if with_dict:
        _dictionary(tmp_path)  # writes dict.jsonl.gz
        dict_path = tmp_path / "dict.jsonl.gz"
    out = tmp_path / "curated"
    stats = tier_file(catalog, out, dictionary_path=dict_path)
    read = {}
    for name in ("catalog_tier_a", "catalog_tier_b", "quarantine"):
        with open(out / f"{name}.csv", newline="", encoding="utf-8") as f:
            read[name] = list(csv.DictReader(f))
    return stats, read


def test_override_goes_to_tier_a_rest_to_b(tmp_path):
    stats, read = _run(tmp_path, [
        _catalog_row(key="a", has_override="1",
                     cpes="cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*"),
        _catalog_row(key="b", created_by="ana@example.com",
                     cpes="cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*"),
    ])
    assert stats["tier_a"] == 1 and stats["tier_b"] == 1
    assert stats["tier_b_human_created"] == 1
    assert read["catalog_tier_b"][0]["creator"] == "human"


def test_contrast_counts_exact_deprecated_and_pairs(tmp_path):
    d = _dictionary(tmp_path)
    c = contrast_aliases([
        "cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*",   # exact
        "cpe:2.3:a:7-zip:7-zip:9.20:*:*:*:*:*:*:*",    # exact + deprecated
        "cpe:2.3:a:7-zip:7-zip:99.0:*:*:*:*:*:*:*",    # pair known only
        "cpe:2.3:a:nobody:nothing:1:*:*:*:*:*:*:*",    # unknown pair
    ], d)
    assert (c.n_in_dict, c.n_deprecated, c.n_pairs_known) == (2, 1, 3)
    assert c.unknown_pairs == (("nobody", "nothing"),)


def test_contaminated_alias_set_is_quarantined(tmp_path):
    # ClamAV title carrying cisco/appdynamics aliases (plan's example):
    # multi-vendor, no product token overlap, appdynamics pair unknown.
    cpes = ",".join([
        "cpe:2.3:a:clamav:clamav:0.101.1:*:*:*:*:*:*:*",
        "cpe:2.3:a:appdynamics:controller:0.101.1:*:*:*:*:*:*:*",
    ])
    stats, read = _run(tmp_path, [_catalog_row(cpes=cpes)])
    assert stats["quarantine"] == 1 and stats["tier_b"] == 0
    assert read["quarantine"][0]["reason"].startswith(
        "incompatible_vendors:appdynamics:controller")


def test_dictionary_known_pairs_are_not_quarantined(tmp_path):
    # nx-os vs mds_9000 share no token, but both cisco pairs exist in
    # the dictionary: legitimate alias set, stays in tier B.
    cpes = ",".join([
        "cpe:2.3:a:cisco:nx-os:13.2:*:*:*:*:*:*:*",
        "cpe:2.3:a:cisco:mds_9000:13.2:*:*:*:*:*:*:*",
    ])
    stats, _ = _run(tmp_path, [_catalog_row(cpes=cpes)])
    assert stats["quarantine"] == 0 and stats["tier_b"] == 1


def test_multi_vendor_dict_known_pairs_not_quarantined(tmp_path):
    d = _dictionary(tmp_path)
    aliases = ["cpe:2.3:a:cisco:nx-os:13.2:*:*:*:*:*:*:*",
               "cpe:2.3:a:clamav:clamav:0.101.1:*:*:*:*:*:*:*"]
    c = contrast_aliases(aliases, d)
    assert quarantine_reason(aliases, c) is None  # both pairs are known


def test_same_vendor_or_token_overlap_never_quarantines(tmp_path):
    assert quarantine_reason([
        "cpe:2.3:a:apache:solr:1:*:*:*:*:*:*:*",
        "cpe:2.3:a:apache:apache_solr:1:*:*:*:*:*:*:*",
    ], None) is None  # single vendor
    assert quarantine_reason([
        "cpe:2.3:a:woocommerce:node-canvas:1:*:*:*:*:*:*:*",
        "cpe:2.3:a:automattic:node-canvas:1:*:*:*:*:*:*:*",
    ], None) is None  # same product


def test_without_dictionary_token_heuristic_still_works(tmp_path):
    cpes = ",".join([
        "cpe:2.3:a:clamav:clamav:0.101.1:*:*:*:*:*:*:*",
        "cpe:2.3:a:appdynamics:controller:0.101.1:*:*:*:*:*:*:*",
    ])
    stats, read = _run(tmp_path, [_catalog_row(cpes=cpes)], with_dict=False)
    assert stats["quarantine"] == 1
    assert read["quarantine"][0]["reason"] == \
        "incompatible_vendors:no_dictionary"
    assert stats["aliases_contrasted"] == 0


def test_metrics_json_written(tmp_path):
    _run(tmp_path, [_catalog_row(
        cpes="cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*")])
    metrics = json.loads(
        (tmp_path / "curated" / "tier_metrics.json").read_text())
    assert metrics["rows"] == 1 and metrics["dictionary_size"] == 5
