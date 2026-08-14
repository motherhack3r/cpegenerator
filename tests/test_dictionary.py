"""Offline tests for the local CPE dictionary snapshot (Phase 7 step 2)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from cpegen.dictionary import (
    HybridDictionary,
    LayeredDictionary,
    LocalDictionary,
    NIERecord,
    _neo4j_fetch,
    build_snapshot,
    layered_dictionary,
    load_nie_records,
    lookup_for,
    write_nie_record,
)
from cpegen.nvd import DictEntry


def _product(name, title="A title", deprecated=False):
    return {"cpe": {"cpeName": name, "cpeNameId": f"id-{name}",
                    "titles": [{"title": title, "lang": "en"}],
                    "deprecated": deprecated}}


CPES = [
    "cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*",
    "cpe:2.3:a:7-zip:7-zip:25.00:*:*:*:*:*:*:*",
    "cpe:2.3:a:notepad-plus-plus:notepad\\+\\+:8.9:*:*:*:*:*:*:*",
]


def _fake_fetch(pages):
    """Build a fetch(start, size) over a dict start_index -> products."""
    calls = []

    def fetch(start, size):
        calls.append(start)
        products = pages.get(start, [])
        return {"totalResults": sum(len(v) for v in pages.values()),
                "resultsPerPage": len(products), "products": products}

    fetch.calls = calls
    return fetch


def test_build_snapshot_writes_jsonl_gz_and_meta(tmp_path):
    out = tmp_path / "dict.jsonl.gz"
    fetch = _fake_fetch({0: [_product(c) for c in CPES[:2]],
                         2: [_product(CPES[2])]})
    meta = build_snapshot(out, fetch=fetch, page_size=2)
    assert meta["done"] and meta["fetched"] == 3 and meta["invalid"] == 0
    with gzip.open(out, "rt", encoding="utf-8") as f:
        lines = [json.loads(l) for l in f]
    assert [l["cpeName"] for l in lines] == CPES
    assert not out.with_suffix(out.suffix + ".part").exists()


def test_build_snapshot_resumes_from_checkpoint(tmp_path):
    out = tmp_path / "dict.jsonl.gz"
    part = out.with_suffix(out.suffix + ".part")
    meta_path = out.with_suffix(out.suffix + ".meta.json")
    # Simulate a run killed after the first page (2 of 3 entries).
    part.write_text("".join(
        json.dumps({"cpeName": c, "cpeNameId": f"id-{c}", "title": "t",
                    "deprecated": False}) + "\n" for c in CPES[:2]))
    meta_path.write_text(json.dumps(
        {"done": False, "resume_index": 2, "total": 3, "fetched": 2,
         "invalid": 0, "page_size": 2}))
    fetch = _fake_fetch({2: [_product(CPES[2])]})
    meta = build_snapshot(out, fetch=fetch, page_size=2)
    assert fetch.calls == [2]          # first page never re-fetched
    assert meta["fetched"] == 3
    with gzip.open(out, "rt", encoding="utf-8") as f:
        assert len(f.readlines()) == 3


def test_build_snapshot_counts_invalid_but_keeps_them(tmp_path):
    out = tmp_path / "dict.jsonl.gz"
    fetch = _fake_fetch({0: [_product("cpe:2.3:a:Bad:Upper:1:*:*:*:*:*:*:*")]})
    meta = build_snapshot(out, fetch=fetch, page_size=10)
    assert meta["invalid"] == 1 and meta["fetched"] == 1


def _snapshot(tmp_path) -> Path:
    out = tmp_path / "dict.jsonl.gz"
    build_snapshot(out, fetch=_fake_fetch({0: [_product(c) for c in CPES]}),
                   page_size=10)
    return out


def test_local_dictionary_exact_pair_lookup(tmp_path):
    d = LocalDictionary.load(_snapshot(tmp_path))
    assert d.size == 3
    hits = d.candidates_for("7-zip", "7-zip")
    assert {e.cpe_name for e in hits} == set(CPES[:2])
    assert d.hits == 1


def test_local_dictionary_binds_raw_values(tmp_path):
    # Raw product with specials must be bound before the index lookup.
    d = LocalDictionary.load(_snapshot(tmp_path))
    hits = d.candidates_for("notepad-plus-plus", "notepad++")
    assert len(hits) == 1 and hits[0].cpe_name == CPES[2]


def test_local_dictionary_vendor_fallback_dedups_to_reps(tmp_path):
    # On pair miss the fallback returns ONE representative per distinct
    # (vendor, product) pair — not every version. Classification of the
    # non-pair rules only reads vendor/product fields, and an
    # un-deduplicated fallback biased the similarity search (2026-08-11).
    d = LocalDictionary.load(_snapshot(tmp_path))
    hits = d.candidates_for("7-zip", "unknown_product")
    assert len(hits) == 1 and hits[0].cpe_name in {CPES[0], CPES[1]}
    assert d.candidates_for("no_such_vendor", "x") == []
    assert d.misses == 1


def test_local_dictionary_product_fallback_across_vendors(tmp_path):
    # The offline stand-in for the API keyword fallback: an unknown
    # vendor with a product the dictionary knows under OTHER vendors
    # must surface those entries — without this, M2B/M3/M1C are
    # unreachable offline (0 occurrences across the 10k RAW pilot).
    d = LocalDictionary.load(_snapshot(tmp_path))
    hits = d.candidates_for("some_new_vendor", "7-zip")
    assert len(hits) == 1
    assert hits[0].cpe_name in {CPES[0], CPES[1]}


def test_local_dictionary_union_vendor_and_product(tmp_path):
    # vendor known (7-zip) + product known under another vendor
    # (notepad++): the candidate set is the union of both sides, which
    # is what lets M1C ("vendor and product exist separately") fire.
    d = LocalDictionary.load(_snapshot(tmp_path))
    hits = d.candidates_for("7-zip", "notepad++")
    names = {e.cpe_name for e in hits}
    assert CPES[2] in names                 # product side
    assert names & {CPES[0], CPES[1]}       # vendor side


def _fake_post(rows):
    """Stub for the Neo4j HTTP transactional endpoint."""
    def post(statement, parameters):
        if statement.startswith("MATCH (p:Platform) RETURN count"):
            return {"results": [{"data": [{"row": [len(rows)]}]}]}
        skip, limit = parameters["skip"], parameters["limit"]
        page = rows[skip:skip + limit]
        return {"results": [{"data": [{"row": r} for r in page]}]}
    return post


def test_neo4j_fetch_yields_nvd_shaped_pages(tmp_path):
    rows = [
        ["cpe:2.3:a:7-zip:7-zip:26.01:*:*:*:*:*:*:*", "id-1", False,
         "7-zip", "7-zip", "26.01"],
        ["cpe:2.3:o:linux:linux_kernel:6.1:*:*:*:*:*:*:*", "id-2", True,
         "linux", "linux_kernel", "6.1"],
    ]
    fetch = _neo4j_fetch(post=_fake_post(rows))
    page = fetch(0, 1)
    assert page["totalResults"] == 2 and page["resultsPerPage"] == 1
    cpe = page["products"][0]["cpe"]
    assert cpe["cpeName"] == rows[0][0]
    assert cpe["titles"][0]["title"] == "7-zip 7-zip 26.01"
    # end-to-end: same build path as the NVD source, deprecated preserved
    out = tmp_path / "dict.jsonl.gz"
    meta = build_snapshot(out, fetch=fetch, source="neo4j", page_size=1)
    assert meta["fetched"] == 2 and meta["source"] == "neo4j"
    d = LocalDictionary.load(out)
    assert d.candidates_for("linux", "linux_kernel")[0].deprecated is True


class _StubClient:
    def __init__(self):
        self.calls = []
        self.entry = DictEntry("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*", "x", "t",
                               False)

    def candidates_for(self, vendor, product):
        self.calls.append(("cand", vendor, product))
        return [self.entry]

    def keyword(self, kw):
        self.calls.append(("kw", kw))
        return [self.entry]


def test_hybrid_local_hit_never_touches_client(tmp_path):
    stub = _StubClient()
    h = HybridDictionary(LocalDictionary.load(_snapshot(tmp_path)), stub)
    assert h.candidates_for("7-zip", "7-zip")
    assert stub.calls == [] and h.api_fallbacks == 0


def test_hybrid_falls_back_to_client_on_miss(tmp_path):
    stub = _StubClient()
    h = HybridDictionary(LocalDictionary.load(_snapshot(tmp_path)), stub)
    assert h.candidates_for("no_such_vendor", None) == [stub.entry]
    assert h.api_fallbacks == 1
    assert h.keyword("seven zip") == [stub.entry]
    assert ("kw", "seven zip") in stub.calls


# ------------------------------------------------------- WP2: NIE records

def _nie(cpe, origin="motherhacker", human="laia", ts="2026-08-13T10:00:00Z",
        evidence="", titles=""):
    return NIERecord(cpe=cpe, origin=origin, human_identity=human,
                     timestamp=ts, evidence=evidence,
                     motivating_titles=titles)


def test_nie_record_roundtrip_csv(tmp_path):
    path = tmp_path / "custom.csv"
    r1 = _nie("cpe:2.3:a:acme:widget:2.0:*:*:*:*:*:*:*",
              evidence="human confirmed", titles="Acme Widget 2.0;Widget 2")
    r2 = _nie("cpe:2.3:a:acme:gadget:1.0:*:*:*:*:*:*:*", origin="rawTFM")
    write_nie_record(path, r1)
    write_nie_record(path, r2)
    loaded = load_nie_records(path)
    assert [r.cpe for r in loaded] == [r1.cpe, r2.cpe]
    assert loaded[0].human_identity == "laia"
    assert loaded[1].origin == "rawTFM"


def test_load_nie_records_drops_malformed_cpe(tmp_path):
    path = tmp_path / "custom.csv"
    write_nie_record(path, _nie("cpe:2.3:a:acme:widget:2.0:*:*:*:*:*:*:*"))
    write_nie_record(path, _nie("not-a-cpe-at-all"))
    loaded = load_nie_records(path)
    assert len(loaded) == 1
    assert loaded[0].cpe == "cpe:2.3:a:acme:widget:2.0:*:*:*:*:*:*:*"


def test_local_dictionary_from_nie_builds_lookup():
    records = [_nie("cpe:2.3:a:acme:widget:2.0:*:*:*:*:*:*:*",
                    titles="Acme Widget 2.0")]
    d = LocalDictionary.from_nie(records)
    hits = d.candidates_for("acme", "widget")
    assert len(hits) == 1
    assert hits[0].cpe_name == records[0].cpe
    # same clean+Dice machinery as the NVD layer: canonicalizes too.
    lk = d.lookup("acme", "widget", title="Acme Widget 2.0")
    assert lk.candidates and lk.resolution is not None


# --------------------------------------------------- WP2: layered lookup

def test_layered_dictionary_no_regression_with_empty_layers(tmp_path):
    base = LocalDictionary.load(_snapshot(tmp_path))
    layered = layered_dictionary(base)  # no custom paths -> pass-through
    direct = base.lookup("7-zip", "7-zip", title="7-Zip 26.01")
    wrapped = layered.lookup("7-zip", "7-zip", title="7-Zip 26.01")
    assert wrapped.candidates == direct.candidates
    assert wrapped.resolution == direct.resolution
    assert wrapped.source == direct.source
    assert wrapped.dictionary_source == "nvd"

    # a genuine miss stays a miss, with no dictionary_source claimed.
    miss = layered.lookup("no_such_vendor", "no_such_product", title="x")
    assert miss.candidates == []
    assert miss.dictionary_source == ""


def test_layered_dictionary_falls_through_to_motherhacker(tmp_path):
    base = LocalDictionary.load(_snapshot(tmp_path))
    mh = LocalDictionary.from_nie([
        _nie("cpe:2.3:a:newvendor:newproduct:1.0:*:*:*:*:*:*:*")])
    layered = LayeredDictionary(base, motherhacker=mh)
    lk = layered.lookup("newvendor", "newproduct", title="NewVendor NewProduct 1.0")
    assert lk.candidates
    assert lk.dictionary_source == "motherhacker"


def test_layered_dictionary_falls_through_to_origin(tmp_path):
    base = LocalDictionary.load(_snapshot(tmp_path))
    origin_dict = LocalDictionary.from_nie([
        _nie("cpe:2.3:a:clienta:special_tool:1.0:*:*:*:*:*:*:*",
            origin="ClientA")])
    layered = LayeredDictionary(base, origin=origin_dict, origin_name="ClientA")
    lk = layered.lookup("clienta", "special_tool",
                        title="ClientA Special Tool 1.0")
    assert lk.candidates
    assert lk.dictionary_source == "ClientA"


def test_layered_dictionary_nvd_wins_over_motherhacker_on_hit(tmp_path):
    # The order is fixed: NVD answers first even when the other layers
    # also know the pair (playbook §3 — "NVD -> MotherHacker -> origen").
    base = LocalDictionary.load(_snapshot(tmp_path))
    mh = LocalDictionary.from_nie([
        _nie("cpe:2.3:a:7-zip:7-zip:99.0:*:*:*:*:*:*:*")])
    layered = LayeredDictionary(base, motherhacker=mh)
    lk = layered.lookup("7-zip", "7-zip", title="7-Zip")
    assert lk.dictionary_source == "nvd"
    assert all(e.cpe_name != "cpe:2.3:a:7-zip:7-zip:99.0:*:*:*:*:*:*:*"
              for e in lk.candidates)


def test_layered_dictionary_candidates_for_and_keyword(tmp_path):
    base = LocalDictionary.load(_snapshot(tmp_path))
    mh = LocalDictionary.from_nie([
        _nie("cpe:2.3:a:newvendor:newproduct:1.0:*:*:*:*:*:*:*")])
    layered = LayeredDictionary(base, motherhacker=mh)
    assert layered.candidates_for("newvendor", "newproduct")
    assert layered.candidates_for("no_such_vendor", "no_such_product") == []
    stub = _StubClient()
    hybrid_base = HybridDictionary(LocalDictionary.load(_snapshot(tmp_path)),
                                   stub)
    layered_over_hybrid = LayeredDictionary(hybrid_base, motherhacker=mh)
    assert layered_over_hybrid.keyword("seven zip") == [stub.entry]


def test_layered_dictionary_works_through_lookup_for(tmp_path):
    # The pipeline never calls LayeredDictionary directly — it goes
    # through the same uniform lookup_for() every other client uses.
    base = LocalDictionary.load(_snapshot(tmp_path))
    layered = layered_dictionary(base)
    lk = lookup_for(layered, "7-zip", "7-zip", title="7-Zip 26.01")
    assert lk.dictionary_source == "nvd"
