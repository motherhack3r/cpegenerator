"""Edge-case tests for the deterministic CPE 2.3 validator."""

import pytest

from cpegen.validator import validate_formatted_string


def valid(s: str) -> bool:
    return validate_formatted_string(s).ok


# ---------------------------------------------------------------- basics

def test_canonical_example():
    assert valid("cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*")


def test_all_any():
    assert valid("cpe:2.3:a:*:*:*:*:*:*:*:*:*:*")


def test_all_na():
    assert valid("cpe:2.3:a:-:-:-:-:-:-:-:-:-:-")


def test_os_and_hardware_parts():
    assert valid("cpe:2.3:o:linux:linux_kernel:5.15:*:*:*:*:*:*:*")
    assert valid("cpe:2.3:h:cisco:catalyst_9300:-:*:*:*:*:*:*:*")


def test_part_logical_values():
    assert valid("cpe:2.3:*:vendor:product:*:*:*:*:*:*:*:*")
    assert valid("cpe:2.3:-:vendor:product:*:*:*:*:*:*:*:*")


def test_invalid_part():
    assert not valid("cpe:2.3:x:vendor:product:*:*:*:*:*:*:*:*")


# ---------------------------------------------------- structure errors

def test_missing_prefix():
    assert not valid("cpe:/a:vendor:product:1.0")
    assert not valid("cpe:2.2:a:v:p:*:*:*:*:*:*:*:*")
    assert not valid("2.3:a:v:p:*:*:*:*:*:*:*:*")


def test_too_few_components():
    assert not valid("cpe:2.3:a:vendor:product")


def test_too_many_components():
    assert not valid("cpe:2.3:a:v:p:1:*:*:*:*:*:*:*:extra")


def test_empty_component():
    assert not valid("cpe:2.3:a::product:1.0:*:*:*:*:*:*:*")


def test_empty_string():
    assert not valid("")


# ------------------------------------------------------------ escaping

def test_escaped_colon_is_not_a_separator():
    assert valid("cpe:2.3:a:vendor:name\\:with_colon:1.0:*:*:*:*:*:*:*")


def test_unescaped_special_rejected():
    assert not valid("cpe:2.3:a:vendor:c++:1.0:*:*:*:*:*:*:*")


def test_escaped_special_accepted():
    assert valid("cpe:2.3:a:vendor:c\\+\\+:1.0:*:*:*:*:*:*:*")


def test_escaping_alphanumeric_rejected():
    assert not valid("cpe:2.3:a:vendor:pro\\duct:1.0:*:*:*:*:*:*:*")


def test_dangling_escape_rejected():
    assert not valid("cpe:2.3:a:vendor:product\\:1.0:*:*:*:*:*:*")


def test_dot_dash_underscore_unescaped_are_valid():
    assert valid("cpe:2.3:a:riot.js:riot-compiler:3.1.2:*:*:*:*:node.js:*:*")


def test_escaped_tilde_and_percent():
    assert valid("cpe:2.3:a:vendor:100\\%_product:1.0\\~beta:*:*:*:*:*:*:*")


# ----------------------------------------------------------- wildcards

def test_wildcard_star_at_end_of_value():
    assert valid("cpe:2.3:a:vendor:product:1.0.*:*:*:*:*:*:*:*")


def test_wildcard_star_at_start_of_value():
    assert valid("cpe:2.3:a:vendor:*manager:1.0:*:*:*:*:*:*:*")


def test_wildcard_star_in_middle_rejected():
    assert not valid("cpe:2.3:a:vendor:pro*duct:1.0:*:*:*:*:*:*:*")


def test_question_mark_runs_at_edges():
    assert valid("cpe:2.3:a:vendor:product:1.0.??:*:*:*:*:*:*:*")
    assert valid("cpe:2.3:a:vendor:??product:1.0:*:*:*:*:*:*:*")


def test_question_mark_in_middle_rejected():
    assert not valid("cpe:2.3:a:vendor:pro?duct:1.0:*:*:*:*:*:*:*")


def test_double_star_rejected():
    assert not valid("cpe:2.3:a:vendor:product:1.0.**:*:*:*:*:*:*:*")


def test_only_wildcards_rejected():
    assert not valid("cpe:2.3:a:vendor:??:1.0:*:*:*:*:*:*:*")
    assert not valid("cpe:2.3:a:vendor:*?:1.0:*:*:*:*:*:*:*")


def test_escaped_star_is_literal_not_wildcard():
    # escaped '*' in the middle is a quoted literal, allowed
    assert valid("cpe:2.3:a:vendor:pro\\*duct:1.0:*:*:*:*:*:*:*")


# ------------------------------------------------------- value hygiene

def test_uppercase_rejected():
    assert not valid("cpe:2.3:a:Vendor:product:1.0:*:*:*:*:*:*:*")


def test_whitespace_rejected():
    assert not valid("cpe:2.3:a:ven dor:product:1.0:*:*:*:*:*:*:*")
    assert not valid("cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:* ")


def test_na_and_any_mix():
    assert valid("cpe:2.3:a:vendor:product:-:*:-:*:-:*:-:*")


def test_dash_prefixed_value_is_avstring_not_na():
    assert valid("cpe:2.3:a:vendor:-product:1.0:*:*:*:*:*:*:*")


def test_components_dict_returned():
    res = validate_formatted_string(
        "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"
    )
    assert res.ok
    assert res.components["vendor"] == "in2code"
    assert res.components["target_sw"] == "typo3"


def test_error_messages_are_specific():
    res = validate_formatted_string("cpe:2.3:a:Ven dor:pro*duct:1.0:*:*:*:*:*:*:*")
    assert not res.ok
    assert any("uppercase" in e for e in res.errors)
    assert any("wildcard" in e for e in res.errors)
