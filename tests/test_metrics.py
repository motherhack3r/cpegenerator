"""Tests for the MUC / SemEval'13 entity-level evaluation."""

from cpegen.goldset import GoldRecord
from cpegen.metrics import EntityEval, Report, compare_entity


# ------------------------------------------------------- MUC categories

def test_compare_entity_correct():
    assert compare_entity("femanager", "femanager") == "COR"


def test_compare_entity_missing():
    assert compare_entity("femanager", None) == "MIS"


def test_compare_entity_spurious():
    assert compare_entity(None, "femanager") == "SPU"


def test_compare_entity_both_absent():
    assert compare_entity(None, None) is None


def test_compare_entity_partial_token_overlap():
    # "axigen_mail" vs "axigen_mail_server": shared tokens -> PAR
    assert compare_entity("axigen_mail_server", "axigen_mail") == "PAR"


def test_compare_entity_partial_containment():
    assert compare_entity("protobuf", "protobufs") == "PAR"


def test_compare_entity_incorrect_no_overlap():
    assert compare_entity("in2code", "google") == "INC"


def test_compare_entity_version_near_miss_is_partial():
    # version "5.5.1" vs "5.5" -> containment counts as partial
    assert compare_entity("5.5.1", "5.5") == "PAR"


# ------------------------------------------------------ scheme formulas

def test_semeval_blog_worked_example():
    """Reproduce the arithmetic of the blog's summary table (partial scheme):
    COR=3, INC=2, PAR=2, MIS=1, SPU=1 -> partial P/R = (3+1)/8 = 0.5...
    using our two schemes on the same counts."""
    e = EntityEval(cor=3, inc=2, par=2, mis=1, spu=1)
    assert e.possible == 8
    assert e.actual == 8
    assert e.strict_precision == 3 / 8
    assert e.strict_recall == 3 / 8
    assert e.partial_precision == (3 + 0.5 * 2) / 8
    assert e.partial_recall == (3 + 0.5 * 2) / 8


def test_strict_ignores_partial():
    e = EntityEval(cor=0, par=4)
    assert e.strict_f1 == 0.0
    assert e.partial_f1 > 0.0


def test_empty_counts_yield_zero():
    e = EntityEval()
    assert e.strict_f1 == 0.0
    assert e.partial_f1 == 0.0


# ------------------------------------------------------------- report

def gold(vendor=None, product=None, version=None, target_sw=None):
    return GoldRecord(title="t", vendor=vendor, product=product,
                      version=version, target_sw=target_sw)


def test_report_correct_row():
    r = Report()
    r.add_entities(gold(vendor="in2code", product="femanager", version="5.5.1"),
                   {"vendor": "in2code", "product": "femanager",
                    "version": "5.5.1", "target_sw": None})
    assert r.entity_counts["vendor"].cor == 1
    assert r.entity_counts["product"].cor == 1
    assert r.entity_counts["target_sw"].possible == 0  # both absent: ignored


def test_report_partial_and_spurious():
    r = Report()
    r.add_entities(gold(vendor="gecad", product="axigen mail server"),
                   {"vendor": "gecad", "product": "axigen mail",
                    "version": "9.9", "target_sw": None})
    assert r.entity_counts["product"].par == 1
    assert r.entity_counts["version"].spu == 1  # predicted, not in gold


def test_report_normalizes_before_comparing():
    r = Report()
    r.add_entities(gold(vendor="Zoho Corp"),
                   {"vendor": "zoho_corp", "product": None,
                    "version": None, "target_sw": None})
    assert r.entity_counts["vendor"].cor == 1


def test_report_markdown_contains_schemes():
    r = Report()
    r.add_entities(gold(vendor="a", product="b"),
                   {"vendor": "a", "product": "x", "version": None,
                    "target_sw": None})
    md = r.to_markdown()
    assert "F1 strict" in md
    assert "F1 partial" in md
    assert "COR" in md
