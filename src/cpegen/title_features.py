"""Shared deterministic title features — WP3 (Fase 9.3), spec §8.1.

One module, one contract, reused by three consumers that must never
disagree on what "this title is hard" means: the WP3 stratified sampler
below, the WP4 per-attempt trace schema, and the future WP 9.7 router.
Written and tested once, here.

Seven signals (spec §8.1, "``title_features`` deterministes"):

- ``has_parens``            — the title carries a parenthesized qualifier
  (``SIMATIC STEP 7 (TIA Portal)``): a segmentation trap for the reader.
- ``has_arch_locale_tokens`` — an architecture (``x64``, ``amd64``,
  ``win32``...) or locale (``en-us``, ``pt-br``...) token: noise the
  matcher must not fold into vendor/product.
- ``vendor_in_alias_table``  — some token span of the title is already a
  known vendor spelling (:class:`cpegen.dictionary.VendorAliases`).
  Requires a loaded dictionary; ``False`` without one (never a crash).
- ``versioned_family``       — the title's own trailing token looks like
  a release (year or dotted number) — the family trap of WP1
  (``sql_server_2019``). Reuses :func:`cpegen.matcher.family_token`
  directly: same regex the matcher's versioned-family hard rule already
  uses, never a second implementation of "what looks like a version".
- ``length``                 — character length of the raw title.
- ``n_numeric_tokens``       — count of purely-numeric tokens.
- ``direct_dice_ge_085``     — some dictionary pair scores >= 0.85 Dice
  against the cleaned title with NO margin/family adjudication (the
  "this is basically already in the dictionary verbatim" signal, as
  opposed to the notary's full :func:`cpegen.matcher.decide`). Requires
  a loaded dictionary; ``False`` without one.

:func:`is_hard` — the WP3 stratification criterion — deliberately uses
only the four signals that need NO dictionary (``versioned_family``,
driver/OEM tokens, non-ASCII, ``has_arch_locale_tokens``): the spec's
promise is that stratifying ~90k titles costs zero GPU and no snapshot
load, only string ops over the titles already on disk.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .matcher import DIRECT_DICE_THRESHOLD, clean, family_token

if TYPE_CHECKING:  # pragma: no cover
    from .dictionary import LocalDictionary

_WORD = re.compile(r"[a-z0-9]+")

# Architecture tokens and BCP47-ish locale codes (en-us, pt-br, zh-cn...),
# matched directly against the raw (lowered) title rather than pre-split
# tokens: "x86_64" and "32-bit" would otherwise be cut into pieces by a
# plain alnum tokenizer and miss a straight token-set membership check.
_ARCH_LOCALE_RE = re.compile(
    r"\b(?:x86_64|x86|x64|amd64|arm64|aarch64|i[336]86|ia64|"
    r"win32|win64|32-?bit|64-?bit|[a-z]{2}-[a-z]{2})\b", re.IGNORECASE)

# Small curated set of driver/OEM vocabulary (spec local-prompt hardness
# criterion). Deliberately narrow: `cpegen titles`/`inventory` already
# filter KB/hotfix/language-pack noise upstream (inventory.NOISE_PATTERNS)
# — this is about legitimate driver/OEM PRODUCTS, not noise removal.
_DRIVER_OEM_TOKENS = {
    "driver", "drivers", "oem", "chipset", "firmware", "controller",
    "adapter", "codec", "modem", "bios",
}

# Vendor spans up to this many tokens long are checked against the alias
# table (multi-word vendors: "schneider electric", "trend micro").
_MAX_VENDOR_SPAN = 4


def _tokens(title: str) -> list[str]:
    return _WORD.findall(title.lower())


def _has_parens(title: str) -> bool:
    return "(" in title or ")" in title


def _has_arch_locale_tokens(title: str) -> bool:
    return bool(_ARCH_LOCALE_RE.search(title))


def _has_driver_oem_tokens(tokens: list[str]) -> bool:
    return any(t in _DRIVER_OEM_TOKENS for t in tokens)


def _is_non_ascii(title: str) -> bool:
    return any(ord(c) > 127 for c in title)


def _is_versioned_family(title: str) -> bool:
    # family_token() is the matcher's own "does the trailing token look
    # like a release" check (WP1's versioned-family hard rule) — it
    # operates on any underscore/space-tokenizable string, so the raw
    # title works unchanged. Shared code, not a second regex.
    return family_token(title) is not None


def _n_numeric_tokens(tokens: list[str]) -> int:
    return sum(1 for t in tokens if t.isdigit())


def _vendor_in_alias_table(tokens: list[str],
                           dictionary: "LocalDictionary | None") -> bool:
    if dictionary is None:
        return False
    aliases = getattr(dictionary, "aliases", None)
    if aliases is None:
        return False
    keys = set(aliases.variants) | set(aliases.seed)
    if not keys:
        return False
    n = len(tokens)
    for i in range(n):
        for j in range(i + 1, min(i + _MAX_VENDOR_SPAN, n) + 1):
            if "".join(tokens[i:j]) in keys:
                return True
    return False


def _direct_dice_ge_085(title: str,
                        dictionary: "LocalDictionary | None") -> bool:
    if dictionary is None:
        return False
    index = getattr(dictionary, "index", None)
    if index is None:
        return False
    cleaned = clean(title)
    if not cleaned:
        return False
    return bool(index.search(cleaned, min_score=DIRECT_DICE_THRESHOLD))


def features(title: str,
            dictionary: "LocalDictionary | None" = None) -> dict:
    """The seven deterministic signals of spec §8.1 for one raw title.

    ``dictionary`` is optional (a loaded :class:`cpegen.dictionary.
    LocalDictionary`): without it, ``vendor_in_alias_table`` and
    ``direct_dice_ge_085`` deterministically report ``False`` rather than
    raising — every other signal is dictionary-free by construction.
    """
    tokens = _tokens(title)
    return {
        "has_parens": _has_parens(title),
        "has_arch_locale_tokens": _has_arch_locale_tokens(title),
        "vendor_in_alias_table": _vendor_in_alias_table(tokens, dictionary),
        "versioned_family": _is_versioned_family(title),
        "length": len(title),
        "n_numeric_tokens": _n_numeric_tokens(tokens),
        "direct_dice_ge_085": _direct_dice_ge_085(title, dictionary),
    }


def is_hard(title: str) -> bool:
    """The WP3 stratification criterion: versioned family, driver/OEM
    vocabulary, non-ASCII, or an architecture/locale token.

    No dictionary needed on purpose (see module docstring) — stratifying
    the full RAW population must cost zero GPU and no snapshot load.
    """
    tokens = _tokens(title)
    return (_is_versioned_family(title)
            or _has_driver_oem_tokens(tokens)
            or _is_non_ascii(title)
            or _has_arch_locale_tokens(title))
