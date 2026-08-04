"""Offline tests for the SCCM catalog curation module (steps 1-2)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cpegen.curate import (
    CurationStats,
    canonicalize_alias,
    curate_file,
    curate_rows,
    split_aliases,
)

HEADER = (
    "MS Product ID;CPE;Edition;Part;Product;Update;Vendor Platform;"
    "Override Title;Override Platform;Override Platform Version;"
    "Override Vendor;Sync Title;Sync Platform;Sync Platform Version;"
    "Sync Vendor;Date Created;Last Modified;Last Updated;Last Published;"
    "Last Synced;Created By;Updated By;Last Sync Data Source;Source;"
    "Product Version;Title;Display;Vendor;Vuln DB ID;Platform Name;"
    "Platform;Vendor Definition"
)


def _row(cpe="", title="Tool 1.0", version="1.0", vendor="Acme",
         product="Tool", vulndb="k1", created_by="system",
         override_title="", edition=""):
    cols = [""] * 32
    cols[1] = cpe
    cols[2] = edition
    cols[4] = product
    cols[7] = override_title
    cols[20] = created_by
    cols[21] = "1,10492E+18"  # Excel-corrupted epoch, must be ignored
    cols[24] = version
    cols[25] = title
    cols[27] = vendor
    cols[28] = vulndb
    return ";".join(cols)


def _write_csv(tmp_path: Path, rows: list[str]) -> Path:
    path = tmp_path / "products.csv"
    path.write_bytes(("\r\n".join([HEADER] + rows) + "\r\n").encode("utf-8"))
    return path


def _curate(tmp_path: Path, rows: list[str]):
    path = _write_csv(tmp_path, rows)
    out = tmp_path / "curated"
    stats = curate_file(path, out)
    with open(out / "catalog_parsed.csv", encoding="utf-8", newline="") as f:
        kept = list(csv.DictReader(f))
    rejects = [json.loads(line)
               for line in (out / "rejects.log").read_text().splitlines()]
    return stats, kept, rejects, out


def test_valid_single_cpe_row_is_kept(tmp_path):
    stats, kept, rejects, _ = _curate(tmp_path, [
        _row(cpe="cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*"),
    ])
    assert stats.rows_kept == 1 and not rejects
    assert kept[0]["key"] == "k1"
    assert kept[0]["key_source"] == "vulndb"
    assert kept[0]["cpes"] == "cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*"


def test_alias_set_is_exploded_and_deduped(tmp_path):
    cell = ("cpe:2.3:a:woocommerce:node-canvas:0.13.0:*:*:*:*:*:*:*,"
            "cpe:2.3:a:automattic:node-canvas:0.13.0:*:*:*:*:*:*:*,"
            "cpe:2.3:a:automattic:node-canvas:0.13.0:*:*:*:*:*:*:*")
    stats, kept, _, _ = _curate(tmp_path, [_row(cpe=cell)])
    assert kept[0]["n_aliases"] == "2"
    assert stats.aliases_deduped == 1


def test_escaped_comma_does_not_split_alias():
    aliases = split_aliases(
        r"cpe:2.3:a:acme:tool\,pro:1.0:*:*:*:*:*:*:*,"
        r"cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*")
    assert len(aliases) == 2
    assert aliases[0] == r"cpe:2.3:a:acme:tool\,pro:1.0:*:*:*:*:*:*:*"


def test_unfixable_alias_dropped_but_row_kept(tmp_path):
    cell = ("cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*,"
            "cpe:2.3:a:acme:tool:1.0")  # wrong component count: no salvage
    stats, kept, rejects, _ = _curate(tmp_path, [_row(cpe=cell)])
    assert stats.rows_kept == 1
    assert kept[0]["n_aliases"] == "1"
    assert kept[0]["n_dropped_aliases"] == "1"
    assert any(r["step"] == "validate" and r["reason"].startswith("abnf:")
               for r in rejects)


def test_near_miss_alias_is_normalized_and_logged(tmp_path):
    # Uppercase version + embedded space: canonical WFN salvage.
    cell = "cpe:2.3:h:arubanetworks:proliant:2.69 (Gen9 Server):*:*:*:*:*:*:*"
    stats, kept, rejects, out = _curate(tmp_path, [_row(cpe=cell)])
    assert stats.rows_kept == 1 and stats.aliases_normalized == 1
    assert kept[0]["cpes"] == (
        r"cpe:2.3:h:arubanetworks:proliant:2.69_\(gen9_server\):*:*:*:*:*:*:*")
    assert kept[0]["n_normalized_aliases"] == "1"
    assert not rejects
    norm = [json.loads(line)
            for line in (out / "normalized.log").read_text().splitlines()]
    assert norm[0]["original"] == cell.split(";")[0] or norm[0]["original"]
    assert norm[0]["canonical"] == kept[0]["cpes"]


def test_normalization_collapses_onto_existing_valid_alias(tmp_path):
    cell = ("cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*,"
            "cpe:2.3:a:Acme:tool:1.0:*:*:*:*:*:*:*")  # normalizes to twin
    stats, kept, _, _ = _curate(tmp_path, [_row(cpe=cell)])
    assert kept[0]["n_aliases"] == "1"  # no duplicate after salvage
    assert stats.aliases_normalized == 1


def test_canonicalize_alias_rejects_wrong_shape():
    assert canonicalize_alias("Release Candidate 1:*:*") is None
    assert canonicalize_alias("cpe:2.3:a:php:php:4.0") is None


def test_row_with_all_invalid_aliases_is_rejected(tmp_path):
    stats, kept, rejects, _ = _curate(tmp_path, [
        _row(cpe="cpe:2.3:a:acme:tool:1.0"),  # wrong component count
    ])
    assert stats.rows_kept == 0 and not kept
    assert any(r["reason"] == "all_aliases_invalid" for r in rejects)


def test_row_without_cpe_is_rejected_with_log(tmp_path):
    stats, kept, rejects, _ = _curate(tmp_path, [_row(cpe="")])
    assert stats.rows_rejected_no_cpe == 1 and not kept
    assert rejects[0]["reason"] == "no_cpe"
    assert rejects[0]["key"] == "k1"


def test_missing_vulndb_id_gets_stable_derived_key(tmp_path):
    row = _row(cpe="cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*", vulndb="")
    stats1, kept1, _, _ = _curate(tmp_path, [row])
    (tmp_path / "products.csv").unlink()
    stats2, kept2, _, _ = _curate(tmp_path, [row])
    assert kept1[0]["key_source"] == "derived"
    assert kept1[0]["key"] == kept2[0]["key"]  # deterministic
    assert stats1.keys_derived == 1


def test_duplicate_key_is_rejected(tmp_path):
    row = _row(cpe="cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*")
    stats, kept, rejects, _ = _curate(tmp_path, [row, row])
    assert stats.rows_kept == 1 and len(kept) == 1
    assert any(r["reason"] == "duplicate_key" for r in rejects)


def test_override_and_created_by_survive_for_tiering(tmp_path):
    _, kept, _, _ = _curate(tmp_path, [
        _row(cpe="cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*",
             override_title="Fixed Title", created_by="user@example.com"),
        _row(cpe="cpe:2.3:a:acme:other:2.0:*:*:*:*:*:*:*", vulndb="k2"),
    ])
    assert kept[0]["has_override"] == "1"
    assert kept[0]["created_by"] == "user@example.com"
    assert kept[1]["has_override"] == "0"


def test_corrupt_updated_by_is_not_consumed(tmp_path):
    # The Excel-degraded 'Updated By' must never leak into the output.
    _, kept, _, out = _curate(tmp_path, [
        _row(cpe="cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*"),
    ])
    text = (out / "catalog_parsed.csv").read_text()
    assert "10492E" not in text


def test_missing_required_column_raises():
    stats = CurationStats()
    with pytest.raises(ValueError, match="missing expected columns"):
        list(curate_rows(iter([]), ["Title", "CPE"], lambda r: None, stats))


def test_metrics_json_written_with_source_hash(tmp_path):
    _, _, _, out = _curate(tmp_path, [
        _row(cpe="cpe:2.3:a:acme:tool:1.0:*:*:*:*:*:*:*"),
    ])
    metrics = json.loads((out / "curation_metrics.json").read_text())
    assert metrics["stats"]["rows_kept"] == 1
    assert len(metrics["source_sha256"]) == 64
