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

WP1 step 2 (2026-08-13) adds the *canonicalization* layer ported from
`.ideas/CPE_LOOKUP_PLAYBOOK.md` (KGCS/APOC) to pure stdlib Python:

- :func:`clean` — the symmetric comparison key (lowercase, ASCII
  alphanumerics only), applied to the title AND to the dictionary's
  ``vendor + product``. Neutralizes separator convention, CPE escaping,
  punctuation and spacing in one step. It is ONLY a comparison key: the
  bound WFN still comes from ``normalize_raw``/``bind_component``.
- :func:`dice` — Sorensen-Dice over character bigram *multisets*. The
  multiset variant (not the set variant) reproduces
  ``apoc.text.sorensenDiceSimilarity`` to three decimals on all seven
  validated cases of the playbook (§8), so the port is measurable
  against the same evidence that justified it.
- :func:`decide` — the decision rule of playbook §7: absolute band plus
  the **margin over the runner-up pair**, the hard rule for versioned
  product families (§7.1), the ``part`` choice with title evidence and
  the ``deprecated`` tiebreak (decisions 2026-08-12).

The lookup that produces the scored candidates lives in
:mod:`cpegen.dictionary` (inverted bigram index, vendor alias table);
this module owns the string metrics and the decision rules.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .nvd import DictEntry
from .wfn import WFN, Logical

SIMILARITY_THRESHOLD = 0.8

# --- canonicalization thresholds (playbook §7; calibrated on 7 cases) ---
MIN_DICE = 0.60          # below this: no candidate at all ("gap")
WEAK_DICE = 0.85         # [MIN_DICE, WEAK_DICE): weak candidate, never auto
MARGIN_AUTO = 0.10       # margin over the runner-up pair to auto-accept
MARGIN_REVIEW = 0.05     # below this margin: human review is mandatory

# WP3 (docs/reader-league-implementation-plan.md, spec §8.1): the
# "direct_dice_ge_085" title_features signal — is the RAW title already
# near-verbatim in the dictionary, with no margin/family adjudication?
# Distinct from WEAK_DICE: that band feeds the notary's decide() cascade,
# this one is a plain stratification/trace signal on its own.
DIRECT_DICE_THRESHOLD = 0.85

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


# --------------------------------------------------- canonicalization keys

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WORD = re.compile(r"[a-z0-9]+")

# A trailing product token that names a release rather than the product:
# a year (sql_server_2019), or a bare/dotted version (acrobat_9, foo_1.2).
_VERSION_TOKEN = re.compile(r"^(?:(?:19|20)\d{2}|v?\d+(?:[.]\d+)*)$")


def clean(value: str) -> str:
    """The symmetric comparison key: lowercase, ASCII alphanumerics only.

    Equivalent to ``apoc.text.clean()`` (playbook §4.1). Neutralizes in
    one step: case, ``-``/``_``/concatenation separator conventions
    (``schneider-electric`` vs ``schneider_electric``), CPE backslash
    escaping and parentheses (``simatic_step_7_\\(tia_portal\\)``), and
    the spacing/punctuation of a commercial title.

    This is a *comparison key only*. It never replaces
    ``wfn.normalize_raw``/``bind_component`` as the stored or bound
    value — those must preserve separators to emit a valid CPE
    (docs/match-rules.md, "Límits explícits").
    """
    return _NON_ALNUM.sub("", value.lower())


def bigrams(s: str) -> Counter:
    """Character bigram multiset of an already-cleaned string."""
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def dice(a: str, b: str) -> float:
    """Sorensen-Dice similarity over bigram multisets, in [0,1].

    ``2*|A ∩ B| / (|A| + |B|)`` with multiplicities. Multiset (not set)
    semantics: this is what reproduces ``apoc.text.sorensenDiceSimilarity``
    on the seven validated cases of the playbook (§8) — the set variant
    drifts by up to 0.033 (e.g. Fortinet FortiOS: 0.870 vs the reference
    0.903). Both arguments must already be :func:`clean`ed.

    Dice, not Levenshtein: a commercial title carries tokens absent from
    the CPE (versions, qualifiers like ``CommDTM``). Levenshtein charges
    them as edits; bigram overlap tolerates them (0.853 vs 0.750 on the
    playbook's reference case).
    """
    if a == b:
        return 1.0 if a else 0.0
    ca, cb = bigrams(a), bigrams(b)
    na, nb = sum(ca.values()), sum(cb.values())
    if not na or not nb:
        return 0.0
    common = sum((ca & cb).values())
    return 2 * common / (na + nb)


