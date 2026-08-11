"""M1-M3 match classification against the official CPE dictionary.

Encodes the rules from docs/match-rules.md (TFM 2023, coses.xlsx) as a
deterministic cascade. Similarity is normalized Levenshtein.

The classification is purely deterministic: it depends only on the
generated WFN and the dictionary candidates. Model confidence (NER or
LLM) is NOT part of the cascade — it is reported alongside the result
by the callers, never blended into it (decision 2026-07-24; see
docs/evaluation.md). The M1x bucket ("high confidence" in the 2023
baseline's vocabulary) refers to confidence in the *match*, not in the
extraction model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .nvd import DictEntry
from .wfn import WFN, Logical

SIMILARITY_THRESHOLD = 0.8

# Classification -> human meaning (docs/match-rules.md)
RULE_NAMES = {
    "M1": "Perfect match",
    "M1A": "Accepted perfect match",
    "M1B": "New software version",
    "M1C": "New software CPE",
    "M2": "New product candidate",
    "M2B": "New vendor candidate",
    "M3": "Other candidates",
    "M4": "No dictionary match",
}
HIGH_CONFIDENCE = {"M1", "M1A", "M1B", "M1C"}


def levenshtein(a: str, b: str) -> int:
    """Plain Levenshtein edit distance (iterative DP, O(len(a)*len(b)))."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) + len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def similarity(a: str, b: str) -> float:
    """Normalized edit-distance similarity in [0,1]."""
    if not a and not b:
        return 1.0
    dist = levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b))


@dataclass
class MatchResult:
    """Outcome of classifying one generated WFN against the dictionary.

    similarity is the dictionary-side edit similarity that drove the
    rule (1.0 for exact-field rules; sim(version) for M1B; sim(product)
    for M2; sim(vendor) for M3; 0.0 for M4, the no-signal bucket).
    """

    rule: str
    rule_name: str
    similarity: float
    matched_cpe: str | None = None
    detail: str = ""

    @property
    def high_confidence(self) -> bool:
        return self.rule in HIGH_CONFIDENCE


def _val(wfn_value: str | Logical) -> str | None:
    return wfn_value if isinstance(wfn_value, str) else None


def classify(wfn: WFN, candidates: list[DictEntry]) -> MatchResult:
    """Apply the M1-M3 cascade to one WFN and its dictionary candidates.

    Deterministic: same WFN + same candidates -> same result, regardless
    of which model produced the entities or how sure it claimed to be.
    """
    vendor = _val(wfn.vendor) or ""
    product = _val(wfn.product) or ""
    version = _val(wfn.version) or ""
    generated_fs = wfn.bind()

    # Parse candidate entries into comparable fields once.
    parsed: list[tuple[DictEntry, WFN]] = []
    for entry in candidates:
        if entry.deprecated:
            continue
        try:
            parsed.append((entry, WFN.unbind(entry.cpe_name)))
        except ValueError:
            continue  # malformed dictionary entry: skip, never crash

    def fields(w: WFN) -> tuple[str, str, str]:
        return (_val(w.vendor) or "", _val(w.product) or "", _val(w.version) or "")

    # M1: the full formatted string exists verbatim in the dictionary.
    for entry, _ in parsed:
        if entry.cpe_name == generated_fs:
            return MatchResult("M1", RULE_NAMES["M1"], 1.0, entry.cpe_name)

    # M1A: vendor:product and version all match one entry (other attrs differ).
    for entry, w in parsed:
        ev, ep, evr = fields(w)
        if (ev, ep) == (vendor, product) and evr == version and version:
            return MatchResult("M1A", RULE_NAMES["M1A"], 1.0, entry.cpe_name)

    # M1B: vendor:product match, version does not -> new version candidate.
    best_vp = None
    for entry, w in parsed:
        ev, ep, evr = fields(w)
        if (ev, ep) == (vendor, product):
            sim = similarity(version, evr)
            if best_vp is None or sim > best_vp[2]:
                best_vp = (entry, evr, sim)
    if best_vp:
        entry, evr, sim = best_vp
        return MatchResult("M1B", RULE_NAMES["M1B"], sim, entry.cpe_name,
                           detail=f"dict version {evr!r} vs {version!r}")

    vendor_exact = any(fields(w)[0] == vendor for _, w in parsed) if vendor else False
    product_exact_entries = [
        (entry, w) for entry, w in parsed if product and fields(w)[1] == product
    ]

    # M1C: vendor and product both known to the dictionary but the pair is
    # not -> valid candidate for a brand-new CPE entry.
    if vendor_exact and product_exact_entries:
        return MatchResult("M1C", RULE_NAMES["M1C"], 1.0, None,
                           detail="vendor and product exist separately in dictionary")

    # M2: vendor known to the dictionary, product is not (under that
    # vendor) -> new product candidate. This is the 2023 baseline's
    # operational meaning (53% of the inventory landed here): the vendor
    # anchors the row, the similarity is reported as signal, and the
    # best entry is only cited as a match when it clears the threshold.
    # Requiring sim > 0.8 to enter the bucket at all (pre-2026-08-11
    # behaviour) silently dumped these rows into the catch-all.
    best_m2 = None
    for entry, w in parsed:
        ev, ep, _ = fields(w)
        if ev == vendor and vendor:
            sim = similarity(product, ep)
            if best_m2 is None or sim > best_m2[1]:
                best_m2 = (entry, sim)
    if best_m2:
        entry, sim = best_m2
        matched = entry.cpe_name if sim > SIMILARITY_THRESHOLD else None
        return MatchResult("M2", RULE_NAMES["M2"], sim, matched,
                           detail="vendor exists in dictionary; "
                                  f"best product similarity {sim:.2f}")

    # M3 (rule): product matches, vendor merely similar.
    best_m3 = None
    for entry, w in product_exact_entries:
        sim = similarity(vendor, fields(w)[0])
        if best_m3 is None or sim > best_m3[1]:
            best_m3 = (entry, sim)
    if best_m3 and best_m3[1] > SIMILARITY_THRESHOLD:
        return MatchResult("M3", RULE_NAMES["M3"], best_m3[1],
                           best_m3[0].cpe_name)

    # M2B: product exists but the vendor is unknown -> new vendor candidate.
    if product_exact_entries and not vendor_exact:
        return MatchResult("M2B", RULE_NAMES["M2B"], 1.0,
                           product_exact_entries[0][0].cpe_name,
                           detail="product exists, vendor unknown to dictionary")

    # M4: no dictionary signal at all — neither the vendor nor the
    # product is known. v2 addition (2026-08-11): the 2023 baseline
    # lumped these into M3 "Other candidates", which made the M3 bucket
    # unreadable (a row with zero candidates wore the same label as a
    # product match under a similar vendor). For baseline comparisons,
    # v2's M3+M4 together correspond to 2023's M3.
    return MatchResult("M4", RULE_NAMES["M4"], 0.0, None,
                       detail="vendor and product both unknown to dictionary")
