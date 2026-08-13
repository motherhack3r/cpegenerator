"""Offline tests for the clean+Dice canonicalization layer (WP1 step 2).

Everything here runs without network or credentials: the dictionary is a
synthetic snapshot built through the same ``build_snapshot`` path the
real one uses.

The reference numbers in :func:`test_dice_reproduces_apoc_reference_cases`
are the seven validated cases of `.ideas/CPE_LOOKUP_PLAYBOOK.md` §8, run
against the real KGCS with ``apoc.text.sorensenDiceSimilarity``. They are
the acceptance criterion of the port: a Python reimplementation that does
not reproduce them is not the same function.
"""

from __future__ import annotations

import csv
import random

import pytest

from cpegen.dictionary import (
    LEGAL_SUFFIXES,
    LocalDictionary,
    PairIndex,
    VendorAliases,
    build_snapshot,
    write_alias_table,
)
from cpegen.matcher import (
    MIN_DICE,
    ScoredPair,
    canonicalize,
    classify,
    clean,
    decide,
    dice,
    family_stem,
    family_token,
    similarity,
    version_token_in_title,
)
from cpegen.nvd import DictEntry
from cpegen.wfn import WFN

# --------------------------------------------------------------- clean


def test_clean_is_symmetric_across_separator_conventions():
    # The test docs/match-rules.md asks for: one key, whatever the
    # dictionary's separator convention happens to be (playbook §2.1).
    assert (clean("Rockwell Automation") == clean("rockwellautomation")
            == clean("rockwell_automation") == clean("rockwell-automation")
            == "rockwellautomation")


def test_clean_neutralizes_cpe_escaping():
    assert (clean(r"simatic_step_7_\(tia_portal\)")
            == clean("SIMATIC STEP 7 (TIA Portal)")
            == "simaticstep7tiaportal")


def test_clean_keeps_only_ascii_alphanumerics():
    assert clean("AT&T, Inc.") == "attinc"
    assert clean("Café 3.0") == "caf30"     # like apoc.text.clean: ASCII only
    assert clean("") == ""


# ---------------------------------------------------------------- dice

REFERENCE_CASES = [
    # (title, vendor, product, apoc dice) — playbook §8, Query A
    ("Microsoft SQL Server 2019", "microsoft", "sql_server_2019", 1.000),
    ("Schneider Electric EcoStruxure Control Expert 15.0",
     "schneider-electric", "ecostruxure_control_expert", 0.964),
    ("Siemens SIMATIC STEP 7 (TIA Portal) V17", "siemens",
     r"simatic_step_7_\(tia_portal\)", 0.947),
    ("VMware vCenter Server 7.0", "vmware", "vcenter_server", 0.947),
    ("Rockwell Automation FactoryTalk EnerGyMetrix 3.0",
     "rockwellautomation", "factorytalk_energrymetrix", 0.940),
    ("Fortinet FortiOS 7.2.5", "fortinet", "fortios", 0.903),
    ("Rockwell Automation FactoryTalk Linx CommDTM V1.4.0",
     "rockwellautomation", "factorytalk_linx", 0.853),
]


@pytest.mark.parametrize("title,vendor,product,expected", REFERENCE_CASES)
def test_dice_reproduces_apoc_reference_cases(title, vendor, product,
                                              expected):
    assert round(dice(clean(title), clean(vendor + product)), 3) == expected


def test_dice_tolerates_extra_title_tokens_better_than_levenshtein():
    # The reason the playbook chose Dice: "CommDTM" and "V1.4.0" are not
    # edit errors, they are tokens the CPE simply does not model.
    q = clean("Rockwell Automation FactoryTalk Linx CommDTM V1.4.0")
    k = clean("rockwellautomation" + "factorytalk_linx")
    assert round(dice(q, k), 3) == 0.853
    assert round(similarity(q, k), 3) == 0.750


def test_dice_is_symmetric_and_bounded():
    assert dice("abcd", "abcd") == 1.0
    assert dice("", "") == 0.0
    assert dice("abc", "") == 0.0
    assert dice("abcd", "cdef") == dice("cdef", "abcd")
    assert 0.0 <= dice("abcdef", "defabc") <= 1.0


