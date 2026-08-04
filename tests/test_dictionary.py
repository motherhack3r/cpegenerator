"""Offline tests for the local CPE dictionary snapshot (Phase 7 step 2)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from cpegen.dictionary import (
    HybridDictionary,
    LocalDictionary,
    build_snapshot,
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


def test_local_dictionary_vendor_fallback_and_miss(tmp_path):
    d = LocalDictionary.load(_snapshot(tmp_path))
    assert len(d.candidates_for("7-zip", "unknown_product")) == 2  # vendor
    assert d.candidates_for("no_such_vendor", "x") == []
    assert d.misses == 1


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
