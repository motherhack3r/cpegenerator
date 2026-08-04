"""Confidence tiering + local dictionary contrast — steps 3-4 of
docs/data-curation-plan.md.

Consumes the ``catalog_parsed.csv`` produced by :mod:`cpegen.curate`
(steps 1-2) and splits it into:

- ``catalog_tier_a.csv`` — rows with an explicit human override
  (``Override *`` columns in the source export);
- ``catalog_tier_b.csv`` — everything else, with a ``creator`` column
  (``human``/``system``) preserved so the 113k analyst-created rows
  without override stay distinguishable;
- ``quarantine.csv`` — alias sets with contamination signals, each with
  a machine-readable reason. Quarantine is a review queue, not a bin:
  nothing is deleted.

Step 4 (dictionary contrast) is fully local against the snapshot built
by ``cpegen dict --build`` (KGCS Neo4j or NVD API — same file): for
every alias we record whether the exact CPE exists in the official
dictionary, whether it is deprecated there, and whether at least the
(vendor, product) pair is known. Absence is a signal (M2 territory),
never a rejection — per the plan, "absent del diccionari != incorrecte".

The contrast also sharpens quarantine: a multi-vendor alias set whose
products share no name tokens is only quarantined when at least one
alias's (vendor, product) pair is unknown to the dictionary — pairs the
dictionary itself contains (e.g. cisco:nx-os) are legitimate aliases,
whatever their string distance.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .curate import OUTPUT_FIELDS
from .dictionary import LocalDictionary
from .wfn import split_formatted_string

_ALIAS_SPLIT = re.compile(r"(?<!\\),")
_TOKEN_SPLIT = re.compile(r"[_\-.]")


@dataclass
class Contrast:
    """Step-4 outcome for one row's alias set."""

    n_in_dict: int = 0          # aliases present verbatim in the dictionary
    n_deprecated: int = 0       # of those, deprecated ones
    n_pairs_known: int = 0      # aliases whose (vendor, product) pair exists
    unknown_pairs: tuple = ()   # (vendor, product) pairs the dict ignores


def _vendor_product(alias: str) -> tuple[str, str]:
    comps = split_formatted_string(alias)
    return (comps[3], comps[4]) if len(comps) == 13 else ("", "")


def contrast_aliases(aliases: list[str],
                     dictionary: LocalDictionary) -> Contrast:
    """Contrast one alias set against the local dictionary snapshot."""
    c = Contrast()
    unknown = []
    for alias in aliases:
        vendor, product = _vendor_product(alias)
        candidates = dictionary.by_pair.get((vendor, product))
        if candidates is None:
            unknown.append((vendor, product))
            continue
        c.n_pairs_known += 1
        exact = next((e for e in candidates if e.cpe_name == alias), None)
        if exact is not None:
            c.n_in_dict += 1
            if exact.deprecated:
                c.n_deprecated += 1
    c.unknown_pairs = tuple(unknown)
    return c


def _products_share_tokens(products: set[str]) -> bool:
    """True when every pair of product names shares at least one token."""
    toks = [set(t for t in _TOKEN_SPLIT.split(p) if t) for p in products]
    return all(a & b for i, a in enumerate(toks) for b in toks[i + 1:])


def quarantine_reason(aliases: list[str],
                      contrast: Contrast | None) -> str | None:
    """Deterministic contamination check for one alias set.

    Signal (from the 2026-07-24 exploration, e.g. a ClamAV title carrying
    ``cisco``/``appdynamics`` aliases): several distinct vendors AND
    product names with no token overlap. When a dictionary contrast is
    available, pairs the official dictionary knows are exonerated; the
    set is only quarantined if some incompatible alias is also unknown
    to the dictionary.
    """
    if len(aliases) < 2:
        return None
    pairs = [_vendor_product(a) for a in aliases]
    vendors = {v for v, _ in pairs}
    products = {p for _, p in pairs}
    if len(vendors) < 2 or _products_share_tokens(products):
        return None
    if contrast is not None and not contrast.unknown_pairs:
        return None  # every pair is dictionary-known: legitimate aliases
    detail = (",".join(f"{v}:{p}" for v, p in contrast.unknown_pairs)
              if contrast is not None else "no_dictionary")
    return f"incompatible_vendors:{detail}"


CONTRAST_FIELDS = ("creator", "n_aliases_in_dict", "n_deprecated_in_dict",
                   "n_pairs_known")


def tier_file(catalog_path: Path, output_dir: Path,
              dictionary_path: Path | None = None,
              progress: Callable[[int], None] | None = None) -> dict:
    """Split the parsed catalog into tiers + quarantine, with contrast.

    Returns the metrics dict (also written to ``tier_metrics.json``).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dictionary = (LocalDictionary.load(dictionary_path)
                  if dictionary_path else None)

    fields = list(OUTPUT_FIELDS) + list(CONTRAST_FIELDS)
    stats = {"rows": 0, "tier_a": 0, "tier_b": 0, "quarantine": 0,
             "tier_b_human_created": 0,
             "aliases_contrasted": 0, "aliases_in_dict": 0,
             "aliases_deprecated": 0, "aliases_pair_known": 0,
             "dictionary": str(dictionary_path) if dictionary_path else None,
             "dictionary_size": dictionary.size if dictionary else 0}

    with open(catalog_path, newline="", encoding="utf-8") as fin, \
            open(output_dir / "catalog_tier_a.csv", "w", newline="",
                 encoding="utf-8") as fa, \
            open(output_dir / "catalog_tier_b.csv", "w", newline="",
                 encoding="utf-8") as fb, \
            open(output_dir / "quarantine.csv", "w", newline="",
                 encoding="utf-8") as fq:
        wa, wb = csv.writer(fa), csv.writer(fb)
        wq = csv.writer(fq)
        wa.writerow(fields)
        wb.writerow(fields)
        wq.writerow(fields + ["reason"])

        for row in csv.DictReader(fin):
            stats["rows"] += 1
            aliases = _ALIAS_SPLIT.split(row["cpes"])
            creator = ("system" if row["created_by"] in ("", "system")
                       else "human")

            contrast = None
            if dictionary is not None:
                contrast = contrast_aliases(aliases, dictionary)
                stats["aliases_contrasted"] += len(aliases)
                stats["aliases_in_dict"] += contrast.n_in_dict
                stats["aliases_deprecated"] += contrast.n_deprecated
                stats["aliases_pair_known"] += contrast.n_pairs_known

            out_row = [row[f] for f in OUTPUT_FIELDS] + [
                creator,
                contrast.n_in_dict if contrast else "",
                contrast.n_deprecated if contrast else "",
                contrast.n_pairs_known if contrast else "",
            ]

            reason = quarantine_reason(aliases, contrast)
            if reason is not None:
                stats["quarantine"] += 1
                wq.writerow(out_row + [reason])
            elif row["has_override"] == "1":
                stats["tier_a"] += 1
                wa.writerow(out_row)
            else:
                stats["tier_b"] += 1
                if creator == "human":
                    stats["tier_b_human_created"] += 1
                wb.writerow(out_row)
            if progress and stats["rows"] % 20000 == 0:
                progress(stats["rows"])

    (output_dir / "tier_metrics.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return stats