def test_index_fast_dice_equals_the_reference_implementation():
    # The index scores with a hand-rolled single walk over the key (no
    # Counter allocation) because it runs thousands of times per title.
    # It has to stay bit-identical to matcher.dice, so the port's
    # acceptance criterion keeps covering what actually runs.
    from cpegen.dictionary import _dice_from_counts
    from cpegen.matcher import bigrams

    rng = random.Random(20260813)
    for _ in range(2000):
        a = "".join(rng.choice("abcab12_") for _ in range(rng.randint(0, 20)))
        b = "".join(rng.choice("abcab12_") for _ in range(rng.randint(0, 20)))
        qc = bigrams(a)
        na, nb = sum(qc.values()), max(len(b) - 1, 0)
        expected = dice(a, b) if na and nb else 0.0
        assert _dice_from_counts(qc, na, b, nb) == pytest.approx(expected)


def test_sql_server_family_is_the_pathological_margin():
    q = clean("Microsoft SQL Server 2019")
    assert round(dice(q, clean("microsoft" + "sql_server_2019")), 3) == 1.000
    assert round(dice(q, clean("microsoft" + "sql_server_2017")), 3) == 0.952


# ------------------------------------------------------- versioned family


def test_family_token_and_stem():
    assert family_token("sql_server_2019") == "2019"
    assert family_stem("sql_server_2019") == "sql_server"
    assert family_token("acrobat_reader") is None
    assert family_token("2019") is None      # a bare version is not a family
    assert family_token("acrobat_9") == "9"


def test_version_token_in_title():
    assert version_token_in_title("2019", "Microsoft SQL Server 2019")
    assert version_token_in_title("2019", "MicrosoftSQLServer2019")
    assert not version_token_in_title("2017", "Microsoft SQL Server 2019")
    assert version_token_in_title("7", "SIMATIC STEP 7 (TIA Portal) V17")
    # short tokens must be standalone: no substring luck
    assert not version_token_in_title("7", "Windows 10")


def _pair(vendor, product, score, part="a", cpes=1, deprecated=False):
    return ScoredPair(vendor, product, part, score, cpes, deprecated)


def test_decide_auto_requires_score_and_margin():
    res = decide([_pair("vmware", "vcenter_server", 0.947),
                  _pair("vmware", "vcenter_converter", 0.773)],
                 "VMware vCenter Server 7.0")
    assert res.decision == "auto" and res.accepted
    assert res.winner.product == "vcenter_server"
    assert round(res.margin, 3) == 0.174


def test_decide_thin_margin_is_flagged_but_still_accepted():
    res = decide([_pair("v", "alpha", 0.90), _pair("v", "beta", 0.83)],
                 "alpha thing")
    assert res.decision == "flagged" and res.accepted
    assert "thin_margin" in res.review_reasons


def test_decide_narrow_margin_needs_human_review():
    res = decide([_pair("v", "alpha", 0.90), _pair("v", "beta", 0.88)],
                 "alpha thing")
    assert res.decision == "review" and not res.accepted
    assert "narrow_margin" in res.review_reasons


def test_decide_weak_band_is_never_accepted():
    res = decide([_pair("v", "alpha", 0.70)], "alpha")
    assert res.decision == "weak" and not res.accepted


def test_decide_drops_everything_under_the_floor():
    res = decide([_pair("v", "alpha", MIN_DICE - 0.01)], "alpha")
    assert res.winner is None and res.decision == "none"


def test_versioned_family_without_evidence_is_never_automatic():
    # The failure mode the hard rule exists for: assigning the wrong year
    # with high confidence (playbook §7.1).
    res = decide([_pair("microsoft", "sql_server_2019", 0.98),
                  _pair("microsoft", "sql_server_2017", 0.95)],
                 "Microsoft SQL Server")
    assert res.decision == "review" and not res.accepted
    assert "versioned_family" in res.review_reasons


def test_versioned_family_picks_the_sibling_the_title_names():
    res = decide([_pair("microsoft", "sql_server_2019", 1.0),
                  _pair("microsoft", "sql_server_2017", 0.952)],
                 "Microsoft SQL Server 2017")
    assert res.winner.product == "sql_server_2017"
    assert res.family_verified


