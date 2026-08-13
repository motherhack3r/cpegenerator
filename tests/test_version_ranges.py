"""Offline tests for the version comparator and the range sidecar.

WP1 step 3 (spec #2, N10): the CPE dictionary is *extensional* — it lists
concrete versions — while the NVD models most of the version space
through ``PlatformConfiguration`` ranges. When a pair matches but the
version is not listed, the ranges are the richer source.

The comparator's whole design point is its third verdict. CPE version
strings have no single grammar, so anything the token structure does not
settle must come back as "undecidable" and be reported as such, never
guessed into a boolean.
"""

from __future__ import annotations

import gzip
import json

import pytest

from cpegen.dictionary import (
    DEFAULT_RANGES,
    LocalDictionary,
    _neo4j_ranges_fetch,
    build_ranges,
    load_ranges,
)
from cpegen.matcher import (
    VersionRange,
    classify,
    compare_versions,
    version_in_ranges,
    version_tokens,
)
from cpegen.nvd import DictEntry
from cpegen.wfn import WFN

# ------------------------------------------------------------ tokenizer


def test_version_tokens_splits_numbers_and_words():
    assert version_tokens("4.8.04690.02") == [4, 8, 4690, 2]
    assert version_tokens("4.0.1_build_5289") == [4, 0, 1, "build", 5289]
    assert version_tokens("v11.1.2245") == [11, 1, 2245]   # NVD writes both
    assert version_tokens("cpr9") == ["cpr", 9]
    assert version_tokens("") == []


# ------------------------------------------------------------ comparator


@pytest.mark.parametrize("a,b,expected", [
    ("1.0", "1.0", 0),
    ("1.0", "1.0.0", 0),          # trailing zeros are equality
    ("6.0", "6.00", 0),           # the padding problem of playbook §9.3
    ("1.0", "1.0.1", -1),
    ("6.10", "6.9", 1),           # numeric, not lexicographic
    ("2.43.6", "2.43.10", -1),
    ("15.5.7", "15.5.10", -1),
    ("24.8.0.1", "24.8.5", -1),
    ("2019", "2017", 1),
    ("13.00.00", "13.0", 0),
])
def test_compare_versions_orders_real_shapes(a, b, expected):
    assert compare_versions(a, b) == expected
    assert compare_versions(b, a) == -expected


@pytest.mark.parametrize("a,b", [
    ("cpr9", "2.90"),        # a word facing a number: no shared order
    ("1.0.0", "1.0.0rc1"),   # pre-release or build metadata? CPE does not say
    ("1.0", ""),
    ("", "1.0"),
])
def test_compare_versions_refuses_to_guess(a, b):
    assert compare_versions(a, b) is None


@pytest.mark.parametrize("a,b", [
    ("19.0", "2019.1.4"),            # AutoCAD: internal vs year release
    ("23.1", "2019.1.4"),
    ("22.002", "2020.009.20074"),    # Adobe Reader: continuous vs classic
    ("8.5.1", "2012"),               # LabVIEW
])
def test_compare_versions_detects_a_numbering_scheme_mismatch(a, b):
    # Found by auditing real verdicts on the 10k pilot (2026-08-13).
    # Numerically 19 < 2019, so the naive comparator answered "inside the
    # vulnerable range" with full confidence about two numbering schemes
    # that were never on the same scale.
    assert compare_versions(a, b) is None


@pytest.mark.parametrize("a,b,expected", [
    ("2020.1", "2019.5", 1),         # both year releases: comparable
    ("91.0", "107.0.1418.62", -1),   # neither: comparable
    ("2019", "2017", 1),
])
def test_scheme_guard_does_not_fire_on_matching_schemes(a, b, expected):
    assert compare_versions(a, b) == expected


def test_comparator_is_a_total_order_where_it_answers():
    versions = ["1.0", "1.0.1", "1.2", "2.0", "2.0.1", "10.0", "10.0.1"]
    for i, a in enumerate(versions):
        for j, b in enumerate(versions):
            cmp = compare_versions(a, b)
            assert cmp is not None
            assert cmp == (0 if i == j else (-1 if i < j else 1))


# --------------------------------------------------------------- ranges