def title_tokens(title: str) -> set[str]:
    """Lowercase alphanumeric tokens of a raw title."""
    return set(_WORD.findall(title.lower()))


def product_tokens(product: str) -> list[str]:
    """Split a CPE product value into its underlying tokens."""
    return [t for t in _WORD.findall(unescape_cpe_value(product).lower()) if t]


def unescape_cpe_value(value: str) -> str:
    """Drop CPE backslash escaping from a formatted-string component."""
    return value.replace("\\", "")


def family_token(product: str) -> str | None:
    """The trailing release token of a product name, if it has one.

    ``sql_server_2019`` -> ``2019``; ``acrobat_reader`` -> ``None``.
    """
    toks = product_tokens(product)
    if len(toks) < 2:
        return None  # a bare "2019" product is not a family member
    return toks[-1] if _VERSION_TOKEN.match(toks[-1]) else None


def family_stem(product: str) -> str | None:
    """The product name with its trailing release token removed."""
    tok = family_token(product)
    if tok is None:
        return None
    return "_".join(product_tokens(product)[:-1])


def version_token_in_title(token: str, title: str) -> bool:
    """Deterministic check that a release token is present in the title.

    Standalone token match ("Microsoft SQL Server 2019" -> ``2019``), or
    — for tokens of four characters or more, where a substring hit is not
    a coincidence — a hit inside the cleaned title ("SQLServer2019").
    """
    token = token.lower()
    if token in title_tokens(title):
        return True
    return len(token) >= 4 and token in clean(title)


# ------------------------------------------------- version range checking

# One run of digits or one run of letters. Separators (".", "_", "-", " ")
# are boundaries and carry no meaning of their own: the NVD writes the
# same release as "4.8.04690.02", "5.0.8703" and "4.0.1_build_5289".
_VER_TOKEN = re.compile(r"\d+|[a-z]+")

UNDECIDABLE = None  # readability alias for the third verdict


def version_tokens(value: str) -> list:
    """Split a version string into comparable tokens (ints and words)."""
    v = value.strip().lower()
    if len(v) > 1 and v[0] == "v" and v[1].isdigit():
        v = v[1:]           # "v11.1.2245" is "11.1.2245" (seen in the NVD)
    return [int(t) if t.isdigit() else t for t in _VER_TOKEN.findall(v)]


def _year_like(token) -> bool:
    """Does this leading token name a *year release* rather than a number?

    Vendors routinely ship two numbering schemes for the same product —
    AutoCAD is both ``19.0`` and ``2019.1.4``, Adobe Reader is both
    ``22.002`` and ``2020.009.20074``, LabVIEW is both ``8.5.1`` and
    ``2012`` — and the NVD's ranges use whichever the advisory used.
    """
    return isinstance(token, int) and 1990 <= token <= 2100


def compare_versions(a: str, b: str) -> int | None:
    """Order two version strings: -1, 0, 1 — or ``None`` for *undecidable*.

    The third verdict is the point. CPE version strings have no single
    grammar (playbook §9.3: ``6.00`` vs ``6.0`` vs ``6.10``, ``cpr9``,
    ``13.00.00``, ``35.011``), so a comparator that always answers is a
    comparator that sometimes lies. Here, anything the token structure
    does not settle returns ``None`` and the caller treats the version as
    unvalidated — never as in-range.

    Undecidable cases: a number facing a word (``cpr9`` vs ``2.90``); a
    trailing word-token where the other side has run out (``1.0.0`` vs
    ``1.0.0rc1``: pre-release or build metadata, and CPE does not say);
    and a **numbering-scheme mismatch**, where one side leads with a year
    release and the other does not (``19.0`` vs ``2019.1.4``). That last
    one was found by auditing real verdicts on the 10k pilot: purely
    numerically ``19 < 2019``, so the naive answer is a confident "this
    version is inside the vulnerable range" about two numbering schemes
    that were never on the same scale (AutoCAD, Adobe Reader, LabVIEW).
    Trailing zeros are equality: ``1.0`` == ``1.0.0``.
    """
    ta, tb = version_tokens(a), version_tokens(b)
    if not ta or not tb:
        return None
    if _year_like(ta[0]) != _year_like(tb[0]):
        return None
    for x, y in zip(ta, tb):
        if isinstance(x, int) and isinstance(y, int):
            if x != y:
                return -1 if x < y else 1
        elif isinstance(x, str) and isinstance(y, str):
            if x != y:
                return -1 if x < y else 1
        else:
            return None
    if len(ta) == len(tb):
        return 0
    common = min(len(ta), len(tb))
    longer, sign = (ta, 1) if len(ta) > len(tb) else (tb, -1)
    rest = longer[common:]
    if isinstance(rest[0], str):
        return None
    if all(isinstance(t, int) and t == 0 for t in rest):
        return 0
    return sign


