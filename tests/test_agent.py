"""Offline tests for the Phase-4 agent loop, tools and escalation."""

import json

from cpegen.agent import (AgentResult, MockAgentProvider, ModelReply, ToolCall,
                          run_agent, _finalize)
from cpegen.nvd import NVDClient
from cpegen.pipeline import RowResult, needs_escalation, run
from cpegen.tools import ToolBox, build_wfn_from_args


def make_toolbox(tmp_path, seed: dict | None = None) -> ToolBox:
    nvd = NVDClient(cache_path=tmp_path / "cache.json", offline=True)
    if seed:
        for query, products in seed.items():
            nvd._cache_put(query, products)
    return ToolBox(nvd=nvd)


def seed_femanager():
    query = json.dumps({"cpeMatchString": "cpe:2.3:*:in2code:femanager"},
                       sort_keys=True)
    return {query: [{
        "cpeName": "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*",
        "cpeNameId": "abc", "deprecated": False,
        "titles": [{"title": "in2code femanager 5.5.1 for TYPO3", "lang": "en"}],
    }]}


# ------------------------------------------------------------------ tools

def test_toolbox_bind_and_validate(tmp_path):
    tb = make_toolbox(tmp_path)
    out = json.loads(tb.execute("bind_and_validate",
                                {"vendor": "in2code", "product": "femanager",
                                 "version": "5.5.1", "target_sw": "typo3"}))
    assert out["valid"]
    assert out["cpe"] == "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"


def test_toolbox_search_dictionary_cached(tmp_path):
    tb = make_toolbox(tmp_path, seed_femanager())
    out = json.loads(tb.execute("search_dictionary",
                                {"vendor": "in2code", "product": "femanager"}))
    assert out["total"] == 1
    assert out["entries"][0]["cpe"].startswith("cpe:2.3:a:in2code:femanager")


def test_toolbox_search_requires_input(tmp_path):
    tb = make_toolbox(tmp_path)
    out = json.loads(tb.execute("search_dictionary", {}))
    assert "error" in out


def test_toolbox_classify_match(tmp_path):
    tb = make_toolbox(tmp_path, seed_femanager())
    out = json.loads(tb.execute("classify_match",
                                {"vendor": "in2code", "product": "femanager",
                                 "version": "5.5.1", "target_sw": "typo3",
                                 "confidence": 0.9}))
    assert out["rule"] == "M1"
    assert out["high_confidence"]


def test_toolbox_unknown_tool(tmp_path):
    tb = make_toolbox(tmp_path)
    out = json.loads(tb.execute("nonexistent", {}))
    assert "error" in out


def test_toolbox_never_raises(tmp_path):
    tb = make_toolbox(tmp_path)
    out = json.loads(tb.execute("classify_match", {"confidence": "not-a-number"}))
    assert "error" in out


def test_build_wfn_from_args_normalizes():
    w = build_wfn_from_args({"vendor": "Zoho Corp", "product": "ManageEngine"})
    assert w.vendor == "zoho_corp"
    assert w.product == "manageengine"


# ------------------------------------------------------------------- loop

def test_agent_loop_mock_end_to_end(tmp_path):
    tb = make_toolbox(tmp_path, seed_femanager())
    res = run_agent("in2code femanager 5.5.1 for typo3", MockAgentProvider(), tb)
    assert res.valid
    assert res.cpe == "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"
    assert res.rule == "M1"  # dictionary seeded: deterministic reclassification
    assert res.turns == 3
    assert res.error == ""


def test_agent_loop_no_dictionary_falls_to_m4(tmp_path):
    tb = make_toolbox(tmp_path)
    res = run_agent("google protobuf 3.6.1", MockAgentProvider(), tb)
    assert res.valid
    assert res.rule == "M4"


def test_agent_budget_exhausted(tmp_path):
    class NeverSubmits:
        def chat(self, messages):
            return ModelReply(tool_calls=[
                ToolCall("x", "search_dictionary", {"vendor": "acme"})])

    tb = make_toolbox(tmp_path)
    res = run_agent("acme thing 1.0", NeverSubmits(), tb, max_turns=3)
    assert res.error
    assert res.turns == 3


def test_agent_text_only_gets_nudged_then_fails(tmp_path):
    class TalksOnly:
        def chat(self, messages):
            return ModelReply(text="I think the vendor is acme.")

    tb = make_toolbox(tmp_path)
    res = run_agent("acme thing 1.0", TalksOnly(), tb, max_turns=2)
    assert res.error


def test_finalize_escapes_specials_deterministically(tmp_path):
    # Raw specials are escaped by the deterministic bind, so the result is
    # valid by construction: 'pro?duct' -> 'pro\?duct' (literal, not wildcard).
    tb = make_toolbox(tmp_path)
    res = _finalize(AgentResult(title="t"),
                    {"vendor": "acme", "product": "pro?duct", "confidence": 0.9},
                    tb)
    assert res.valid
    assert "pro\\?duct" in res.cpe


def test_finalize_rejects_unprintable_submission(tmp_path):
    # A non-printable character cannot be escaped: the gate must reject it.
    tb = make_toolbox(tmp_path)
    res = _finalize(AgentResult(title="t"),
                    {"vendor": "acme", "product": "pro\x01duct", "confidence": 0.9},
                    tb)
    assert not res.valid
    assert res.cpe == ""
    assert res.validation_errors


def test_finalize_requires_entities(tmp_path):
    tb = make_toolbox(tmp_path)
    res = _finalize(AgentResult(title="t"), {"confidence": 0.9}, tb)
    assert res.error


# -------------------------------------------------------------- escalation

