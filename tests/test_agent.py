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


def test_agent_loop_no_dictionary_falls_to_m3(tmp_path):
    tb = make_toolbox(tmp_path)
    res = run_agent("google protobuf 3.6.1", MockAgentProvider(), tb)
    assert res.valid
    assert res.rule == "M3"


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
    # offline+empty dict -> fast pass lands M3 -> escalated to agent
    assert rows[0].stage == "agent"
    assert rows[0].fast_rule == "M3"
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