@dataclass(frozen=True)
class VersionRange:
    """A ``PlatformConfiguration`` version range, as the NVD models it."""

    start_including: str = ""
    start_excluding: str = ""
    end_including: str = ""
    end_excluding: str = ""

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.start_including, self.start_excluding,
                self.end_including, self.end_excluding)

    @property
    def bounded(self) -> bool:
        return any(self.as_tuple())

    def __str__(self) -> str:
        lo = (f">={self.start_including}" if self.start_including
              else f">{self.start_excluding}" if self.start_excluding else "")
        hi = (f"<={self.end_including}" if self.end_including
              else f"<{self.end_excluding}" if self.end_excluding else "")
        return " ".join(p for p in (lo, hi) if p)

    def contains(self, version: str) -> bool | None:
        """Is ``version`` inside this range? ``None`` if undecidable."""
        if not self.bounded:
            return None
        checks = (
            (self.start_including, lambda c: c >= 0),
            (self.start_excluding, lambda c: c > 0),
            (self.end_including, lambda c: c <= 0),
            (self.end_excluding, lambda c: c < 0),
        )
        for bound, ok in checks:
            if not bound:
                continue
            cmp = compare_versions(version, bound)
            if cmp is None:
                return None
            if not ok(cmp):
                return False
        return True


def version_in_ranges(version: str,
                      ranges: "list[VersionRange]") -> bool | None:
    """True if any range covers the version; None if none could be read.

    A single undecidable range is enough to withhold a ``False``: saying
    "the NVD does not know this version" when the comparator simply could
    not read it would be a lie with consequences (it is the difference
    between "new release" and "unchecked").
    """
    if not version or version in ("*", "-") or not ranges:
        return None
    unknown = False
    for rng in ranges:
        verdict = rng.contains(version)
        if verdict is True:
            return True
        if verdict is None:
            unknown = True
    return None if unknown else False


# ------------------------------------------------- part evidence heuristic

# Only consulted when the SAME (vendor, product) exists under more than
# one CPE part (933 of 150.578 pairs in the 2026-07-02 snapshot). With a
# single part there is nothing to choose: we take it — which is the whole
# point of never assuming ``a`` (playbook §9.5, FortiOS -> ``o``).
PART_EVIDENCE: dict[str, tuple[str, ...]] = {
    "o": ("firmware", "os", "operating", "kernel", "bios", "rtos",
          "android", "ios"),
    "h": ("appliance", "hardware", "router", "switch", "modem", "chipset",
          "board", "sensor"),
}


def part_from_evidence(title: str, product: str,
                       parts: list[str]) -> tuple[str | None, bool]:
    """Pick a CPE part from title evidence; never silently.

    Returns ``(part, ambiguous)``. A part is chosen when exactly one of
    the available parts has evidence in the title or in the product name
    (NVD's ``*_firmware`` convention). Otherwise the caller keeps its
    ranking order and the row is flagged for review — decision
    2026-08-12: "the multi-part pair without evidence is flagged".
    """
    haystack = title_tokens(title) | set(product_tokens(product))
    hits = [p for p in parts
            if p in PART_EVIDENCE
            and haystack & set(PART_EVIDENCE[p])]
    if product.endswith("_firmware") and "o" in parts:
        hits = ["o"]
    if len(hits) == 1:
        return hits[0], False
    return None, True


# ------------------------------------------------------ scored candidates