def test_verified_family_margin_ignores_its_own_siblings():
    # 0.048 against ...2017 must not send a title that literally says
    # 2019 to human review: the deterministic token check replaced the
    # margin for exactly this comparison.
    res = decide([_pair("microsoft", "sql_server_2019", 1.0),
                  _pair("microsoft", "sql_server_2017", 0.952),
                  _pair("microsoft", "office", 0.40)],
                 "Microsoft SQL Server 2019")
    assert res.family_verified and res.decision == "auto"
    assert res.runner_up is None or res.runner_up.product != "sql_server_2017"


def test_deprecated_loses_ties_and_is_flagged():
    res = decide([_pair("v", "alpha", 0.95, deprecated=True),
                  _pair("v", "alpha", 0.95)], "alpha")
    assert res.winner.deprecated is False
    res2 = decide([_pair("v", "alpha", 0.95, deprecated=True)], "alpha")
    assert res2.winner.deprecated is True
    assert "deprecated" in res2.review_reasons


# ------------------------------------------------------------------ part


def test_part_is_taken_from_the_dictionary_not_assumed():
    res = decide([_pair("fortinet", "fortios", 0.903, part="o")],
                 "Fortinet FortiOS 7.2.5")
    assert res.winner.part == "o"
    assert not res.part_ambiguous


def test_multi_part_pair_uses_title_evidence():
    cands = [_pair("siemens", "simatic_step_7", 0.95, part="a", cpes=40),
             _pair("siemens", "simatic_step_7", 0.95, part="h", cpes=3)]
    res = decide(cands, "Siemens SIMATIC STEP 7 hardware appliance")
    assert res.winner.part == "h" and not res.part_ambiguous


def test_multi_part_pair_without_evidence_is_flagged_not_guessed():
    cands = [_pair("siemens", "simatic_step_7", 0.95, part="a", cpes=40),
             _pair("siemens", "simatic_step_7", 0.95, part="h", cpes=3)]
    res = decide(cands, "Siemens SIMATIC STEP 7 V17")
    assert res.part_ambiguous
    assert "part_ambiguous" in res.review_reasons
    assert res.decision == "flagged" and res.accepted   # flagged, not lost
    assert res.winner.part == "a"                       # highest volume


# ------------------------------------------------------------- classify


def _entry(cpe, deprecated=False):
    return DictEntry(cpe_name=cpe, cpe_name_id="x", title="t",
                     deprecated=deprecated)


def test_classify_canonicalizes_an_accepted_pair_into_m1x():
    # Failure mode 2 of the spec: the reader read "Rockwell Automation"
    # perfectly and the old matcher still lost the match because the
    # dictionary spells it "rockwellautomation".
    wfn = WFN(part="a", vendor="rockwell_automation",
              product="factorytalk_linx", version="1.4.0")
    entries = [_entry("cpe:2.3:a:rockwellautomation:factorytalk_linx:"
                      "6.11:*:*:*:*:*:*:*")]
    res = decide([_pair("rockwellautomation", "factorytalk_linx", 0.853),
                  _pair("rockwellautomation", "factorytalk_view", 0.70)],
                 "Rockwell Automation FactoryTalk Linx CommDTM V1.4.0")
    before = classify(wfn, entries)
    after = classify(wfn, entries, title="Rockwell Automation FactoryTalk "
                                         "Linx CommDTM V1.4.0",
                     resolution=res)
    assert before.rule == "M3"   # product matched, vendor merely similar
    assert after.rule == "M1B" and after.high_confidence
    assert after.canonical_vendor == "rockwellautomation"
    assert after.decision == "auto" and after.dice == 0.853


def test_classify_reports_signals_even_when_not_accepted():
    wfn = WFN(part="a", vendor="acme", product="widget", version="1.0")
    res = decide([_pair("acme2", "widget2", 0.70)], "acme widget")
    out = classify(wfn, [], title="acme widget", resolution=res)
    assert out.rule == "M4"                    # no canonicalization
    assert out.canonical_vendor == "acme"      # the WFN's own value
    assert out.decision == "weak" and out.dice == 0.7
    assert out.needs_review and "weak_score" in out.review_reason