def test_range_contains_respects_inclusive_and_exclusive_bounds():
    rng = VersionRange(start_including="2.43.0", end_excluding="2.43.6")
    assert rng.contains("2.43.0") is True
    assert rng.contains("2.43.5") is True
    assert rng.contains("2.43.6") is False
    assert rng.contains("2.42.9") is False
    excl = VersionRange(start_excluding="1.0", end_including="2.0")
    assert excl.contains("1.0") is False
    assert excl.contains("2.0") is True


def test_range_str_is_readable():
    assert str(VersionRange(start_including="1.0", end_excluding="2.0")) == \
        ">=1.0 <2.0"
    assert str(VersionRange(end_including="6.11")) == "<=6.11"


def test_unbounded_range_is_undecidable_not_true():
    assert VersionRange().contains("1.0") is None


def test_version_in_ranges_returns_the_third_verdict():
    # Real ranges of rockwellautomation:factorytalk_linx in the KGCS.
    ranges = [VersionRange(end_including="6.11"),
              VersionRange(end_excluding="6.50")]
    assert version_in_ranges("6.11", ranges) is True
    assert version_in_ranges("7.00", ranges) is False
    # An unreadable version must not be reported as "not covered": that
    # is the difference between "new release" and "never checked".
    assert version_in_ranges("cpr9", ranges) is None
    assert version_in_ranges("", ranges) is None
    assert version_in_ranges("1.0", []) is None


def test_one_unreadable_range_withholds_the_false():
    ranges = [VersionRange(end_including="6.11"),
              VersionRange(start_including="cpr1", end_including="cpr9")]
    assert version_in_ranges("7.0", ranges) is None


# ---------------------------------------------------- build and reload

KGCS_ROWS = [
    ["cpe:2.3:a:rockwellautomation:factorytalk_linx:*:*:*:*:*:*:*:*",
     "", "", "6.11", ""],
    ["cpe:2.3:a:rockwellautomation:factorytalk_linx:*:*:*:*:*:*:*:*",
     "", "", "", "6.50"],
    ["cpe:2.3:a:rockwellautomation:factorytalk_linx:*:*:*:*:*:*:*:*",
     "", "", "6.11", ""],                       # duplicate: collapses
    ["cpe:2.3:a:notepad-plus-plus:notepad\\+\\+:*:*:*:*:*:*:*:*",
     "8.0", "", "", "8.9"],
    ["not a cpe", "1.0", "", "", "2.0"],        # malformed: counted
]


def _fake_ranges_fetch(rows):
    def post(statement, parameters):
        if "count(*)" in statement:
            return {"results": [{"data": [{"row": [len(rows)]}]}]}
        skip, limit = parameters["skip"], parameters["limit"]
        page = rows[skip:skip + limit]
        return {"results": [{"data": [{"row": r} for r in page]}]}
    return _neo4j_ranges_fetch(post=post)


def test_build_ranges_aggregates_per_pair(tmp_path):
    out = tmp_path / "ranges.jsonl.gz"
    stats = build_ranges(out, fetch=_fake_ranges_fetch(KGCS_ROWS),
                         page_size=2)
    assert stats["malformed"] == 1
    assert stats["pairs"] == 2
    assert stats["ranges"] == 3          # the duplicate collapsed
    with gzip.open(out, "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert {r["v"] for r in rows} == {"rockwellautomation",
                                      "notepad-plus-plus"}


def test_load_ranges_keys_on_the_bound_component_form(tmp_path):
    out = tmp_path / "ranges.jsonl.gz"
    build_ranges(out, fetch=_fake_ranges_fetch(KGCS_ROWS), page_size=10)
    table = load_ranges(out)
    # The key is the dictionary's own escaped form, so it indexes
    # straight into LocalDictionary.by_pair without a second convention.
    assert ("notepad-plus-plus", "notepad\\+\\+") in table
    ranges = table[("rockwellautomation", "factorytalk_linx")]
    assert version_in_ranges("6.11", ranges) is True