@dataclass
class ScoredPair:
    """One ``(vendor, product, part)`` dictionary pair with its score."""

    vendor: str
    product: str
    part: str
    score: float
    cpes: int = 0            # how many CPE entries the pair holds
    deprecated: bool = False  # every entry of the pair is deprecated

    @property
    def key(self) -> tuple[str, str]:
        return (self.vendor, self.product)


@dataclass
class PairResolution:
    """Outcome of the clean+Dice lookup for one query.

    ``decision`` follows playbook §7:

    ``auto``     score >= WEAK_DICE and margin > MARGIN_AUTO
    ``flagged``  score >= WEAK_DICE and MARGIN_REVIEW <= margin <= MARGIN_AUTO
    ``review``   score >= WEAK_DICE but margin < MARGIN_REVIEW, or a hard
                 rule fired (versioned family, ambiguous part)
    ``weak``     MIN_DICE <= score < WEAK_DICE
    ``none``     nothing above MIN_DICE

    Only ``auto`` and ``flagged`` are :attr:`accepted` — i.e. allowed to
    canonicalize the WFN before classification.
    """

    query: str = ""
    winner: ScoredPair | None = None
    runner_up: ScoredPair | None = None
    margin: float = 0.0
    decision: str = "none"
    family_verified: bool = False
    part_ambiguous: bool = False
    review_reasons: list[str] = field(default_factory=list)
    candidates: list[ScoredPair] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.decision in ("auto", "flagged")

    @property
    def score(self) -> float:
        return self.winner.score if self.winner else 0.0

    @property
    def reason(self) -> str:
        return ";".join(self.review_reasons)


