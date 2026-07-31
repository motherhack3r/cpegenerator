"""Tests for WFN binding/unbinding and normalization."""

import pytest

from cpegen.validator import validate_formatted_string
from cpegen.wfn import WFN, Logical, bind_component, normalize_raw, unbind_component


def test_bind_canonical():
    w = WFN(part="a", vendor="in2code", product="femanager",
            version="5.5.1", target_sw="typo3")
    assert w.bind() == "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"


def test_bind_escapes_specials():
    w = WFN(part="a", vendor="vendor", product="c++")
    assert w.bind() == "cpe:2.3:a:vendor:c\\+\\+:*:*:*:*:*:*:*:*"


def test_bind_output_always_validates():
    nasty = ["c++", "100% cpu", "a:b", "tilde~name", "back\\slash", "(x64)"]
    for raw in nasty:
        w = WFN(part="a", vendor="v", product=normalize_raw(raw))
        assert validate_formatted_string(w.bind()).ok, raw


def test_roundtrip():
    fs = "cpe:2.3:a:gecad:axigen_mail_server:3.0:beta:*:*:*:*:*:*"
    w = WFN.unbind(fs)
    assert w.vendor == "gecad"
    assert w.update == "beta"
    assert w.bind() == fs


def test_roundtrip_with_escapes():
    fs = "cpe:2.3:a:riot.js:riot-compiler:3.1.2:*:*:*:*:node.js:*:*"
    assert WFN.unbind(fs).bind() == fs


def test_unbind_logicals():
    w = WFN.unbind("cpe:2.3:a:vendor:product:-:*:*:*:*:*:*:*")
    assert w.version is Logical.NA
    assert w.update is Logical.ANY


def test_invalid_part_raises():
    with pytest.raises(ValueError):
        WFN(part="x")


def test_normalize_raw():
    assert normalize_raw("  Zoho Corp ") == "zoho_corp"
    assert normalize_raw("Visual C++ 2013") == "visual_c++_2013"
    assert normalize_raw("a\tb  c") == "a_b_c"


def test_bind_component_literal_wildcards_escaped():
    assert bind_component("v1.*") == "v1.\\*"
    assert bind_component(Logical.ANY) == "*"
    assert bind_component(Logical.NA) == "-"


def test_unbind_component():
    assert unbind_component("c\\+\\+") == "c++"
    assert unbind_component("*") is Logical.ANY
    assert unbind_component("-") is Logical.NA


def test_to_wfn_string():
    w = WFN(part="a", vendor="in2code", product="femanager",
            version="5.5.1", target_sw="typo3")
    s = w.to_wfn_string()
    assert s.startswith("wfn:[")
    assert 'version="5\\.5\\.1"' in s
    assert "update" not in s  # ANY omitted
