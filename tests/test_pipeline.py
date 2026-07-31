"""Tests for gold-set parsing, extraction parsing and the offline pipeline."""

import json

from cpegen.extractor import MockProvider, _parse_response, extract
from cpegen.goldset import parse_annotation
from cpegen.pipeline import build_wfn, process_title
from cpegen.nvd import NVDClient


def test_parse_annotation():
    g = parse_annotation(
        "in2code femanager 5.5.1 for typo3",
        "[in2code](cpe_vendor) [femanager](cpe_product) [5.5.1](cpe_version) for typo3",
    )
    assert g.vendor == "in2code"
    assert g.product == "femanager"
    assert g.version == "5.5.1"
    assert g.target_sw == "typo3"


def test_parse_annotation_multiword_product():
    g = parse_annotation(
        "gecad technologies axigen mail server 3.0 beta",
        "[gecad](cpe_vendor) technologies [axigen mail server](cpe_product) [3.0](cpe_version) beta",
    )
    assert g.product == "axigen mail server"
    assert g.target_sw is None


def test_parse_response_strict_json():
    ext = _parse_response("t", '{"vendor": "acme", "product": "thing", '
                          '"version": "1.0", "confidence": 0.9}')
    assert ext.vendor == "acme"
    assert ext.error is None


def test_parse_response_wrapped_json():
    ext = _parse_response("t", 'Here you go:\n{"vendor": "acme", "product": "p", '
                          '"version": null, "confidence": 1.5}\nDone.')
    assert ext.vendor == "acme"
    assert ext.version is None
    assert ext.confidence == 1.0  # clamped


def test_parse_response_garbage():
    ext = _parse_response("t", "sorry, I cannot help")
    assert ext.error is not None


def test_mock_provider_extraction():
    ext = extract(MockProvider(), "in2code femanager 5.5.1 for typo3")
    assert ext.vendor == "in2code"
    assert ext.product == "femanager"
    assert ext.version == "5.5.1"
    assert ext.target_sw == "typo3"


def test_build_wfn_binds_valid_cpe():
    from cpegen.validator import validate_formatted_string
    ext = extract(MockProvider(), "gecad axigen mail server 3.0 beta")
    w = build_wfn(ext)
    assert w is not None
    assert validate_formatted_string(w.bind()).ok


def test_process_title_offline(tmp_path):
    nvd = NVDClient(cache_path=tmp_path / "cache.json", offline=True)
    row = process_title("in2code femanager 5.5.1 for typo3", MockProvider(), nvd)
    assert row.valid
    assert row.cpe == "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"
    assert row.rule  # classified even with no candidates (M3 catch-all)


def test_nvd_cache_roundtrip(tmp_path):
    nvd = NVDClient(cache_path=tmp_path / "cache.json", offline=True)
    # seed the cache manually, as the warm-cache offline flow does
    query = json.dumps({"cpeMatchString": "cpe:2.3:*:in2code:femanager"}, sort_keys=True)
    nvd._cache_put(query, [{
        "cpeName": "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*",
        "cpeNameId": "abc", "deprecated": False,
        "titles": [{"title": "in2code femanager 5.5.1 for TYPO3", "lang": "en"}],
    }])
    entries = nvd.match_string("cpe:2.3:*:in2code:femanager")
    assert len(entries) == 1
    assert entries[0].cpe_name.endswith(":typo3:*:*")
