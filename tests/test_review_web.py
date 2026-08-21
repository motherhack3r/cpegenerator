"""Tests for cpegen.review_web (WP3 Fase A — annotation web UI).

Offline by design: the HTTP layer is exercised through the pure handler
functions (handle_state / handle_verdict), never through sockets.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
from pathlib import Path

import pytest

from cpegen import goldset
from cpegen.dictionary import load_nie_records
from cpegen.review_web import (
    CANDIDATE_NEW_PRODUCT_VERSION,
    CANDIDATE_NEW_VERSION,
    CANDIDATE_OTHER,
    CSV_FIELDS,
    ENTITY_RE,
    IN_PROGRESS,
    PART_VALUES,
    UI_ASSET,
    VERDICTS,
    ReviewState,
    TermsIndex,
    VerdictError,
    bind_components,
    handle_dictcheck,
    handle_history,
    handle_nie_add,
    handle_progress,
    handle_state,
    handle_terms,
    handle_unbind,
    handle_verdict,
    load_or_build_terms,
    match_terms,
    nie_target,
)
from cpegen.sampling import QUEUE_FIELDS


def make_queue(tmp_path: Path, titles=("7-Zip 25.00 (x64)", "Steam 2.10")) -> Path:
    path = tmp_path / "gold-test_queue.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        for t in titles:
            row = {f: "" for f in QUEUE_FIELDS}
            row.update(title=t, origin="rawTest", stratum="random")
            writer.writerow(row)
    return path


def test_load_requires_identity(tmp_path):
    q = make_queue(tmp_path)
    with pytest.raises(VerdictError):
        ReviewState.load(q, identity="  ")


def test_load_rejects_non_queue_csv(tmp_path):
    bad = tmp_path / "results.csv"
    bad.write_text("title,rule\nfoo,M1\n", encoding="utf-8")
    with pytest.raises(VerdictError):
        ReviewState.load(bad, identity="humbert")


def test_annotated_verdict_roundtrips_through_goldset(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    annotated = "[7-Zip](cpe_vendor) [7-Zip](cpe_product) [25.00](cpe_version) (x64)"
    row = state.apply_verdict(0, "annotated", annotated)
    assert row["verdict"] == "annotated"
    assert row["annotator"] == "humbert"
    assert row["timestamp"]  # stamped
    # a frozen queue row must parse as gold with no conversion
    rec = goldset.parse_annotation(row["title"], row["annotated_title"])
    assert rec.vendor == "7-zip"
    assert rec.product == "7-zip"
    assert rec.version == "25.00"


def test_annotated_requires_brackets_and_vendor_or_product(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.apply_verdict(0, "annotated", "no brackets at all")
    with pytest.raises(VerdictError):
        state.apply_verdict(0, "annotated", "[25.00](cpe_version)")


def test_not_software_clears_brackets(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(1, "not_software",
                              "[stale](cpe_vendor) leftover")
    assert row["annotated_title"] == ""
    assert row["verdict"] == "not_software"


def test_unknown_verdict_and_bad_index(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.apply_verdict(0, "maybe", "")
    with pytest.raises(VerdictError):
        state.apply_verdict(99, "skipped", "")


def test_incremental_save_and_resume(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    state.apply_verdict(
        0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)")
    # a fresh load (new session) resumes with the verdict on disk
    resumed = ReviewState.load(q, identity="humbert")
    assert resumed.rows[0]["verdict"] == "annotated"
    assert resumed.rows[1]["verdict"] == ""
    assert resumed.progress() == {
        "total": 2, "done": 1, "annotated": 1,
        "not_software": 0, "skipped": 0,
    }


def test_save_preserves_all_queue_columns(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    state.apply_verdict(0, "skipped", "")
    with open(q, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == list(CSV_FIELDS)
        rows = list(reader)
    assert rows[0]["title"] == "7-Zip 25.00 (x64)"
    assert rows[0]["origin"] == "rawTest"


def test_separate_output_path_leaves_queue_untouched(tmp_path):
    q = make_queue(tmp_path)
    out = tmp_path / "annotations.csv"
    state = ReviewState.load(q, identity="humbert", output_path=out)
    state.apply_verdict(0, "not_software", "")
    original = ReviewState.load(q, identity="humbert")
    assert original.rows[0]["verdict"] == ""
    assert ReviewState.load(out, identity="humbert").rows[0]["verdict"] == \
        "not_software"


def test_http_handlers_are_thin_wrappers(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    payload = handle_state(state)
    assert payload["identity"] == "humbert"
    assert len(payload["rows"]) == 2

    ok = handle_verdict(state, {
        "index": 0, "verdict": "annotated",
        "annotated_title": "[Steam](cpe_vendor) [Steam](cpe_product)",
    })
    assert ok["ok"] is True
    assert ok["progress"]["done"] == 1

    bad = handle_verdict(state, {"index": 0, "verdict": "nope"})
    assert bad["ok"] is False and "verdict" in bad["error"]


def test_entity_regex_stays_in_sync_with_goldset():
    # review_web validates with its own copy of the pattern; if goldset's
    # private regex ever changes shape, this must fail loudly.
    assert ENTITY_RE.pattern == goldset._ENTITY_RE.pattern


def test_ui_asset_exists_and_is_self_contained():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "/api/state" in html and "/api/verdict" in html
    # no external script/resource dependencies (fonts degrade gracefully
    # and are the single allowed external reference)
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == [], f"unexpected external resources: {external}"


def test_bind_components_notary_path():
    out = bind_components({"part": "a", "vendor": "Microsoft",
                           "product": "Visual C++", "version": "2013"})
    assert out["ok"] is True
    assert out["cpe"] == "cpe:2.3:a:microsoft:visual_c\\+\\+:2013:*:*:*:*:*:*:*"
    assert out["wfn"].startswith("wfn:[")
    # normalization is the notary's, echoed back
    assert out["components"]["product"] == "visual_c++"


def test_bind_components_na_and_invalid_part():
    ok = bind_components({"part": "o", "vendor": "fortinet",
                          "product": "fortios", "update": "-"})
    assert ok["ok"] and ":o:fortinet:fortios:" in ok["cpe"] and ":-:" in ok["cpe"]
    bad = bind_components({"part": "x", "vendor": "acme", "product": "thing"})
    assert bad["ok"] is False and bad["cpe"] == "" and bad["errors"]


def test_annotated_verdict_stores_validated_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(
        0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)",
        components={"part": "a", "vendor": "7-Zip", "product": "7-Zip",
                    "version": "25.00"})
    assert row["cpe"] == "cpe:2.3:a:7-zip:7-zip:25.00:*:*:*:*:*:*:*"
    # persisted and resumable
    resumed = ReviewState.load(state.queue_path, identity="humbert")
    assert resumed.rows[0]["cpe"] == row["cpe"]


def test_annotated_verdict_rejects_unbindable_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.apply_verdict(
            0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)",
            components={"part": "zz", "vendor": "7-Zip", "product": "7-Zip"})
    # nothing was written for that row
    assert state.rows[0]["verdict"] == ""


def test_untouched_builder_defaults_store_no_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(
        0, "annotated", "[Steam](cpe_vendor) [Steam](cpe_product)",
        components={"part": "a", "target_sw": "confluence"})  # defaults only
    assert row["cpe"] == ""


def test_not_software_clears_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.apply_verdict(0, "annotated", "[Steam](cpe_vendor) [Steam](cpe_product)",
                        components={"vendor": "valve", "product": "steam"})
    row = state.apply_verdict(0, "not_software", "")
    assert row["cpe"] == "" and row["annotated_title"] == ""


def test_legacy_queue_without_cpe_column_loads_and_upgrades(tmp_path):
    q = make_queue(tmp_path)  # written with QUEUE_FIELDS only (no cpe)
    state = ReviewState.load(q, identity="humbert")
    assert all(r["cpe"] == "" for r in state.rows)
    state.apply_verdict(0, "skipped", "")
    with open(q, newline="", encoding="utf-8") as fh:
        assert csv.DictReader(fh).fieldnames == list(CSV_FIELDS)


# -- official component search (typeahead, design 2026-08-14) --------------


def make_terms_sidecar(tmp_path: Path) -> Path:
    """A tiny synthetic sidecar — never the real 1.77M-row snapshot."""
    path = tmp_path / "cpe_terms.json.gz"
    payload = {
        "vendors": [
            ["microsoft", 500], ["rockwellautomation", 20],
            ["schneider-electric", 2767], ["schneider_electric", 38],
        ],
        "pairs": {
            "microsoft": [["windows", 300], ["visual_c\\+\\+", 120],
                          ["office", 80]],
            "rockwellautomation": [["factorytalk_view", 20]],
            "schneider-electric": [["ecostruxure", 2767]],
            "schneider_electric": [["modicon", 38]],
        },
    }
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def test_terms_index_load_aggregates_products_across_vendors(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    assert dict(terms.vendors)["microsoft"] == 500
    assert dict(terms.pairs["microsoft"]) == {
        "windows": 300, "visual_c\\+\\+": 120, "office": 80}
    # global product list aggregates across every vendor
    assert dict(terms.products)["windows"] == 300


def test_match_terms_cascade_prefix_then_substring_then_clean(tmp_path):
    items = [("microsoft", 500), ("rockwellautomation", 20),
             ("schneider-electric", 2767)]
    # prefix hit
    assert [r["value"] for r in match_terms(items, "micro")] == ["microsoft"]
    # substring hit (not a prefix)
    assert [r["value"] for r in match_terms(items, "soft")] == ["microsoft"]
    # clean() hit: "rockwell automation" -> matches rockwellautomation only
    # once separators are stripped, and would not match as a substring
    out = match_terms(items, "rockwell automation")
    assert [r["value"] for r in out] == ["rockwellautomation"]


def test_match_terms_empty_query_returns_top_by_count():
    items = [("a", 3), ("b", 9), ("c", 1)]  # pre-sorted by the sidecar
    assert [r["value"] for r in match_terms(items, "")] == ["a", "b", "c"]


def test_handle_terms_vendor_field(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_terms(terms, "vendor", "schneider")
    assert out["ok"] is True
    values = [r["value"] for r in out["results"]]
    # both coexisting variants surface (§2.1 of the design note)
    assert "schneider-electric" in values and "schneider_electric" in values


def test_handle_terms_product_filtered_by_chosen_vendor(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_terms(terms, "product", "", vendor="microsoft")
    assert [r["value"] for r in out["results"]] == [
        "windows", "visual_c\\+\\+", "office"]  # microsoft's own ranking
    # an unrecognized vendor falls back to the global (vendor-agnostic) list
    out_unknown = handle_terms(terms, "product", "windows", vendor="acme")
    assert [r["value"] for r in out_unknown["results"]] == ["windows"]


def test_handle_terms_unknown_field_errors(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_terms(terms, "bogus", "x")
    assert out["ok"] is False and "field" in out["error"]


def test_handle_terms_degrades_cleanly_without_index():
    out = handle_terms(None, "vendor", "any")
    assert out == {"ok": True, "results": []}


def test_load_or_build_terms_none_without_sidecar_or_snapshot(tmp_path):
    terms = load_or_build_terms(tmp_path / "missing_terms.json.gz",
                                tmp_path / "missing_snapshot.jsonl.gz")
    assert terms is None


def make_dictionary_snapshot(tmp_path: Path) -> Path:
    """A minimal but real ``LocalDictionary``-loadable snapshot."""
    path = tmp_path / "cpe_dictionary.jsonl.gz"
    entries = [
        {"cpeName": "cpe:2.3:a:7-zip:7-zip:25.00:*:*:*:*:*:*:*",
         "cpeNameId": "id-1", "title": "7-Zip 25.00", "deprecated": False},
        {"cpeName": "cpe:2.3:a:microsoft:windows:11:*:*:*:*:*:*:*",
         "cpeNameId": "id-2", "title": "Microsoft Windows 11",
         "deprecated": False},
    ]
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return path


def test_load_or_build_terms_auto_builds_from_snapshot(tmp_path, capsys):
    snapshot = make_dictionary_snapshot(tmp_path)
    terms_path = tmp_path / "cpe_terms.json.gz"
    assert not terms_path.exists()
    terms = load_or_build_terms(terms_path, snapshot)
    assert terms is not None
    assert terms_path.exists()  # built and left on disk for next time
    assert dict(terms.vendors) == {"7-zip": 1, "microsoft": 1}
    assert dict(terms.pairs["microsoft"]) == {"windows": 1}
    out = capsys.readouterr()
    assert "building" in out.out


def test_part_values_closed_set():
    assert PART_VALUES == ("*", "a", "o", "h", "-")


def test_ui_asset_has_part_dropdown_and_typeahead_wiring():
    html = UI_ASSET.read_text(encoding="utf-8")
    # part renders as a <select>, never a free-text input (design point 3)
    assert 'data-attr="part"' in html
    assert re.search(r'<select data-attr="part">', html)
    assert 'PART_VALUES=["*","a","o","h","-"]' in html.replace(" ", "")
    # vendor/product get the typeahead wrapper + the terms endpoint is wired
    assert 'data-ta="${a}"' in html
    assert '"ta-wrap"' in html
    assert "/api/terms" in html
    assert "TA_FIELDS" in html


# -- portal v2: in_progress draft persistence (design 2026-08-14) ----------


def test_in_progress_kept_out_of_verdicts_and_never_counts_as_done():
    assert IN_PROGRESS not in VERDICTS


def test_save_progress_persists_full_partial_state_and_resumes(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    row = state.save_progress(
        0, annotated_title="[7-Zip](cpe_vendor) partial",
        notes="still checking the version",
        components={"part": "a", "vendor": "7-zip", "product": "7-zip"},
        cpe_text="cpe:2.3:a:7-zip:7-zip:*:*:*:*:*:*:*:*")
    assert row["verdict"] == IN_PROGRESS
    assert row["annotated_title"] == "[7-Zip](cpe_vendor) partial"

    # a fresh load (new session) restores every piece of the draft
    resumed = ReviewState.load(q, identity="humbert")
    r0 = resumed.rows[0]
    assert r0["verdict"] == IN_PROGRESS
    assert r0["annotated_title"] == "[7-Zip](cpe_vendor) partial"
    assert r0["notes"] == "still checking the version"
    draft = json.loads(r0["draft"])
    assert draft["components"] == {"part": "a", "vendor": "7-zip",
                                    "product": "7-zip"}
    assert draft["cpe_text"] == "cpe:2.3:a:7-zip:7-zip:*:*:*:*:*:*:*:*"
    # in_progress is not a final verdict: it must not count as done
    assert resumed.progress()["done"] == 0


def test_save_progress_refuses_to_downgrade_a_final_verdict(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.apply_verdict(0, "annotated",
                        "[7-Zip](cpe_vendor) [7-Zip](cpe_product)")
    with pytest.raises(VerdictError):
        state.save_progress(0, notes="changed my mind")
    # the final verdict is untouched
    assert state.rows[0]["verdict"] == "annotated"


def test_save_progress_bad_index_raises(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    with pytest.raises(VerdictError):
        state.save_progress(99)


def test_apply_verdict_clears_a_prior_draft(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.save_progress(0, components={"vendor": "7-zip"},
                        cpe_text="cpe:2.3:a:7-zip:*:*:*:*:*:*:*:*:*")
    assert state.rows[0]["draft"] != ""
    row = state.apply_verdict(0, "skipped", "")
    assert row["draft"] == ""
    assert state.rows[0]["draft"] == ""


def test_handle_progress_thin_wrapper(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    ok = handle_progress(state, {
        "index": 0, "annotated_title": "[Steam](cpe_vendor)",
        "components": {"vendor": "valve"}, "cpe_text": "", "notes": "x",
    })
    assert ok["ok"] is True and ok["row"]["verdict"] == IN_PROGRESS

    bad = handle_progress(state, {"index": 99})
    assert bad["ok"] is False and "index" in bad["error"]


def test_legacy_queue_without_draft_column_loads_and_upgrades(tmp_path):
    q = make_queue(tmp_path)  # written with QUEUE_FIELDS only (no draft)
    state = ReviewState.load(q, identity="humbert")
    assert all(r["draft"] == "" for r in state.rows)
    state.save_progress(0, components={"vendor": "7-zip"})
    with open(q, newline="", encoding="utf-8") as fh:
        assert csv.DictReader(fh).fieldnames == list(CSV_FIELDS)


# -- portal v2: WFN-wins bidirectional sync (design 2026-08-14) ------------


def test_handle_unbind_is_the_mirror_of_bind_components():
    bound = bind_components({"part": "a", "vendor": "Microsoft",
                             "product": "Visual C++", "version": "2013"})
    assert bound["ok"] is True
    out = handle_unbind(bound["cpe"])
    assert out["ok"] is True
    assert out["components"]["vendor"] == "microsoft"
    assert out["components"]["product"] == "visual_c++"
    assert out["components"]["version"] == "2013"
    assert out["components"]["part"] == "a"
    # untouched attributes come back as the "*" ANY marker, same convention
    # the builder inputs already use
    assert out["components"]["update"] == "*"
    assert out["wfn"] == bound["wfn"]


def test_handle_unbind_na_component_roundtrips():
    bound = bind_components({"part": "o", "vendor": "fortinet",
                             "product": "fortios", "update": "-"})
    out = handle_unbind(bound["cpe"])
    assert out["ok"] is True and out["components"]["update"] == "-"


def test_handle_unbind_rejects_invalid_formatted_string():
    out = handle_unbind("cpe:2.3:x:acme:thing:*:*:*:*:*:*:*:*")
    assert out["ok"] is False and out["errors"]


def test_handle_unbind_rejects_empty_input():
    assert handle_unbind("") == {"ok": False, "errors": ["empty"]}


# -- portal v2: append-only verdict history (design 2026-08-14) ------------


def test_history_appends_one_entry_per_verdict_not_per_draft(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    state.save_progress(0, components={"vendor": "7-zip"})  # draft: no log
    state.apply_verdict(0, "skipped", "")  # verdict #1
    state.apply_verdict(
        0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)")  # #2

    entries = state.read_history(0)
    assert len(entries) == 2
    assert [e["verdict"] for e in entries] == ["skipped", "annotated"]
    assert entries[0]["annotator"] == "humbert"
    assert entries[0]["timestamp"]
    # a different, never-touched row has no history
    assert state.read_history(1) == []


def test_history_survives_reload_and_is_per_output_file(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    state.apply_verdict(0, "not_software", "")
    assert state.history_path.exists()
    assert state.history_path.name.endswith(".history.jsonl")

    resumed = ReviewState.load(q, identity="laia")
    resumed.apply_verdict(1, "skipped", "")
    # history accumulates across sessions, keyed by row index
    assert len(resumed.read_history(0)) == 1
    assert len(resumed.read_history(1)) == 1


def test_handle_history_thin_wrapper(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.apply_verdict(0, "skipped", "")
    ok = handle_history(state, 0)
    assert ok["ok"] is True and len(ok["entries"]) == 1

    bad = handle_history(state, 99)
    assert bad["ok"] is False


# -- portal v2: UI asset wiring for the rebuilt workspace -------------------


def test_ui_asset_wires_progress_unbind_and_history_endpoints():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "/api/progress" in html
    assert "/api/unbind" in html
    assert "/api/history" in html


def test_ui_asset_has_editable_wfn_field_and_notes_textarea():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert 'id="wfnfield"' in html
    assert "<textarea" in html  # notes get a large field now, not <input>


def test_ui_asset_has_collapsible_title_block():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "<details" in html and "<summary" in html


def test_ui_asset_has_save_draft_action():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "savedraft" in html.lower().replace(" ", "").replace("-", "").replace("_", "")


def test_ui_asset_still_self_contained_after_rebuild():
    html = UI_ASSET.read_text(encoding="utf-8")
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == [], f"unexpected external resources: {external}"


# -- portal v2: extra (non-gold) component span marks -----------------------
#
# Buttons for update/edition/language/sw_edition/target_sw/target_hw/other
# feed the builder only — they never touch the RASA-bracket
# annotated_title, so the frozen vendor/product/version gold format and
# goldset.parse_annotation are completely untouched (feedback 2026-08-14:
# "falten els botons per anotar la resta de components").


def test_save_progress_persists_extra_marks(tmp_path):
    q = make_queue(tmp_path)
    state = ReviewState.load(q, identity="humbert")
    row = state.save_progress(
        0, annotated_title="[7-Zip](cpe_vendor)",
        components={"vendor": "7-zip", "update": "sp1"},
        extra_marks={"3": "u", "5": "ts"})
    draft = json.loads(row["draft"])
    assert draft["extra_marks"] == {"3": "u", "5": "ts"}

    resumed = ReviewState.load(q, identity="humbert")
    assert json.loads(resumed.rows[0]["draft"])["extra_marks"] == \
        {"3": "u", "5": "ts"}


def test_save_progress_extra_marks_default_empty(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.save_progress(0)
    assert json.loads(row["draft"])["extra_marks"] == {}


def test_handle_progress_passes_through_extra_marks(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    ok = handle_progress(state, {"index": 0, "extra_marks": {"2": "ed"}})
    assert ok["ok"] is True
    assert json.loads(ok["row"]["draft"])["extra_marks"] == {"2": "ed"}


# -- portal v2 point 4: dictionary field-match stamp (design 2026-08-14) ---


def test_handle_dictcheck_degrades_cleanly_without_index():
    out = handle_dictcheck(None, {"vendor": "microsoft", "product": "windows"})
    assert out == {"ok": True, "vendor_known": None, "product_known": None,
                   "pair_known": None, "candidate": None, "category": None}


def test_handle_dictcheck_known_pair_is_a_new_version_candidate(tmp_path):
    # this review UI only ever sees titles the pipeline couldn't
    # auto-resolve, so even a known pair is at least a version candidate
    # (heuristic approved 2026-08-14 over extending the sidecar with
    # per-pair version data)
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_dictcheck(terms, {"vendor": "microsoft", "product": "windows"})
    assert out["ok"] is True
    assert out["vendor_known"] is True
    assert out["product_known"] is True
    assert out["pair_known"] is True
    assert out["candidate"] is True
    assert out["category"] == CANDIDATE_NEW_VERSION


def test_handle_dictcheck_known_vendor_unknown_product_is_new_product_version(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_dictcheck(terms, {"vendor": "microsoft", "product": "flightsim"})
    assert out["vendor_known"] is True
    assert out["pair_known"] is False
    assert out["candidate"] is True
    assert out["category"] == CANDIDATE_NEW_PRODUCT_VERSION


def test_handle_dictcheck_unknown_vendor_is_other_candidate(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_dictcheck(terms, {"vendor": "acme-corp", "product": "widget"})
    assert out["vendor_known"] is False
    assert out["pair_known"] is False
    assert out["candidate"] is True
    assert out["category"] == CANDIDATE_OTHER


def test_handle_dictcheck_known_names_but_new_pairing_is_new_product_version(tmp_path):
    # both names exist in the dictionary individually, but never together —
    # from THIS vendor's perspective the product is new, so it categorizes
    # as new_product_version, not new_version (that needs the pair itself)
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_dictcheck(terms, {"vendor": "microsoft", "product": "ecostruxure"})
    assert out["vendor_known"] is True
    # product not in microsoft's own pair list -> falls back to the global
    # product set, where it IS known (ships under schneider-electric)
    assert out["product_known"] is True
    assert out["pair_known"] is False
    assert out["candidate"] is True
    assert out["category"] == CANDIDATE_NEW_PRODUCT_VERSION


def test_handle_dictcheck_blank_and_wildcard_fields_are_not_checked(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_dictcheck(terms, {"vendor": "*", "product": "-"})
    assert out == {"ok": True, "vendor_known": None, "product_known": None,
                   "pair_known": None, "candidate": None, "category": None}


def test_handle_dictcheck_vendor_only_no_pair_verdict(tmp_path):
    terms = TermsIndex.load(make_terms_sidecar(tmp_path))
    out = handle_dictcheck(terms, {"vendor": "microsoft", "product": ""})
    assert out["vendor_known"] is True
    assert out["product_known"] is None
    assert out["pair_known"] is None
    assert out["candidate"] is False  # the one checked field is known
    assert out["category"] is None  # needs both fields to categorize


def test_ui_asset_has_full_component_button_set_and_dictcheck_panel():
    html = UI_ASSET.read_text(encoding="utf-8")
    for attr in ("update", "edition", "language", "sw_edition",
                "target_sw", "target_hw", "other"):
        assert f'"{attr}"' in html or f"'{attr}'" in html, attr
    assert "/api/dictcheck" in html
    assert "new candidate" in html.lower()


def test_ui_asset_has_all_three_dictcheck_candidate_categories():
    html = UI_ASSET.read_text(encoding="utf-8")
    for category in ("new_version", "new_product_version", "other"):
        assert category in html, category
    for label in ("NEW VERSION candidate", "NEW PRODUCT AND VERSION candidate",
                 "OTHER candidate"):
        assert label in html, label


# -- title-span overlap (design 2026-08-15, "Apple Mobile Device Support") -
#
# The overlap fix ("una mateixa paraula per anotar diferents elements") is
# entirely client-side JS (marks-as-array, toggle paint, bracketString's
# primary+secondary pass) — no CSV/draft wire format changes, so it's
# covered here as UI-asset content assertions (mirroring the existing
# test_ui_asset_has_* pattern) plus a round-trip check that a title with
# two overlapping v/p spans still parses correctly through the unchanged,
# frozen goldset contract — the whole point of the design (append a
# second bracket segment rather than touch the bracket grammar).


def test_ui_asset_marks_are_multi_valued_for_overlapping_spans():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "tagdots" in html
    assert ".includes(cls)" in html


def test_overlapping_vendor_and_product_brackets_both_parse():
    # what bracketString (client) now emits for a token tagged both vendor
    # AND product ("Apple" in "Apple Mobile Device Support") — the primary
    # pass brackets it as vendor, a secondary pass appends a standalone
    # product bracket that repeats the word. parse_annotation must recover
    # both regardless: it only ever scans for [text](label), never by
    # position — exactly what makes the overlap fix possible without
    # touching the frozen bracket grammar.
    annotated = ("[Apple](cpe_vendor) Mobile Device Support 11.3 "
                "[Apple Mobile Device Support](cpe_product)")
    record = goldset.parse_annotation(
        "Apple Mobile Device Support 11.3", annotated)
    assert record.vendor == "apple"
    assert record.product == "apple mobile device support"


def test_apply_verdict_accepts_overlapping_bracket_segments(tmp_path):
    # the server side never needed a change for overlap — apply_verdict
    # already just extracts entities via ENTITY_RE.findall, so a bracket
    # string with the same word appearing in two segments works unchanged.
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    row = state.apply_verdict(
        0, "annotated",
        "[Apple](cpe_vendor) Mobile Device Support 11.3 "
        "[Apple Mobile Device Support](cpe_product) [11.3](cpe_version)",
        components={"part": "a", "vendor": "apple",
                    "product": "apple_mobile_device_support", "version": "11.3"})
    assert row["cpe"] == \
        "cpe:2.3:a:apple:apple_mobile_device_support:11.3:*:*:*:*:*:*:*"


# -- custom-dictionary inclusion (NIE ceremony, WP5, design 2026-08-15) ----
#
# "Els items marcats com a 'candidats' s'haurien de poder incloure al
# custom dictionary (per defecte MotherHacker)": reuses WP2's NIERecord/
# write_nie_record unchanged (`test_dictionary.py` already covers that
# machinery) — these tests only cover the new endpoint/target-resolution
# glue this feature adds on top.


def test_nie_target_defaults_and_aliases_resolve_to_motherhacker(tmp_path):
    mh = tmp_path / "motherhacker.csv"
    custom = tmp_path / "custom"
    for name in ("", "MotherHacker", "motherhacker", "mh", "  Mother Hacker  "):
        path, origin = nie_target(name, mh, custom)
        assert path == mh, name
        assert origin == "motherhacker", name


def test_nie_target_slugifies_a_client_name_into_its_own_custom_csv(tmp_path):
    mh = tmp_path / "motherhacker.csv"
    custom = tmp_path / "custom"
    path, origin = nie_target("Acme Corp!", mh, custom)
    assert path == custom / "acme_corp.csv"
    assert origin == "acme_corp"


def test_handle_nie_add_requires_a_notary_validated_cpe(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    out = handle_nie_add(state, tmp_path / "motherhacker.csv",
                         tmp_path / "custom", {"index": 0})
    assert out["ok"] is False
    assert "notary-validated" in out["error"]


def test_handle_nie_add_bad_index(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    out = handle_nie_add(state, tmp_path / "motherhacker.csv",
                         tmp_path / "custom", {"index": 99})
    assert out["ok"] is False
    assert "index" in out["error"]


def test_handle_nie_add_writes_to_motherhacker_by_default(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="laia")
    state.apply_verdict(
        0, "annotated", "[7-Zip](cpe_vendor) [7-Zip](cpe_product)",
        components={"part": "a", "vendor": "7-Zip", "product": "7-Zip",
                    "version": "25.00"})
    mh = tmp_path / "dicts" / "motherhacker.csv"
    out = handle_nie_add(state, mh, tmp_path / "dicts" / "custom",
                         {"index": 0, "evidence": "no NVD match found"})
    assert out["ok"] is True
    assert out["origin"] == "motherhacker"
    records = load_nie_records(mh)
    assert len(records) == 1
    assert records[0].cpe == "cpe:2.3:a:7-zip:7-zip:25.00:*:*:*:*:*:*:*"
    assert records[0].human_identity == "laia"
    assert records[0].origin == "motherhacker"
    assert records[0].evidence == "no NVD match found"
    assert "7-Zip" in records[0].motivating_titles


def test_handle_nie_add_writes_to_a_named_client_custom_dict(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.apply_verdict(
        0, "annotated", "[Steam](cpe_vendor) [Steam](cpe_product)",
        components={"part": "a", "vendor": "steam", "product": "steam",
                    "version": "2.10"})
    mh = tmp_path / "dicts" / "motherhacker.csv"
    custom = tmp_path / "dicts" / "custom"
    out = handle_nie_add(state, mh, custom, {"index": 0, "target": "Acme Corp"})
    assert out["ok"] is True
    assert out["origin"] == "acme_corp"
    assert not mh.exists()  # never touches the community dict for a client target
    records = load_nie_records(custom / "acme_corp.csv")
    assert len(records) == 1
    assert records[0].origin == "acme_corp"


def test_handle_nie_add_rejects_a_stale_invalid_stored_cpe(tmp_path):
    # defensive re-validation: only bind_components/apply_verdict ever set
    # row["cpe"], so this should not happen in practice — but a NIE is a
    # governance write, never a place to trust state without checking it.
    state = ReviewState.load(make_queue(tmp_path), identity="humbert")
    state.rows[0]["cpe"] = "not-a-cpe-at-all"
    out = handle_nie_add(state, tmp_path / "motherhacker.csv",
                         tmp_path / "custom", {"index": 0})
    assert out["ok"] is False
    assert "no longer validates" in out["error"]


def test_ui_asset_wires_the_add_to_dictionary_action():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert "/api/nie" in html
    assert "nietarget" in html
    assert "MotherHacker" in html


# -- Advanced review wizard: /api/assist helper registry (2026-08-21) ------
#
# Offline by construction: the LLM helper runs on the extractor's
# MockProvider, web candidates are pure URL construction, and every helper
# is exercised through the pure `handle_assist` / helper functions.

from cpegen.extractor import MockProvider  # noqa: E402
from cpegen.review_web import (  # noqa: E402
    ASSIST_COMPONENTS,
    ASSIST_HELPERS,
    SOURCE_DICTIONARY,
    SOURCE_LLM,
    SOURCE_TITLE,
    SOURCE_TRANSFORM,
    SOURCE_WEB,
    AssistContext,
    LLMAssist,
    handle_assist,
    helper_llm,
    helper_product_title_scan,
    helper_vendor_reverse_lookup,
    helper_vendor_title_scan,
    helper_version_regex,
    helper_version_transforms,
    helper_web_links,
    raw_term,
    title_ngrams,
    title_tokens,
)

MSVC = "Microsoft Visual C++ 2013 Redistributable (x64) - 12.0.30501"


def _terms(tmp_path):
    return TermsIndex.load(make_terms_sidecar(tmp_path))


def _by_source(cands, source):
    return [c for c in cands if c["source"] == source]


def test_assist_registry_covers_exactly_the_three_wizard_steps():
    assert set(ASSIST_HELPERS) == set(ASSIST_COMPONENTS) == {"vendor", "product", "version"}
    for helpers in ASSIST_HELPERS.values():
        assert helpers and all(callable(h) for h in helpers)
        assert helper_web_links in helpers  # every step can hand off to a human web search


def test_title_tokens_match_the_client_split_and_ngrams_index_into_it():
    tks = title_tokens("7-Zip  25.00 (x64)")
    assert tks == ["7-Zip", "  ", "25.00", " ", "(x64)"]  # separators kept, like the UI
    grams = title_ngrams(tks, max_n=2)
    assert grams[0] == ("7-Zip 25.00", 0, 2)          # longest first
    assert ("(x64)", 4, 4) in grams
    assert all("".join(tks[a:b + 1]).split() == text.split() for text, a, b in grams)


def test_raw_term_unescapes_dictionary_spelling_for_the_builder():
    assert raw_term("visual_c\\+\\+") == "visual_c++"
    assert raw_term("microsoft") == "microsoft"
    # round trip through the notary: raw in, escaped formatted string out
    assert bind_components({"product": raw_term("visual_c\\+\\+")})["cpe"] \
        .split(":")[4] == "visual_c\\+\\+"


def test_vendor_title_scan_finds_exact_ngram_with_span(tmp_path):
    ctx = AssistContext("vendor", MSVC, terms=_terms(tmp_path))
    cands = helper_vendor_title_scan(ctx)
    assert [(c["value"], c["span"], c["source"]) for c in cands] == [("microsoft", [0, 0], SOURCE_TITLE)]
    assert "500 CPEs" in cands[0]["evidence"]


def test_vendor_title_scan_matches_multiword_and_separator_variants(tmp_path):
    ctx = AssistContext("vendor", "Schneider Electric EcoStruxure 2.1", terms=_terms(tmp_path))
    values = {c["value"]: c["span"] for c in helper_vendor_title_scan(ctx)}
    # both coexisting dictionary spellings surface, same 2-word span
    assert values == {"schneider-electric": [0, 2], "schneider_electric": [0, 2]}


def test_vendor_title_scan_never_prefix_matches_short_ngrams(tmp_path):
    ctx = AssistContext("vendor", "Mi Fit 1.0", terms=_terms(tmp_path))
    assert helper_vendor_title_scan(ctx) == []  # "Mi" must not light up microsoft


def test_vendor_reverse_lookup_inverts_pairs(tmp_path):
    ctx = AssistContext("vendor", "FactoryTalk View 12.0", terms=_terms(tmp_path))
    cands = helper_vendor_reverse_lookup(ctx)
    assert [c["value"] for c in cands] == ["rockwellautomation"]
    assert cands[0]["source"] == SOURCE_DICTIONARY and cands[0]["span"] is None
    assert "factorytalk view" in cands[0]["evidence"].lower()


def test_product_title_scan_filters_by_chosen_vendor_then_falls_back(tmp_path):
    terms = _terms(tmp_path)
    scoped = helper_product_title_scan(AssistContext(
        "product", MSVC, components={"vendor": "microsoft"}, terms=terms))
    assert [(c["value"], c["span"]) for c in scoped] == [("visual_c++", [2, 4])]
    assert "product of microsoft" in scoped[0]["evidence"]
    # unknown vendor -> global aggregate, same hit, labelled as such
    global_ = helper_product_title_scan(AssistContext(
        "product", MSVC, components={"vendor": "nobody"}, terms=terms))
    assert [c["value"] for c in global_] == ["visual_c++"]
    assert "any vendor" in global_[0]["evidence"]
    # a product of another vendor is NOT offered when scoped
    other = helper_product_title_scan(AssistContext(
        "product", "Microsoft Modicon 1.0", components={"vendor": "microsoft"}, terms=terms))
    assert other == []


def test_version_regex_extracts_shapes_with_spans():
    ctx = AssistContext("version", "Foo v2.1.3 2019 R2 build 12345 (x64) 7")
    cands = helper_version_regex(ctx)
    got = {c["value"]: (c["kind"], c["span"]) for c in cands}
    assert got["v2.1.3"] == ("dotted", [2, 2])
    assert got["2019"] == ("year", [4, 4])
    assert got["R2"] == ("release", [6, 6])
    assert got["12345"] == ("build", [10, 10])
    assert got["7"] == ("bare", [14, 14])
    assert all(c["source"] == SOURCE_TITLE for c in cands)


def test_version_transforms_are_explicit_buttons_never_silent():
    ctx = AssistContext("version", "Acrobat Reader DC v21.001 Service Pack 2 (x64)",
                        components={"version": "v21.001"})
    cands = helper_version_transforms(ctx)
    applies = {c["value"]: c["apply"] for c in cands}
    assert applies["21.001"] == {"version": "21.001"}   # strip leading v
    assert applies["sp2"] == {"update": "sp2"}          # SP -> update
    assert applies["x64"] == {"target_hw": "x64"}       # arch -> target_hw
    assert all(c["source"] == SOURCE_TRANSFORM for c in cands)
    # nothing applicable -> no transforms at all (no phantom buttons)
    assert helper_version_transforms(AssistContext("version", "Steam 2.10")) == []


def test_web_links_are_pure_urls_per_step():
    for comp in ASSIST_COMPONENTS:
        cands = helper_web_links(AssistContext(comp, "7-Zip 25.00",
                                               components={"vendor": "7-zip", "product": "7-zip"}))
        assert [c["value"] for c in cands] == ["DuckDuckGo", "Google", "NVD CPE search"]
        assert all(c["source"] == SOURCE_WEB and c["url"].startswith("https://") for c in cands)
        assert all(" " not in c["url"] for c in cands)
    nvd = helper_web_links(AssistContext("vendor", "x"))[2]["url"]
    assert "nvd.nist.gov/products/cpe/search/results" in nvd and "namingFormat=2.3" in nvd


def test_llm_helper_only_surfaces_notary_validated_entities():
    ctx = AssistContext("vendor", MSVC, llm_entities={"vendor": "microsoft", "confidence": 0.9})
    cands = helper_llm(ctx)
    assert len(cands) == 1 and cands[0]["source"] == SOURCE_LLM
    assert cands[0]["value"] == "microsoft" and cands[0]["span"] == [0, 0]
    assert "confidence 0.90" in cands[0]["evidence"]
    # absent entity -> nothing; bad part -> flagged invalid, not offered
    assert helper_llm(AssistContext("product", MSVC, llm_entities={"vendor": "x"})) == []
    assert helper_llm(AssistContext("vendor", MSVC, llm_entities=None)) == []


def test_llm_assist_is_one_memoised_call_per_title():
    calls = []

    class Counting(MockProvider):
        def complete(self, title):
            calls.append(title)
            return super().complete(title)

    llm = LLMAssist(Counting())
    assert llm.enabled and llm.name == "mock"
    e1 = llm.entities("in2code femanager 5.5.1 for typo3")
    e2 = llm.entities("in2code femanager 5.5.1 for typo3")
    assert e1 is e2 and calls == ["in2code femanager 5.5.1 for typo3"]
    assert e1["vendor"] == "in2code" and e1["product"] == "femanager"
    assert e1["version"] == "5.5.1" and e1["target_sw"] == "typo3"
    disabled = LLMAssist(None)
    assert not disabled.enabled and disabled.name == "" and disabled.entities("x") is None


def test_handle_assist_runs_the_registry_and_reuses_client_cached_llm(tmp_path):
    calls = []

    class Counting(MockProvider):
        def complete(self, title):
            calls.append(title)
            return super().complete(title)

    llm = LLMAssist(Counting())
    terms = _terms(tmp_path)
    r1 = handle_assist(terms, {"component": "vendor", "title": MSVC}, llm)
    assert r1["ok"] and r1["terms"] is True and r1["llm"]["enabled"]
    sources = {c["source"] for c in r1["candidates"]}
    assert {SOURCE_TITLE, SOURCE_LLM, SOURCE_WEB} <= sources
    assert r1["llm_entities"]["vendor"] == "microsoft" and calls == [MSVC]
    # the next step hands the cached entities back -> no second call,
    # even with a fresh (cold) LLMAssist
    r2 = handle_assist(terms, {"component": "product", "title": MSVC,
                               "components": {"vendor": "microsoft"},
                               "llm_entities": r1["llm_entities"]}, LLMAssist(Counting()))
    assert calls == [MSVC]
    assert _by_source(r2["candidates"], SOURCE_LLM)[0]["value"] == "visual c++"
    assert _by_source(r2["candidates"], SOURCE_TITLE)[0]["value"] == "visual_c++"
    # use_llm=false: the registry still runs, the LLM is never asked
    r3 = handle_assist(terms, {"component": "version", "title": MSVC, "use_llm": False},
                       LLMAssist(Counting()))
    assert calls == [MSVC] and r3["llm_entities"] is None
    assert [c["value"] for c in _by_source(r3["candidates"], SOURCE_TITLE)] == ["2013", "12.0.30501"]


def test_handle_assist_rejects_unknown_component():
    res = handle_assist(None, {"component": "edition", "title": "x"})
    assert res["ok"] is False and "edition" in res["error"]


def test_handle_assist_degrades_cleanly_without_sidecar_or_provider():
    for comp in ASSIST_COMPONENTS:
        res = handle_assist(None, {"component": comp, "title": MSVC}, None)
        assert res["ok"] and res["terms"] is False and res["llm"] == {
            "enabled": False, "provider": "", "error": ""}
        sources = {c["source"] for c in res["candidates"]}
        assert SOURCE_DICTIONARY not in sources and SOURCE_LLM not in sources
        assert SOURCE_WEB in sources  # web deep-links need nothing at all
    # version still gets its regex candidates with no data whatsoever
    res = handle_assist(None, {"component": "version", "title": MSVC})
    assert "12.0.30501" in [c["value"] for c in res["candidates"]]


def test_handle_assist_reports_llm_errors_instead_of_failing():
    class Broken:
        name = "broken"

        def complete(self, title):
            return "I refuse"  # no JSON -> extraction error

    res = handle_assist(None, {"component": "vendor", "title": MSVC}, LLMAssist(Broken()))
    assert res["ok"] and res["llm"]["enabled"] and "no JSON" in res["llm"]["error"]
    assert _by_source(res["candidates"], SOURCE_LLM) == []


def test_every_assist_candidate_value_survives_the_notary(tmp_path):
    """Helpers propose; the notary validates — and nothing a helper emits
    (other than web links / flagged-invalid LLM output) may be unbindable."""
    llm = LLMAssist(MockProvider())
    for title in (MSVC, "Schneider Electric EcoStruxure 2.1", "FactoryTalk View 12.0 SP1 (x64)"):
        for comp in ASSIST_COMPONENTS:
            res = handle_assist(_terms(tmp_path), {"component": comp, "title": title}, llm)
            for c in res["candidates"]:
                if c["source"] == SOURCE_WEB or c.get("invalid"):
                    continue
                assert bind_components({comp: c["value"]})["ok"], (title, comp, c)


def test_save_progress_persists_the_wizard_llm_cache(tmp_path):
    state = ReviewState.load(make_queue(tmp_path), identity="h")
    state.save_progress(0, llm_entities={"vendor": "7-zip", "confidence": 0.5})
    draft = json.loads(state.rows[0]["draft"])
    assert draft["llm_entities"] == {"vendor": "7-zip", "confidence": 0.5}
    state.save_progress(1)
    assert json.loads(state.rows[1]["draft"])["llm_entities"] == {}
    res = handle_progress(state, {"index": 0, "llm_entities": {"product": "x"}})
    assert res["ok"] and json.loads(res["row"]["draft"])["llm_entities"] == {"product": "x"}


def test_ui_asset_wires_the_advanced_review_wizard():
    html = UI_ASSET.read_text(encoding="utf-8")
    assert 'id="advreview"' in html and "/api/assist" in html
    for fn in ("openWizard", "wizFinish", "wizAssist", "bindWizardCands"):
        assert fn in html
    for src in (SOURCE_TITLE, SOURCE_DICTIONARY, SOURCE_LLM, SOURCE_WEB, SOURCE_TRANSFORM):
        assert f".wsrc.{src}" in html  # every source is visibly labelled
    assert 'target="_blank"' in html and "llm_entities" in html
    # still self-contained
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == [], external
