"""Deterministic CPE 2.3 formatted-string validator.

Implements the ABNF grammar of NISTIR 7695 6.2 (fig. 6-3) as a
hand-written character-level parser. No LLM, no heuristics: a string
either satisfies the grammar or it does not. This is the single gate
every generated CPE must pass before leaving the pipeline.

Grammar essentials enforced here:
- prefix ``cpe:2.3:`` followed by exactly 11 components separated by
  unescaped colons;
- ``part`` is ``a`` / ``o`` / ``h`` or a logical value (``*`` / ``-``);
- each component is a logical value or a non-empty avstring;
- unreserved characters: lowercase letters, digits, ``_``, ``.``, ``-``;
- any other printable non-whitespace character must be backslash-escaped;
- escaping an alphanumeric or ``_`` is illegal;
- unquoted wildcards: a single ``*`` or a run of ``?`` only at the
  beginning and/or end of a component, never in the middle, and never
  forming the whole component together (a lone ``*``/``-`` is logical);
- whitespace and uppercase are illegal anywhere.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field

from .wfn import ATTRIBUTES, split_formatted_string

_UNRESERVED = set(string.ascii_lowercase + string.digits + "._-")
_ALNUM_UNDERSCORE = set(string.ascii_lowercase + string.ascii_uppercase + string.digits + "_")
_PRINTABLE = set(string.printable) - set(string.whitespace)


@dataclass
class ValidationResult:
    """Outcome of validating a formatted string."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    components: dict[str, str] | None = None

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.ok


def _validate_avstring(comp: str, attr: str) -> list[str]:
    """Validate one component against the avstring grammar."""
    errors: list[str] = []
    if comp == "":
        return [f"{attr}: empty component"]
    if comp in ("*", "-"):
        return []  # logical values, always valid

    # Tokenize: each token is ('char', c), ('quoted', c) or ('wild', c)
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(comp):
        ch = comp[i]
        if ch == "\\":
            if i + 1 >= len(comp):
                errors.append(f"{attr}: dangling escape at end of {comp!r}")
                break
            nxt = comp[i + 1]
            if nxt in _ALNUM_UNDERSCORE:
                errors.append(
                    f"{attr}: illegal escape of alphanumeric {nxt!r} in {comp!r}"
                )
            elif nxt not in _PRINTABLE:
                errors.append(
                    f"{attr}: escaped non-printable character in {comp!r}"
                )
            tokens.append(("quoted", nxt))
            i += 2
        elif ch in ("*", "?"):
            tokens.append(("wild", ch))
            i += 1
        elif ch in _UNRESERVED:
            tokens.append(("char", ch))
            i += 1
        elif ch in string.ascii_uppercase:
            errors.append(
                f"{attr}: uppercase character {ch!r} in {comp!r} (values must be lowercase)"
            )
            i += 1
        elif ch in string.whitespace:
            errors.append(f"{attr}: whitespace in {comp!r}")
            i += 1
        else:
            errors.append(
                f"{attr}: unescaped special character {ch!r} in {comp!r}"
            )
            i += 1

    # Wildcard placement rules.
    kinds = [k for k, _ in tokens]
    n = len(tokens)
    # leading wildcard run
    lead = 0
    while lead < n and kinds[lead] == "wild":
        lead += 1
    trail = 0
    while trail < n - lead and kinds[n - 1 - trail] == "wild":
        trail += 1
    body = tokens[lead : n - trail]
    if any(k == "wild" for k, _ in body):
        errors.append(f"{attr}: wildcard in the middle of {comp!r}")
    if not body:
        # whole component is wildcards (and longer than a lone '*')
        errors.append(f"{attr}: component {comp!r} is only wildcards")
    for run in (tokens[:lead], tokens[n - trail :] if trail else []):
        chars = [c for _, c in run]
        if "*" in chars and (len(chars) > 1):
            errors.append(
                f"{attr}: '*' wildcard must be a single character at start/end of {comp!r}"
            )
        # a run of '?' of any length is allowed by the grammar

    return errors


def validate_formatted_string(s: str) -> ValidationResult:
    """Validate a full CPE 2.3 formatted string against the grammar."""
    errors: list[str] = []

    if any(c in string.whitespace for c in s):
        errors.append("whitespace is not allowed in a formatted string")

    comps = split_formatted_string(s)
    if len(comps) < 2 or comps[0] != "cpe" or comps[1] != "2.3":
        return ValidationResult(False, [f"missing 'cpe:2.3:' prefix in {s!r}"] + errors)
    if len(comps) != 13:
        errors.append(
            f"expected 11 components after 'cpe:2.3:', found {len(comps) - 2}"
        )
        return ValidationResult(False, errors)

    values = comps[2:]
    part = values[0]
    if part not in ("a", "o", "h", "*", "-"):
        errors.append(f"part: must be 'a', 'o', 'h', '*' or '-'; got {part!r}")

    for attr, comp in zip(ATTRIBUTES[1:], values[1:]):
        errors.extend(_validate_avstring(comp, attr))

    if errors:
        return ValidationResult(False, errors)
    return ValidationResult(True, [], dict(zip(ATTRIBUTES, values)))
