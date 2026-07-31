"""Well-Formed Name (WFN) model and CPE 2.3 formatted-string binding.

Implements the logical WFN representation of NISTIR 7695 and the
bind/unbind algorithms between raw attribute values and the CPE 2.3
formatted string. Validation of formatted strings lives in
`cpegen.validator`; this module assumes raw (unescaped) Python values
and produces/consumes bound strings deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Logical(Enum):
    """Logical attribute values (NISTIR 7695 5.3.1)."""

    ANY = "ANY"
    NA = "NA"


ATTRIBUTES = (
    "part",
    "vendor",
    "product",
    "version",
    "update",
    "edition",
    "language",
    "sw_edition",
    "target_sw",
    "target_hw",
    "other",
)

VALID_PARTS = {"a", "o", "h"}

# Characters that appear unescaped in a formatted string component
# (NISTIR 7695 fig. 6-3: unreserved = ALPHA / DIGIT / "-" / "." / "_",
# with ALPHA restricted to lowercase).
_FS_UNRESERVED = re.compile(r"[a-z0-9._-]")


def normalize_raw(value: str) -> str:
    """Normalize a free-text extracted value into WFN convention.

    Lowercase, trim, collapse internal whitespace to single underscores.
    Deterministic: same input always yields the same output.
    """
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    return value


def bind_component(value: str | Logical) -> str:
    """Bind one raw attribute value to its formatted-string component.

    Raw means unescaped: every character is literal. Alphanumerics
    (lowercase), ``_``, ``.`` and ``-`` pass through; any other printable
    character is escaped with a backslash. ``*`` and ``?`` in raw values
    are treated as literals and escaped (the MVP never emits wildcards
    except the logical ANY).
    """
    if value is Logical.ANY:
        return "*"
    if value is Logical.NA:
        return "-"
    if not isinstance(value, str):
        raise TypeError(f"unsupported component value: {value!r}")
    out: list[str] = []
    for ch in value:
        if _FS_UNRESERVED.match(ch):
            out.append(ch)
        else:
            out.append("\\" + ch)
    return "".join(out)


def unbind_component(comp: str) -> str | Logical:
    """Unbind a formatted-string component back to its raw value.

    Assumes the component already passed the validator; raises
    ValueError on malformed escapes as a safety net.
    """
    if comp == "*":
        return Logical.ANY
    if comp == "-":
        return Logical.NA
    out: list[str] = []
    i = 0
    while i < len(comp):
        ch = comp[i]
        if ch == "\\":
            if i + 1 >= len(comp):
                raise ValueError(f"dangling escape in component: {comp!r}")
            out.append(comp[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


@dataclass
class WFN:
    """A Well-Formed Name: 11 attributes, each a raw string or logical."""

    part: str | Logical = Logical.ANY
    vendor: str | Logical = Logical.ANY
    product: str | Logical = Logical.ANY
    version: str | Logical = Logical.ANY
    update: str | Logical = Logical.ANY
    edition: str | Logical = Logical.ANY
    language: str | Logical = Logical.ANY
    sw_edition: str | Logical = Logical.ANY
    target_sw: str | Logical = Logical.ANY
    target_hw: str | Logical = Logical.ANY
    other: str | Logical = Logical.ANY
    _extra: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.part, str) and self.part not in VALID_PARTS:
            raise ValueError(
                f"part must be one of {sorted(VALID_PARTS)}, ANY or NA; got {self.part!r}"
            )

    def bind(self) -> str:
        """Bind to a CPE 2.3 formatted string."""
        comps = [bind_component(getattr(self, attr)) for attr in ATTRIBUTES]
        return "cpe:2.3:" + ":".join(comps)

    @classmethod
    def unbind(cls, formatted: str) -> "WFN":
        """Unbind a CPE 2.3 formatted string into a WFN.

        The string must be valid; callers should run
        `cpegen.validator.validate_formatted_string` first.
        """
        comps = split_formatted_string(formatted)
        if len(comps) != 13 or comps[0] != "cpe" or comps[1] != "2.3":
            raise ValueError(f"not a CPE 2.3 formatted string: {formatted!r}")
        values = [unbind_component(c) for c in comps[2:]]
        return cls(**dict(zip(ATTRIBUTES, values)))

    def to_wfn_string(self) -> str:
        """Render as the wfn:[...] textual form (NISTIR 7695 5.3)."""
        parts = []
        for attr in ATTRIBUTES:
            val = getattr(self, attr)
            if val is Logical.ANY:
                continue  # ANY attributes are conventionally omitted
            if val is Logical.NA:
                parts.append(f"{attr}=NA")
            else:
                quoted = "".join(
                    ch if re.match(r"[a-z0-9_]", ch) else "\\" + ch for ch in val
                )
                parts.append(f'{attr}="{quoted}"')
        return "wfn:[" + ", ".join(parts) + "]"


def split_formatted_string(s: str) -> list[str]:
    """Split a formatted string on unescaped colons."""
    comps: list[str] = []
    cur: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            cur.append(ch)
            cur.append(s[i + 1])
            i += 2
        elif ch == ":":
            comps.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(ch)
            i += 1
    comps.append("".join(cur))
    return comps