def decide(candidates: list[ScoredPair], title: str,
           query: str = "") -> PairResolution:
    """Apply the playbook §7 decision rule to scored candidates.

    Deterministic and total: same candidates + same title -> same
    resolution. Steps, in order:

    1. Rank by score; ``deprecated`` loses every tie (decision
       2026-08-12: flag + tiebreak, never filtered — filtering would
       silently drop pairs whose only entry is deprecated).
    2. **Versioned-family hard rule** (§7.1): when the leader's product
       ends in a release token, that token must appear in the title. If
       a sibling of the same family has its token in the title, that
       sibling wins instead; if none does, the resolution is downgraded
       to ``review`` — a bigram metric cannot tell ``sql_server_2019``
       from ``sql_server_2017`` (margin 0.048) and the failure mode is
       assigning the wrong year with high confidence.
    3. **Margin over the runner-up PAIR**: the runner-up is the best
       candidate with a different ``(vendor, product)``. Part variants of
       the same pair are not competitors — they are resolved by
       :func:`part_from_evidence`, not by the margin.
    4. ``part`` choice with title evidence; ambiguity flags for review
       without blocking the match.
    """
    ranked = sorted(candidates,
                    key=lambda c: (-c.score, c.deprecated, -c.cpes,
                                   c.vendor, c.product, c.part))
    ranked = [c for c in ranked if c.score >= MIN_DICE]
    res = PairResolution(query=query, candidates=ranked)
    if not ranked:
        return res

    winner = ranked[0]
    reasons: list[str] = []
    siblings: list[ScoredPair] = []

    # (2) versioned family: prefer the sibling the title actually names.
    token = family_token(winner.product)
    stem = family_stem(winner.product)
    if token is not None and stem is not None:
        siblings = [c for c in ranked
                    if c.vendor == winner.vendor
                    and family_stem(c.product) == stem]
        named = [c for c in siblings
                 if version_token_in_title(family_token(c.product) or "",
                                           title)]
        if named:
            winner = named[0]
            res.family_verified = True
        else:
            # Family with no version evidence in the title: never automatic.
            reasons.append("versioned_family")

    res.winner = winner
    # (3) Runner-up = best candidate of a DIFFERENT pair. Once the release
    # token is verified against the title, the other members of the family
    # are no longer competitors — they are what the deterministic check
    # just ruled out, and leaving them in would send every correctly
    # resolved "SQL Server 2019" to human review over a 0.048 margin
    # against "…2017". The check replaces the margin here; it does not
    # add to it.
    sibling_keys = {c.key for c in siblings} if res.family_verified else set()
    res.runner_up = next((c for c in ranked if c.key != winner.key
                          and c.key not in sibling_keys), None)
    res.margin = round(winner.score - (res.runner_up.score
                                       if res.runner_up else 0.0), 6)

    # (4) part choice among the variants of the winning pair.
    parts = sorted({c.part for c in ranked if c.key == winner.key})
    if len(parts) > 1:
        chosen, ambiguous = part_from_evidence(title, winner.product, parts)
        res.part_ambiguous = ambiguous
        if chosen and chosen != winner.part:
            winner = next(c for c in ranked
                          if c.key == winner.key and c.part == chosen)
            res.winner = winner
        if ambiguous:
            reasons.append("part_ambiguous")

    if winner.deprecated:
        reasons.append("deprecated")

    # (1)+(3) bands.
    if winner.score < WEAK_DICE:
        res.decision = "weak"
        reasons.append("weak_score")
    elif res.margin < MARGIN_REVIEW:
        res.decision = "review"
        reasons.append("narrow_margin")
    elif res.margin <= MARGIN_AUTO:
        res.decision = "flagged"
        reasons.append("thin_margin")
    else:
        res.decision = "auto"
    # The versioned family is a HARD rule: no automatic acceptance without
    # explicit version evidence (playbook §7.1). An ambiguous part is NOT
    # a hard rule — blocking it would drop the very infrastructure rows
    # the decision was meant to rescue; it downgrades to ``flagged`` and
    # keeps the highest-volume part.
    if "versioned_family" in reasons:
        res.decision = "review"
    elif res.part_ambiguous and res.decision == "auto":
        res.decision = "flagged"
    res.review_reasons = reasons
    return res


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
    # --- canonicalization layer (WP1 step 2) ---
    canonical_vendor: str = ""   # dictionary spelling the row resolved to
    canonical_product: str = ""
    part: str = ""               # never assumed: "" when nothing resolved
    dice: float = 0.0            # winner score of the clean+Dice lookup
    margin: float = 0.0          # margin over the runner-up PAIR
    decision: str = ""           # auto | flagged | review | weak | none
    deprecated: bool = False     # the cited entry/pair is deprecated
    review_reason: str = ""      # semicolon-joined triggers
    # Where the version was validated. A column, never a new M rule: the
    # M scale measures matching and stays uniform (decision 2026-08-11 on
    # dictionary_source, applied again here).
    #   dict     the dictionary lists this exact version (M1/M1A)
    #   range    it falls inside a PlatformConfiguration range
    #   outside  ranges exist for the pair and none covers it
    #   unknown  ranges exist but the comparator could not read them
    #   ""       not applicable, or no ranges snapshot loaded
    version_source: str = ""

    @property
    def high_confidence(self) -> bool:
        return self.rule in HIGH_CONFIDENCE

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reason)


def _val(wfn_value: str | Logical) -> str | None:
    return wfn_value if isinstance(wfn_value, str) else None


def canonicalize(wfn: WFN, resolution: PairResolution | None) -> WFN:
    """Return the WFN the notary should classify and bind.

    When the clean+Dice lookup accepted a pair, the vendor/product/part
    of the WFN are replaced by the dictionary's own spelling. This is the
    whole point of the canonicalization layer: the reader may have read
    "Rockwell Automation" perfectly and still lose the match because the
    dictionary says ``rockwellautomation`` (spec §1, failure mode 2).

    The substitution is deterministic code, never the LLM, and the result
    is re-validated against the ABNF grammar downstream — the invariant
    holds unchanged.
    """
    if resolution is None or resolution.winner is None:
        return wfn
    w = resolution.winner
    same_pair = (clean(w.vendor) == clean(_val(wfn.vendor) or "")
                 and clean(w.product) == clean(_val(wfn.product) or ""))
    if not resolution.accepted and not same_pair:
        return wfn
    part = w.part if w.part in ("a", "o", "h") else wfn.part
    if not resolution.accepted:
        # The pair is already the WFN's own; the only thing the dictionary
        # is allowed to correct here is ``part`` — never assume ``a``
        # (playbook §9.5: FortiOS lives under ``o``).
        return WFN(part=part, vendor=wfn.vendor, product=wfn.product,
                   version=wfn.version, update=wfn.update,
                   edition=wfn.edition, language=wfn.language,
                   sw_edition=wfn.sw_edition, target_sw=wfn.target_sw,
                   target_hw=wfn.target_hw, other=wfn.other)
    return WFN(
        part=part,
        vendor=unescape_cpe_value(w.vendor),
        product=unescape_cpe_value(w.product),
        version=wfn.version, update=wfn.update, edition=wfn.edition,
        language=wfn.language, sw_edition=wfn.sw_edition,
        target_sw=wfn.target_sw, target_hw=wfn.target_hw, other=wfn.other)