def test_canonicalize_corrects_part_on_a_pair_it_did_not_have_to_accept():
    # Same pair, so nothing is being rewritten — but part 'a' was an
    # assumption and the dictionary says otherwise.
    wfn = WFN(part="a", vendor="fortinet", product="fortios", version="7.2.5")
    res = decide([_pair("fortinet", "fortios", 0.70, part="o")],
                 "Fortinet FortiOS 7.2.5")
    assert not res.accepted
    assert canonicalize(wfn, res).part == "o"


def test_canonicalize_is_a_noop_without_a_resolution():
    wfn = WFN(part="a", vendor="acme", product="widget")
    assert canonicalize(wfn, None) is wfn


# --------------------------------------------------- index and aliases

SNAPSHOT_CPES = [
    "cpe:2.3:a:rockwellautomation:factorytalk_energrymetrix:3.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:rockwellautomation:factorytalk_linx:6.11:*:*:*:*:*:*:*",
    "cpe:2.3:a:schneider-electric:ecostruxure_control_expert:15.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:schneider_electric:ecostruxure_machine_expert:1.2:*:*:*:*:*:*:*",
    "cpe:2.3:a:microsoft:sql_server_2019:15.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:microsoft:sql_server_2017:14.0:*:*:*:*:*:*:*",
    "cpe:2.3:o:fortinet:fortios:7.2.5:*:*:*:*:*:*:*",
    "cpe:2.3:a:adobe:acrobat_reader_dc:21.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:hp:deskjet_taplugin:60.0:*:*:*:*:*:*:*",
    "cpe:2.3:a:siemens:simatic_step_7:17.0:*:*:*:*:*:*:*",
    "cpe:2.3:h:siemens:simatic_step_7:-:*:*:*:*:*:*:*",
    "cpe:2.3:a:legacyvendor:legacy_tool:1.0:*:*:*:*:*:*:*",
]
DEPRECATED = {"cpe:2.3:a:legacyvendor:legacy_tool:1.0:*:*:*:*:*:*:*"}


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    out = tmp_path_factory.mktemp("dict") / "dict.jsonl.gz"

    def fetch(start, size):
        products = [{"cpe": {"cpeName": c, "cpeNameId": f"id-{c}",
                             "titles": [{"title": c, "lang": "en"}],
                             "deprecated": c in DEPRECATED}}
                    for c in SNAPSHOT_CPES] if start == 0 else []
        return {"totalResults": len(SNAPSHOT_CPES),
                "resultsPerPage": len(products), "products": products}

    build_snapshot(out, fetch=fetch, page_size=100)
    return out


@pytest.fixture(scope="module")
def local(snapshot):
    return LocalDictionary.load(snapshot)


def test_index_has_one_row_per_pair_not_per_entry(local):
    assert local.size == len(SNAPSHOT_CPES)
    # simatic_step_7 is one pair under two parts -> one index row.
    assert len(local.index) == len(local.by_pair)
    pid = local.index.ids[("siemens", "simatic_step_7")]
    assert local.index.parts[pid] == ("a", "h")


def test_index_search_recovers_the_source_typo(local):
    # "EnerGyMetrix" is misspelled "energrymetrix" in the NVD. No CONTAINS
    # search with the correct spelling ever finds it; the bigram
    # pre-filter plus Dice does (playbook §2.2).
    res = local.resolve("Rockwell Automation FactoryTalk EnerGyMetrix 3.0")
    assert res.winner.product == "factorytalk_energrymetrix"
    assert res.accepted


def test_index_prefilter_never_loses_a_candidate(local):
    """The pre-filter must be admissible, not merely fast."""
    rng = random.Random(20260813)
    queries = [clean(t) for t in [
        "Rockwell Automation FactoryTalk Linx CommDTM V1.4.0",
        "Schneider Electric EcoStruxure Control Expert 15.0",
        "Fortinet FortiOS 7.2.5", "adobe acrobat reader dc",
        "microsoft sql server 2019", "totally unrelated string",
        "hp deskjet", "siemens simatic step 7",
    ]] + ["".join(rng.choice("abcdefghijklmnop") for _ in range(rng.randint(4, 22)))
          for _ in range(60)]
    idx = local.index
    for q in queries:
        got = {(c.vendor, c.product): round(c.score, 9)
               for c in idx.search(q)}
        brute = {}
        for pid, key in enumerate(idx.keys):
            score = dice(q, key)
            if score >= MIN_DICE:
                brute[(idx.vendors[pid], idx.products[pid])] = round(score, 9)
        assert got == brute, q


