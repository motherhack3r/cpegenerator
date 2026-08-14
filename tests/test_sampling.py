"""Tests for the WP3 stratified sampler and pre-annotation queue builder."""

from __future__ import annotations

import csv

from cpegen.dictionary import LocalDictionary, build_snapshot
from cpegen.sampling import (
    QUEUE_FIELDS,
    build_queue_rows,
    read_titles,
    sample_stratified,
    write_queue_csv,
)


def _product(name, title="A title"):
    return {"cpe": {"cpeName": name, "cpeNameId": f"id-{name}",
                    "titles": [{"title": title, "lang": "en"}],
                    "deprecated": False}}


def _dictionary(tmp_path):
    out = tmp_path / "dict.jsonl.gz"

    def fetch(start, size):
        products = [_product(
            "cpe:2.3:a:microsoft:sql_server:2019:*:*:*:*:*:*:*")] if start == 0 else []
        return {"totalResults": 1, "resultsPerPage": len(products),
                "products": products}

    build_snapshot(out, fetch=fetch, page_size=10)
    return LocalDictionary.load(out)


EASY = [f"Freeware Tool Number{i}" for i in range(60)]
HARD = ["Microsoft SQL Server 2019", "App x64", "Café Manager",
       "Some Driver Package", "Windows en-US Pack"]
TITLES = EASY + HARD


def test_sample_stratified_is_deterministic():
    a = sample_stratified(TITLES, seed=42, n_random=10, n_hard=3)
    b = sample_stratified(TITLES, seed=42, n_random=10, n_hard=3)
    assert a.random_titles == b.random_titles
    assert a.hard_titles == b.hard_titles


def test_sample_stratified_different_seed_differs():
    a = sample_stratified(TITLES, seed=1, n_random=10, n_hard=3)
    b = sample_stratified(TITLES, seed=2, n_random=10, n_hard=3)
    assert a.random_titles != b.random_titles or a.hard_titles != b.hard_titles


def test_sample_stratified_hard_and_random_disjoint():
    s = sample_stratified(TITLES, seed=7, n_random=60, n_hard=5)
    assert set(s.random_titles) & set(s.hard_titles) == set()
    assert len(s.hard_titles) == 5
    assert s.hard_population == len(HARD)
    assert s.population == len(TITLES)


def test_sample_stratified_dedupes_input():
    s = sample_stratified(TITLES + TITLES, seed=7, n_random=100, n_hard=100)
    assert s.population == len(TITLES)


def test_sample_stratified_caps_when_population_small():
    small = ["A", "B", "Microsoft SQL Server 2019"]
    s = sample_stratified(small, seed=1, n_random=70, n_hard=30)
    assert len(s.random_titles) + len(s.hard_titles) <= len(small)
    assert s.hard_population == 1


def test_build_queue_rows_without_dictionary():
    s = sample_stratified(TITLES, seed=42, n_random=5, n_hard=2)
    rows = build_queue_rows(s, "rawTest", dictionary=None)
    assert len(rows) == 7
    assert {r["stratum"] for r in rows} == {"random", "hard"}
    for r in rows:
        assert r["origin"] == "rawTest"
        assert r["suggested_vendor"] == ""
        assert r["annotated_title"] == ""


def test_build_queue_rows_with_dictionary_suggests(tmp_path):
    d = _dictionary(tmp_path)
    s = sample_stratified(["microsoft sql server 2019"], seed=1,
                          n_random=1, n_hard=0)
    rows = build_queue_rows(s, "rawTest", dictionary=d)
    assert len(rows) == 1
    row = rows[0]
    assert row["suggested_vendor"] == "microsoft"
    assert row["suggested_product"] == "sql_server"
    assert row["dice"] != ""


def test_write_queue_csv_roundtrip(tmp_path):
    s = sample_stratified(TITLES, seed=42, n_random=5, n_hard=2)
    rows = build_queue_rows(s, "rawTest", dictionary=None)
    out = tmp_path / "queue.csv"
    write_queue_csv(rows, out)
    with open(out, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == list(QUEUE_FIELDS)
        read_rows = list(reader)
    assert len(read_rows) == 7
    assert {r["title"] for r in read_rows} == set(s.titles)


def test_read_titles_no_header(tmp_path):
    p = tmp_path / "titles.csv"
    p.write_text("Foo Bar 1.0\nBaz Qux 2.0\n", encoding="utf-8")
    assert read_titles(p) == ["Foo Bar 1.0", "Baz Qux 2.0"]


def test_read_titles_inventory_header(tmp_path):
    p = tmp_path / "inventory.csv"
    p.write_text("title,name,version,vendor,source\n"
                "7-Zip 26.01,7-Zip,26.01,Igor Pavlov,hklm64\n",
                encoding="utf-8")
    assert read_titles(p) == ["7-Zip 26.01"]