def classify(wfn: WFN, candidates: list[DictEntry], title: str = "",
             resolution: PairResolution | None = None,
             ranges: "list[VersionRange] | None" = None) -> MatchResult:
    """Apply the M1-M3 cascade to one WFN and its dictionary candidates.

    Deterministic: same WFN + same candidates (+ same resolution) -> same
    result, regardless of which model produced the entities or how sure
    it claimed to be.

    ``resolution`` is the optional outcome of the clean+Dice lookup
    (:func:`decide`). When it is accepted, the cascade runs on the
    canonicalized WFN — that is how a title whose only problem was the
    naming convention reaches M1x instead of M2/M4. The scores, margin
    and review triggers are always reported, accepted or not.
    """
    effective = canonicalize(wfn, resolution)
    vendor = _val(effective.vendor) or ""
    product = _val(effective.product) or ""
    version = _val(effective.version) or ""
    generated_fs = effective.bind()

    # Parse candidate entries into comparable fields once. Deprecated
    # entries stay in the candidate set (decision 2026-08-12: flag +
    # tiebreak, never filter — filtering silently loses every pair whose
    # only entry is deprecated); they simply lose every tie below.
    parsed: list[tuple[DictEntry, WFN]] = []
    for entry in candidates:
        try:
            parsed.append((entry, WFN.unbind(entry.cpe_name)))
        except ValueError:
            continue  # malformed dictionary entry: skip, never crash
    parsed.sort(key=lambda pair: (pair[0].deprecated, pair[0].cpe_name))

    result = _cascade(vendor, product, version, generated_fs, parsed)
    return _annotate(result, candidates, resolution, effective, ranges)


def _cascade(vendor: str, product: str, version: str, generated_fs: str,
             parsed: list[tuple[DictEntry, WFN]]) -> MatchResult:
    """The M1-M4 rule cascade of docs/match-rules.md.

    Unchanged by WP1: it still compares exact field values. What changed
    is *which* values reach it — the canonicalized ones when the lookup
    accepted a pair.
    """

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


def _annotate(result: MatchResult, candidates: list[DictEntry],
              resolution: PairResolution | None,
              effective: WFN,
              ranges: "list[VersionRange] | None" = None) -> MatchResult:
    """Attach the canonicalization signals to a cascade outcome.

    Reported whether or not the resolution was accepted: a ``review``
    band with its score and margin is exactly the signal the human loop
    (WP5) prioritizes its queue with.
    """
    result.canonical_vendor = _val(effective.vendor) or ""
    result.canonical_product = _val(effective.product) or ""
    result.part = _val(effective.part) or ""
    if resolution is not None:
        result.dice = round(resolution.score, 4)
        result.margin = round(resolution.margin, 4)
        result.decision = resolution.decision
        result.review_reason = resolution.reason
        if resolution.winner is not None:
            result.deprecated = resolution.winner.deprecated
    if result.matched_cpe:
        cited = next((e for e in candidates
                      if e.cpe_name == result.matched_cpe), None)
        if cited is not None:
            result.deprecated = cited.deprecated

    # Version provenance. M1/M1A already matched an extensional entry;
    # M1B is the bucket the ranges were brought in for ("the pair is
    # right, the version is not listed") — the NVD models most of the
    # version space intensionally, so "not listed" is not "unknown".
    version = _val(effective.version) or ""
    if result.rule in ("M1", "M1A"):
        result.version_source = "dict"
    elif result.rule == "M1B" and ranges:
        verdict = version_in_ranges(version, ranges)
        result.version_source = ("range" if verdict is True
                                 else "outside" if verdict is False
                                 else "unknown")
        if result.version_source == "unknown":
            result.review_reason = ";".join(
                filter(None, [result.review_reason, "version_unreadable"]))
    return result
