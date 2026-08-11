"""Tests for the M1-M3 classification cascade."""

from cpegen.matcher import classify, levenshtein, similarity
from cpegen.nvd import DictEntry
from cpegen.wfn import WFN


def entry(cpe: str, deprecated: bool = False) -> DictEntry:
    return DictEntry(cpe_name=cpe, cpe_name_id="x", title="t", deprecated=deprecated)


def wfn(vendor="in2code", product="femanager", version="5.5.1", **kw) -> WFN:
    return WFN(part="a", vendor=vendor, product=product, version=version, **kw)


def test_levenshtein():
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("", "abc") == 3
    assert levenshtein("same", "same") == 0


def test_similarity_bounds():
    assert similarity("abc", "abc") == 1.0
    assert similarity("", "") == 1.0
    assert 0.0 <= similarity("abc", "xyz") <= 1.0


def test_m1_exact_formatted_string():
    w = wfn(target_sw="typo3")
    dict_entries = [entry(w.bind())]
    res = classify(w, dict_entries)
    assert res.rule == "M1"
    assert res.similarity == 1.0
    assert res.high_confidence


def test_m1a_same_vpv_other_attrs_differ():
    w = wfn()
    dict_entries = [entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*")]
    # generated has target_sw=ANY, dictionary has typo3 -> not M1, but v:p:v match
    res = classify(w, dict_entries)
    assert res.rule == "M1A"
    assert res.similarity == 1.0


def test_m1b_new_version():
    w = wfn(version="9.9.9")
    dict_entries = [entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*")]
    res = classify(w, dict_entries)
    assert res.rule == "M1B"
    assert res.high_confidence


def test_m1c_vendor_and_product_exist_separately():
    w = wfn(vendor="google", product="femanager", version="1.0")
    dict_entries = [
        entry("cpe:2.3:a:google:protobuf:3.6.1:*:*:*:*:*:*:*"),
        entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*"),
    ]
    res = classify(w, dict_entries)
    assert res.rule == "M1C"


def test_m2_similar_product():
    w = wfn(product="femanagers")  # 1 edit away
    dict_entries = [entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*")]
    res = classify(w, dict_entries)
    assert res.rule == "M2"
    assert not res.high_confidence


def test_m3_similar_vendor():
    w = wfn(vendor="in2codee")
    dict_entries = [entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*")]
    res = classify(w, dict_entries)
    assert res.rule == "M3"


def test_m2b_new_vendor():
    w = wfn(vendor="totally_new_vendor")
    dict_entries = [entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*")]
    res = classify(w, dict_entries)
    assert res.rule == "M2B"


def test_no_candidates_is_m4():
    # v2 split (2026-08-11): no dictionary signal at all is its own
    # bucket, not "M3 Other candidates" — a row with zero candidates
    # must not wear the same label as a real vendor-similarity match.
    res = classify(wfn(), [])
    assert res.rule == "M4"
    assert res.similarity == 0.0
    assert res.matched_cpe is None


def test_m2_vendor_known_product_new():
    # The HP DropBoxPlugin case (10k RAW pilot row 332): vendor exists
    # in the dictionary, product does not, similarity under threshold.
    # Baseline semantics: "New product candidate" (M2), with the
    # similarity reported as signal and no matched_cpe cited.
    w = wfn(vendor="hp", product="dropboxplugin", version="28.11")
    dict_entries = [entry("cpe:2.3:a:hp:deskjet_taplugin:60.0.196.0:*:*:*:*:*:*:*")]
    res = classify(w, dict_entries)
    assert res.rule == "M2"
    assert res.matched_cpe is None          # below threshold: no citation
    assert 0.0 < res.similarity <= 0.8      # but the signal is reported
    assert not res.high_confidence


def test_confidence_does_not_gate_classification():
    # Decision 2026-07-24: classification is deterministic; an exact
    # dictionary hit is M1 no matter what the extractor's confidence was
    # (the 0.8-gate once demoted 9 exact matches to M2 on a real run).
    w = wfn(target_sw="typo3")
    dict_entries = [entry(w.bind())]
    res = classify(w, dict_entries)
    assert res.rule == "M1"
    assert res.similarity == 1.0


def test_deprecated_entries_ignored():
    w = wfn(target_sw="typo3")
    dict_entries = [entry(w.bind(), deprecated=True)]
    res = classify(w, dict_entries)
    assert res.rule != "M1"


def test_m2_above_threshold_cites_match():
    w = wfn(product="femanagers")  # 1 edit away, sim > 0.8
    dict_entries = [entry("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*")]
    res = classify(w, dict_entries)
    assert res.rule == "M2"
    assert res.matched_cpe is not None
    assert res.similarity > 0.8