def test_needs_escalation():
    assert needs_escalation(RowResult(title="t", error="boom"))
    assert needs_escalation(RowResult(title="t", valid=True, rule="M3"))
    assert not needs_escalation(RowResult(title="t", valid=True, rule="M1"))
    assert not needs_escalation(RowResult(title="t", valid=True, rule="M1B"))


def test_run_escalate_mode_offline(tmp_path):
    gold = tmp_path / "gold.csv"
    gold.write_text(
        "google protobuf 3.6.1,"
        "[google](cpe_vendor) [protobuf](cpe_product) [3.6.1](cpe_version)\n",
        encoding="utf-8",
    )
    rows, report = run(gold, tmp_path / "out", provider_name="mock",
                       offline=True, agent_mode="escalate",
                       cache_path=tmp_path / "cache.json")
    assert len(rows) == 1
    # offline+empty dict -> fast pass lands M4 -> escalated to agent
    assert rows[0].stage == "agent"
    assert rows[0].fast_rule == "M4"
    assert rows[0].agent_turns == 3
    assert rows[0].valid
    assert report is not None


def test_run_agent_all_mode_offline(tmp_path):
    gold = tmp_path / "gold.csv"
    gold.write_text(
        "in2code femanager 5.5.1 for typo3,"
        "[in2code](cpe_vendor) [femanager](cpe_product) [5.5.1](cpe_version) for typo3\n",
        encoding="utf-8",
    )
    rows, _ = run(gold, tmp_path / "out", provider_name="mock",
                  offline=True, agent_mode="all",
                  cache_path=tmp_path / "cache.json")
    assert rows[0].stage == "agent"
    assert rows[0].cpe == "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"


# ------------------------------------- WP1 step 4: the canonical lookup

def _local_toolbox(tmp_path) -> ToolBox:
    """A ToolBox over a local snapshot, so the agent sees the WP1 lookup."""
    from cpegen.dictionary import LocalDictionary, build_snapshot

    cpes = [
        "cpe:2.3:a:rockwellautomation:factorytalk_linx:6.11:*:*:*:*:*:*:*",
        "cpe:2.3:a:adobe:acrobat_reader_dc:21.0:*:*:*:*:*:*:*",
        "cpe:2.3:o:fortinet:fortios:7.2.5:*:*:*:*:*:*:*",
        "cpe:2.3:a:legacyvendor:legacy_tool:1.0:*:*:*:*:*:*:*",
    ]

    def fetch(start, size):
        products = [{"cpe": {"cpeName": c, "cpeNameId": f"id-{c}",
                             "titles": [{"title": c, "lang": "en"}],
                             "deprecated": c.startswith("cpe:2.3:a:legacy")}}
                    for c in cpes] if start == 0 else []
        return {"totalResults": len(cpes), "resultsPerPage": len(products),
                "products": products}

    snap = tmp_path / "dict.jsonl.gz"
    build_snapshot(snap, fetch=fetch, page_size=100)
    return ToolBox(nvd=LocalDictionary.load(snap))


def test_agent_search_canonicalizes_instead_of_returning_nothing(tmp_path):
    # Before WP1 step 4 the agent saw a strictly weaker dictionary than
    # the fast pass: a prefix lookup on raw values, which answers "no
    # results" for the exact case the canonicalization layer exists for.
    tb = _local_toolbox(tmp_path)
    out = json.loads(tb.execute("search_dictionary", {
        "vendor": "Rockwell Automation",
        "product": "FactoryTalk Linx CommDTM",
        "title": "Rockwell Automation FactoryTalk Linx CommDTM V1.4.0"}))
    assert out["source"] == "dice"
    assert out["canonical"]["vendor"] == "rockwellautomation"
    assert out["canonical"]["product"] == "factorytalk_linx"
    assert out["canonical"]["accepted"] is True
    assert out["canonical"]["dice"] >= 0.85


def test_agent_search_reports_the_part_it_found(tmp_path):
    tb = _local_toolbox(tmp_path)
    out = json.loads(tb.execute("search_dictionary",
                                {"vendor": "fortinet", "product": "fortios"}))
    assert out["canonical"]["part"] == "o"


def test_agent_search_marks_deprecated_instead_of_hiding_it(tmp_path):
    tb = _local_toolbox(tmp_path)
    out = json.loads(tb.execute("search_dictionary",
                                {"vendor": "legacyvendor",
                                 "product": "legacy_tool"}))
    assert out["entries"][0]["deprecated"] is True
    assert out["canonical"]["deprecated"] is True


def test_agent_classify_matches_what_the_notary_will_say(tmp_path):
    # Shared code, not a copy: if the tool and the pipeline could
    # diverge, the agent would be reasoning against a different verdict
    # from the one that ends up on the record.
    from cpegen.dictionary import lookup_for
    from cpegen.matcher import classify
    from cpegen.tools import build_wfn_from_args

    tb = _local_toolbox(tmp_path)
    args = {"vendor": "Rockwell Automation",
            "product": "FactoryTalk Linx CommDTM", "version": "1.4.0",
            "title": "Rockwell Automation FactoryTalk Linx CommDTM V1.4.0",
            "confidence": 0.9}
    out = json.loads(tb.execute("classify_match", args))
    wfn = build_wfn_from_args(args)
    lk = lookup_for(tb.nvd, "rockwell_automation",
                    "factorytalk_linx_commdtm", title=args["title"])
    expected = classify(wfn, lk.candidates, title=args["title"],
                        resolution=lk.resolution, ranges=lk.ranges)
    assert out["rule"] == expected.rule == "M1B"
    assert out["canonical_product"] == expected.canonical_product
    assert out["decision"] == expected.decision


def test_agent_search_still_supports_keyword(tmp_path):
    tb = make_toolbox(tmp_path, seed_femanager())
    out = json.loads(tb.execute("search_dictionary", {"keyword": "femanager"}))
    assert out["source"] == "keyword"