def test_neo4j_ranges_fetch_filters_inactive_by_default():
    seen = []

    def post(statement, parameters):
        seen.append(statement)
        if "count(*)" in statement:
            return {"results": [{"data": [{"row": [0]}]}]}
        return {"results": [{"data": []}]}

    _neo4j_ranges_fetch(post=post)(0, 10)
    assert all("configStatus = 'Active'" in s for s in seen)
    seen.clear()
    _neo4j_ranges_fetch(post=post, include_inactive=True)(0, 10)
    assert all("configStatus" not in s for s in seen)


# --------------------------------------------- integration with classify


def _entry(cpe):
    return DictEntry(cpe_name=cpe, cpe_name_id="x", title="t",
                     deprecated=False)


def test_version_source_is_a_column_not_a_new_rule():
    # Decision 2026-08-11 applied again: provenance is reported in a
    # column; the M scale keeps measuring matching and stays uniform.
    wfn = WFN(part="a", vendor="rockwellautomation",
              product="factorytalk_linx", version="6.30")
    entries = [_entry("cpe:2.3:a:rockwellautomation:factorytalk_linx:"
                      "6.11:*:*:*:*:*:*:*")]
    ranges = [VersionRange(end_excluding="6.50")]
    out = classify(wfn, entries, ranges=ranges)
    assert out.rule == "M1B"                 # unchanged
    assert out.version_source == "range"     # but now we know why


def test_version_source_outside_and_unknown():
    wfn = WFN(part="a", vendor="v", product="p", version="9.9")
    entries = [_entry("cpe:2.3:a:v:p:1.0:*:*:*:*:*:*:*")]
    assert classify(wfn, entries,
                    ranges=[VersionRange(end_including="6.11")]
                    ).version_source == "outside"
    odd = WFN(part="a", vendor="v", product="p", version="cpr9")
    out = classify(odd, entries, ranges=[VersionRange(end_including="6.11")])
    assert out.version_source == "unknown"
    assert "version_unreadable" in out.review_reason


def test_exact_dictionary_version_reports_dict_provenance():
    wfn = WFN(part="a", vendor="v", product="p", version="1.0")
    entries = [_entry("cpe:2.3:a:v:p:1.0:*:*:*:*:*:*:*")]
    assert classify(wfn, entries).version_source == "dict"


def test_no_ranges_snapshot_leaves_the_column_empty():
    wfn = WFN(part="a", vendor="v", product="p", version="9.9")
    entries = [_entry("cpe:2.3:a:v:p:1.0:*:*:*:*:*:*:*")]
    out = classify(wfn, entries)
    assert out.rule == "M1B" and out.version_source == ""


def test_local_dictionary_without_ranges_is_unaffected(tmp_path):
    # The sidecar is optional by construction: no file, no behaviour
    # change anywhere (the runtime must stay offline and self-contained).
    from cpegen.dictionary import build_snapshot

    snap = tmp_path / "dict.jsonl.gz"

    def fetch(start, size):
        products = [{"cpe": {"cpeName": "cpe:2.3:a:v:p:1.0:*:*:*:*:*:*:*",
                             "cpeNameId": "id", "titles": [],
                             "deprecated": False}}] if start == 0 else []
        return {"totalResults": 1, "resultsPerPage": len(products),
                "products": products}

    build_snapshot(snap, fetch=fetch, page_size=10)
    d = LocalDictionary.load(snap, ranges_path=tmp_path / "missing.jsonl.gz")
    assert d.ranges == {}
    assert d.lookup("v", "p", title="v p 1.0").ranges == []
    assert DEFAULT_RANGES.name == "cpe_ranges.jsonl.gz"


def test_build_ranges_refuses_to_write_an_empty_sidecar(tmp_path):
    # Observed 2026-08-13: the KGCS graph lives in a database named
    # "kgcs-dv3" while the client defaults to "neo4j", so the build
    # reported success over zero rows and left an empty sidecar that
    # loads silently and makes every version read "unknown" forever.
    def empty_fetch(start, size):
        return {"totalResults": 0, "resultsPerPage": 0, "rows": []}

    out = tmp_path / "ranges.jsonl.gz"
    with pytest.raises(RuntimeError) as err:
        build_ranges(out, fetch=empty_fetch)
    assert "NEO4J_DATABASE" in str(err.value)
    assert not out.exists()          # nothing half-written either