def test_vendor_alias_table_materializes_coexisting_variants(local):
    # The §2.1 phenomenon, one lookup instead of a runtime problem.
    assert local.aliases.variants["schneiderelectric"] == [
        "schneider-electric", "schneider_electric"]
    assert local.aliases.resolve("Schneider Electric") == [
        "schneider-electric", "schneider_electric"]


def test_vendor_alias_seed_is_validated_against_the_snapshot(local):
    # "adobe" exists here, so the TFM rename survives...
    assert local.aliases.resolve("Adobe Systems Incorporated") == ["adobe"]
    # ...and every rename whose target is absent is dropped and reported,
    # never carried as a rewrite that resolves to nothing.
    assert "hewlettpackard->hp" not in local.aliases.dropped_seed
    assert any(d.startswith("advancedmicrodevices") for d in
               local.aliases.dropped_seed)


def test_legal_suffix_alias_only_fires_when_the_stem_really_exists(local):
    assert "inc" in LEGAL_SUFFIXES
    assert local.aliases.resolve("Nonesuch Corporation") == []  # no such vendor
    assert local.aliases.resolve("Adobe Inc") == ["adobe"]
    # A stem that is not a vendor is not invented.
    assert local.aliases.resolve("Visa") == []


def test_alias_table_export(local, tmp_path):
    out = tmp_path / "aliases.csv"
    n = write_alias_table(local, out)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert n == len(rows) and n > 0
    assert {"schneider-electric", "schneider_electric"} <= {
        r["canonical_vendor"] for r in rows}


# ------------------------------------------------------------- lookup

def test_lookup_exact_pair_short_circuits(local):
    lk = local.lookup("adobe", "acrobat_reader_dc",
                      title="Adobe Acrobat Reader DC 21.0")
    assert lk.source == "pair" and lk.candidates
    assert lk.resolution.winner.part == "a"


def test_lookup_uses_the_alias_table_before_paying_for_dice(local):
    lk = local.lookup("adobe_systems_incorporated", "acrobat_reader_dc",
                      title="Adobe Systems Incorporated Acrobat Reader DC")
    assert lk.source == "alias"
    assert lk.candidates[0].cpe_name.startswith("cpe:2.3:a:adobe:")


def test_lookup_falls_through_to_dice(local):
    lk = local.lookup("rockwell_automation", "factorytalk_linx_commdtm",
                      title="Rockwell Automation FactoryTalk Linx "
                            "CommDTM V1.4.0")
    assert lk.source == "dice"
    assert lk.resolution.winner.product == "factorytalk_linx"


def test_lookup_keeps_the_old_union_fallback(local):
    # HP DropBoxPlugin (10k RAW pilot row 332): vendor known, product not.
    lk = local.lookup("hp", "dropboxplugin", title="HP DropBoxPlugin 28.11")
    assert lk.source == "union" and lk.candidates


def test_lookup_reports_a_miss_without_inventing_anything(local):
    lk = local.lookup("dikeic", "dikeic", title="DikeIC 2.2")
    assert lk.source == "miss" and lk.candidates == []


def test_lookup_never_assumes_part_a(local):
    lk = local.lookup("fortinet", "fortios", title="Fortinet FortiOS 7.2.5")
    assert lk.resolution.winner.part == "o"


def test_deprecated_pair_stays_reachable_and_flagged(local):
    lk = local.lookup("legacyvendor", "legacy_tool", title="Legacy Tool 1.0")
    assert lk.candidates                      # not filtered away
    assert lk.resolution.winner.deprecated is True
    assert "deprecated" in lk.resolution.reason


def test_query_mode_entities_ignores_title_noise(local):
    noisy = "Update for Adobe Acrobat Reader DC (KB4562830) 64-bit"
    by_entities = local.lookup("adobe_systems", "acrobat_reader_dc",
                               title=noisy, query_mode="entities")
    assert by_entities.resolution.winner.product == "acrobat_reader_dc"
