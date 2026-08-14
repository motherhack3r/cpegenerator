"""Tests for the shared title_features module (WP3, spec §8.1)."""

from __future__ import annotations

from cpegen.dictionary import LocalDictionary, build_snapshot
from cpegen.title_features import features, is_hard


def _product(name, title="A title"):
    return {"cpe": {"cpeName": name, "cpeNameId": f"id-{name}",
                    "titles": [{"title": title, "lang": "en"}],
                    "deprecated": False}}


CPES = [
    "cpe:2.3:a:rockwellautomation:factorytalk_linx:6.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:microsoft:sql_server:2019:*:*:*:*:*:*:*",
    "cpe:2.3:a:microsoft:sql_server:2017:*:*:*:*:*:*:*",
]


def _fake_fetch(pages):
    def fetch(start, size):
        products = pages.get(start, [])
        return {"totalResults": sum(len(v) for v in pages.values()),
                "resultsPerPage": len(products), "products": products}
    return fetch


def _dictionary(tmp_path) -> LocalDictionary:
    out = tmp_path / "dict.jsonl.gz"
    build_snapshot(out, fetch=_fake_fetch({0: [_product(c) for c in CPES]}),
                   page_size=10)
    return LocalDictionary.load(out)


# ---------------------------------------------------------- dictionary-free

def test_has_parens():
    assert features("SIMATIC STEP 7 (TIA Portal)")["has_parens"]
    assert not features("SIMATIC STEP 7")["has_parens"]


def test_has_arch_locale_tokens():
    assert features("7-Zip 26.01 (x64)")["has_arch_locale_tokens"]
    assert features("Some App en-US")["has_arch_locale_tokens"]
    assert features("Some App amd64")["has_arch_locale_tokens"]
    assert not features("7-Zip 26.01")["has_arch_locale_tokens"]


def test_versioned_family():
    assert features("Microsoft SQL Server 2019")["versioned_family"]
    assert not features("Acrobat Reader")["versioned_family"]
    # bare single-token "product" has nothing to strip a release off of
    assert not features("2019")["versioned_family"]


def test_length_and_numeric_tokens():
    f = features("7-Zip 26 01 x64")
    assert f["length"] == len("7-Zip 26 01 x64")
    assert f["n_numeric_tokens"] == 3  # "7", "26" and "01" are pure-digit tokens


def test_vendor_and_dice_false_without_dictionary():
    f = features("Rockwell Automation FactoryTalk Linx CommDTM")
    assert f["vendor_in_alias_table"] is False
    assert f["direct_dice_ge_085"] is False


def test_is_hard_criteria():
    assert is_hard("Microsoft SQL Server 2019")       # versioned family
    assert is_hard("Some Driver Package")              # driver/OEM token
    assert is_hard("Café Manager")                     # non-ASCII
    assert is_hard("App x64")                           # arch token
    assert not is_hard("Acrobat Reader")


# -------------------------------------------------------- dictionary-backed

def test_vendor_in_alias_table_true_with_dictionary(tmp_path):
    d = _dictionary(tmp_path)
    f = features("Rockwell Automation FactoryTalk Linx", dictionary=d)
    assert f["vendor_in_alias_table"] is True


def test_vendor_in_alias_table_false_for_unknown_vendor(tmp_path):
    d = _dictionary(tmp_path)
    f = features("Totally Unknown Vendor Thing", dictionary=d)
    assert f["vendor_in_alias_table"] is False


def test_direct_dice_true_for_near_verbatim_title(tmp_path):
    d = _dictionary(tmp_path)
    f = features("microsoft sql server 2019", dictionary=d)
    assert f["direct_dice_ge_085"] is True


def test_direct_dice_false_for_unrelated_title(tmp_path):
    d = _dictionary(tmp_path)
    f = features("Totally Unrelated Freeware Tool", dictionary=d)
    assert f["direct_dice_ge_085"] is False


def test_features_never_crashes_without_dictionary_on_edge_titles():
    for title in ("", "   ", "123", "!!!", "日本語のタイトル"):
        f = features(title)
        assert isinstance(f, dict) and len(f) == 7
