"""WP3/Fase A — local web UI for annotation queues (``cpegen review``).

A zero-dependency (stdlib ``http.server``) localhost server that turns the
WP3 annotation queue CSVs into a visual, keyboard-friendly review flow.
The UI is ergonomics, never authority:

- it READS the queue CSV exactly as ``cpegen sample`` wrote it
  (:data:`cpegen.sampling.QUEUE_FIELDS`);
- it WRITES the same columns back (``annotated_title`` in the RASA-bracket
  format :func:`cpegen.goldset.parse_annotation` already parses, plus
  ``verdict``/``annotator``/``timestamp``/``notes``) — a reviewed queue is
  freezable with no format conversion, identical to hand-editing the CSV;
- every verdict is stamped with the reviewer identity (``--identity``,
  required — spec §6.4/N11) and a UTC timestamp;
- saves are incremental and atomic (temp file + ``os.replace``): closing
  the browser or killing the server never loses confirmed rows.

Phases (decision 2026-08-14): this annotation mode is Fase A; Fase B will
reuse the same module for the WP5 ``needs_review``/NIE flow; Fase C (the
multi-user community/client dictionary platform) is a separate
post-publication product for which A/B act as the validated prototype.

Portal v2 (design 2026-08-14, "portal de review v2 — disseny aprovat"):
three-level workspace — title spans, the 11-component builder, and an
editable WFN/formatted-string field, kept in sync through the same
``bind_components``/``WFN.unbind`` notary path (``/api/bind``,
``/api/unbind``); a row can be saved without a final verdict
(``verdict="in_progress"``, ``/api/progress``) which persists every piece
of partial state and is never counted as done; every real verdict appends
to a per-row, append-only JSONL history beside the output CSV
(``ReviewState.history_path``, ``/api/history``). A fourth panel,
``/api/dictcheck``, stamps the builder's vendor/product fields against the
official (NVD) dictionary via the same typeahead sidecar (:class:`TermsIndex`)
— an unmatched field is a "candidate", which only a MotherHacker community
dictionary or a client custom dictionary can validate for inclusion (the
NIE ceremony, WP5/9.6); this is informational only and never persisted.
Title spans for the other 7 CPE components (update/edition/language/
sw_edition/target_sw/target_hw/other) feed the builder the same way but
never the RASA-bracket ``annotated_title`` — the frozen vendor/product/
version gold format used by :mod:`cpegen.goldset` is untouched. A title
word can carry more than one span at once (feedback 2026-08-15, "Apple
Mobile Device Support": the word "Apple" is both the vendor AND part of
the product name) — the client keeps a *set* of marks per token instead
of one, and ``bracketString`` (client-side) appends any gold mark beyond
a token's first as its own bracket segment so ``parse_annotation`` (a
flat scan for ``[text](label)`` anywhere in the string, never by
position) still recovers it; a row with no overlap emits byte-identical
output to before. Purely a client-side rendering/encoding change — no
new server endpoint, no CSV/format change.

A fifth action (design 2026-08-15, "candidats s'haurien de poder
incloure's al custom dictionary"): once a row has a notary-validated CPE
(``row["cpe"]``), ``POST /api/nie`` mints it into a custom-dictionary CSV
via the existing WP2 ``NIERecord``/``write_nie_record`` (reused, not
reimplemented — this endpoint is the WP5 human-loop caller the
``dictionary.py`` module docstring already named but never had). The
target is free text defaulting to "MotherHacker" (the fixed community
CSV); anything else is slugified into its own per-client custom CSV
under :data:`DEFAULT_CUSTOM_DICT_DIR` — same NIE schema, a different
book, exactly the layering :class:`cpegen.dictionary.LayeredDictionary`
already expects.

"Advanced review" (design decided 2026-08-21): a per-row, step-by-step
wizard (vendor -> product -> version; the other 8 components as plain
fields) backed by ``POST /api/assist`` and a per-component registry of
pure helpers (:data:`ASSIST_HELPERS`): title scan and reverse lookup over
the same typeahead sidecar, regex version extraction with explicit
one-click transforms, pre-built web search deep-links (never fetched by
the server), and an optional LLM helper (``--assist-provider``) whose
JSON entities are revalidated through the notary before being shown and
are never auto-filled. On finish/exit the wizard lands in the normal
builder with fields and title spans filled — the bind/unbind/draft/NIE
backend is untouched. NVD live API was explicitly ruled out.

The server binds 127.0.0.1 only. No network is ever required: the HTML
asset is self-contained (web fonts degrade to system fallbacks offline).
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .dictionary import (
    DEFAULT_SNAPSHOT,
    DEFAULT_TERMS,
    NIERecord,
    build_terms_sidecar,
    write_nie_record,
)
from .matcher import clean
from .sampling import QUEUE_FIELDS
from .validator import validate_formatted_string
from .wfn import WFN, Logical, normalize_raw

CPE_ATTRS = ("part", "vendor", "product", "version", "update", "edition",
             "language", "sw_edition", "target_sw", "target_hw", "other")
# The reviewed CSV adds two columns over the sample queue: the humanly
# built, notary-validated CPE (blank when none was built), and a JSON
# blob of in-progress draft state (blank once a row has a final verdict).
# Both are additive — legacy queues without them load fine (backfilled
# empty) and gain the columns on first save; the contract only grows.
CSV_FIELDS = QUEUE_FIELDS + ("cpe", "draft")

UI_ASSET = Path(__file__).with_name("review_ui.html")

# Same shape goldset._ENTITY_RE accepts; kept local so review_web never
# imports a private name, and a test asserts the two stay in sync.
ENTITY_RE = re.compile(r"\[([^\]]+)\]\((cpe_vendor|cpe_product|cpe_version)\)")

VERDICTS = ("annotated", "not_software", "skipped")

# A fourth, non-final row state (portal v2, design 2026-08-14): "save
# without marking done". Deliberately kept OUT of VERDICTS — it never
# satisfies `apply_verdict`'s bracket/vendor-or-product requirements and
# must never count as done in `progress()` — but every row still carries
# it in the same `verdict` column so a reload shows it as still-pending
# (client-side filters treat it like blank/skipped) while restoring the
# exact partial state (span marks via `annotated_title`, builder
# components + the WFN/formatted-string field via `draft`, and notes).
IN_PROGRESS = "in_progress"

# The five closed values of the ``part`` component (WFN grammar, §5.3.2 of
# the ABNF reference) — the builder UI renders these as a <select>, never
# free text (design 2026-08-14, point 3).
PART_VALUES = ("*", "a", "o", "h", "-")

TERMS_LIMIT = 0  # 0 = unlimited (decision 2026-08-14: no cap; the
# dropdown scrolls — silent truncation would hide coexisting variants)


class VerdictError(ValueError):
    """A verdict payload that must not be written to the queue."""


def bind_components(components: dict) -> dict:
    """Deterministically bind an 11-component dict to a validated CPE 2.3.

    The exact notary code path, never a reimplementation: ``normalize_raw``
    per component, ``WFN.bind()``, then the ABNF validator as the single
    exit gate. ``*`` (or blank) means ANY, ``-`` means NA. Returns
    ``{ok, cpe, wfn, errors, components}`` where ``components`` echoes the
    normalized values actually bound.
    """
    kwargs = {}
    normalized = {}
    for attr in CPE_ATTRS:
        raw = str(components.get(attr, "") or "").strip()
        if raw in ("", "*"):
            kwargs[attr] = Logical.ANY
            normalized[attr] = "*"
        elif raw == "-":
            kwargs[attr] = Logical.NA
            normalized[attr] = "-"
        else:
            value = raw if attr == "part" else normalize_raw(raw)
            kwargs[attr] = value
            normalized[attr] = value
    try:
        wfn = WFN(**kwargs)
    except ValueError as exc:
        return {"ok": False, "cpe": "", "wfn": "", "errors": [str(exc)],
                "components": normalized}
    formatted = wfn.bind()
    result = validate_formatted_string(formatted)
    return {"ok": result.ok, "cpe": formatted if result.ok else "",
            "wfn": wfn.to_wfn_string(),
            "errors": [] if result.ok else list(result.errors),
            "components": normalized}


def components_present(components: dict | None) -> bool:
    """True when the builder was actually used (any non-wildcard value
    beyond the auto-prefilled ``part``/``target_sw`` defaults)."""
    if not components:
        return False
    return any(str(components.get(a, "") or "").strip() not in ("", "*")
               for a in CPE_ATTRS if a not in ("part", "target_sw"))


# -- official component search (typeahead) ----------------------------------
#
# Governance, not just UX (design 2026-08-14): a vendor/product picked from
# the dictionary instead of hand-typed avoids an invented spelling, which
# means fewer accidental NIEs and a cleaner gold set. Assists, never
# restricts — free text always stays valid (point 4 of the design note).


@dataclass
class TermsIndex:
    """In-memory view of the ``cpegen dict --export-terms`` sidecar.

    ``vendors`` and ``products`` are ``(value, cpe_count)`` pairs, each
    pre-sorted by descending count (ties broken alphabetically) so a
    cascade match can just filter-and-take without re-sorting.
    ``products`` is the vendor-agnostic aggregate (counts summed across
    every vendor that ships that product) — used when no vendor is
    selected yet, or the typed vendor doesn't match a known one.
    ``pairs`` narrows to one vendor's own products (Query B of the KGCS
    playbook: rank by that pair's own CPE volume, not the global one).
    """

    vendors: list[tuple[str, int]] = field(default_factory=list)
    pairs: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    products: list[tuple[str, int]] = field(default_factory=list)
    # O(1) membership sets for the dictionary-match stamp (portal v2 point
    # 4, design 2026-08-14) — derived from the three lists above, never
    # serialized, always rebuilt in `load()` alongside them.
    vendor_set: set = field(default_factory=set, repr=False, compare=False)
    pair_sets: dict = field(default_factory=dict, repr=False, compare=False)
    product_set: set = field(default_factory=set, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | str) -> "TermsIndex":
        path = Path(path)
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        vendors = [(v, n) for v, n in data.get("vendors", [])]
        pairs = {vendor: [(p, n) for p, n in products]
                 for vendor, products in data.get("pairs", {}).items()}
        agg: dict[str, int] = {}
        for products in pairs.values():
            for p, n in products:
                agg[p] = agg.get(p, 0) + n
        merged = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
        return cls(vendors=vendors, pairs=pairs, products=merged,
                   vendor_set={v for v, _ in vendors},
                   pair_sets={vendor: {p for p, _ in prods}
                              for vendor, prods in pairs.items()},
                   product_set={p for p, _ in merged})


def load_or_build_terms(terms_path: Path | str = DEFAULT_TERMS,
                        dictionary_path: Path | str = DEFAULT_SNAPSHOT
                        ) -> TermsIndex | None:
    """Load the typeahead sidecar, building it once from the snapshot if
    it's missing but the snapshot exists; ``None`` when neither is there
    (clean degradation to plain inputs, design point 5)."""
    terms_path = Path(terms_path)
    dictionary_path = Path(dictionary_path)
    if not terms_path.exists():
        if not dictionary_path.exists():
            return None
        print(f"cpegen review: no terms sidecar at {terms_path}; building "
              f"from {dictionary_path} (run 'cpegen dict --export-terms' "
              f"ahead of time to skip this at startup)...")
        build_terms_sidecar(dictionary_path, terms_path)
    try:
        return TermsIndex.load(terms_path)
    except (OSError, ValueError, KeyError) as exc:
        print(f"cpegen review: could not load terms sidecar {terms_path} "
              f"({exc}); the builder falls back to plain inputs.")
        return None


def match_terms(items: list[tuple[str, int]], q: str,
                limit: int = TERMS_LIMIT) -> list[dict]:
    """Cascade match: prefix literal -> substring -> ``clean()`` match.

    ``items`` must already be sorted by descending count; each bucket
    keeps that relative order. A value is placed in only the first bucket
    it qualifies for, so nothing is shown twice.
    """
    q = (q or "").strip()
    if not q:
        shown = items[:limit] if limit > 0 else items
        return [{"value": v, "count": n} for v, n in shown]
    ql = q.lower()
    qc = clean(q)
    prefix, substring, cleaned = [], [], []
    for v, n in items:
        vl = v.lower()
        if vl.startswith(ql):
            prefix.append((v, n))
        elif ql in vl:
            substring.append((v, n))
        elif qc and qc in clean(v):
            cleaned.append((v, n))
    ranked = prefix + substring + cleaned
    if limit > 0:
        ranked = ranked[:limit]
    return [{"value": v, "count": n} for v, n in ranked]


def handle_terms(terms: TermsIndex | None, field_name: str, q: str,
                 vendor: str = "") -> dict:
    """Pure handler behind ``GET /api/terms`` — no sockets required."""
    if field_name not in ("vendor", "product"):
        return {"ok": False, "error": f"unknown field {field_name!r}; "
                                       f"expected 'vendor' or 'product'"}
    if terms is None:
        return {"ok": True, "results": []}
    if field_name == "vendor":
        items = terms.vendors
    else:
        vendor = (vendor or "").strip()
        items = terms.pairs.get(vendor) if vendor else None
        if items is None:
            items = terms.products
    return {"ok": True, "results": match_terms(items, q)}


#: The three candidate categories `handle_dictcheck` can classify a filled
#: (vendor, product) pair into, from least to most novel (design
#: 2026-08-14, feedback "indicar si el CPE és un candidat a nou producte i
#: versió, o nova versió, o altres candidats"). This is a **heuristic**,
#: approved deliberately over extending the sidecar with per-pair version
#: data (which would touch `dictionary.py`/`build_terms_sidecar` and grow
#: the sidecar): the typeahead sidecar only ever indexed vendor/product,
#: never version, so "new version" is inferred from "the pair is already
#: known" rather than verified against an actual version list.
CANDIDATE_NEW_VERSION = "new_version"
CANDIDATE_NEW_PRODUCT_VERSION = "new_product_version"
CANDIDATE_OTHER = "other"


def handle_dictcheck(terms: TermsIndex | None, components: dict) -> dict:
    """Pure handler behind ``GET /api/dictcheck`` — portal v2 point 4
    (design 2026-08-14): per-field "does this value exist in the official
    (NVD) dictionary" stamp, reusing the same typeahead sidecar as
    ``/api/terms`` (never the full 1.77M-row snapshot; a field-level
    check, never version — the sidecar only ever indexed vendor/product).

    A vendor/product that doesn't exist in the official dictionary isn't
    wrong — it's a **candidate**: only a MotherHacker community dictionary
    or a client's custom dictionary can validate it for inclusion (same
    human+notary ceremony as a NIE, WP5/9.6). This endpoint only computes
    the stamp; it never writes anything.

    When both vendor and product are filled, ``category`` classifies the
    kind of candidate (heuristic — see :data:`CANDIDATE_NEW_VERSION`
    et al.; this review UI only ever sees titles the pipeline could not
    auto-resolve, so an already-known pair is treated as *at least* a new
    version candidate, never a silent "nothing to see here"):

    - the pair is already known -> :data:`CANDIDATE_NEW_VERSION` (the
      product line exists; if this exact version isn't already
      catalogued, it's a new version of it — not verified, inferred);
    - the vendor is known but not with this product ->
      :data:`CANDIDATE_NEW_PRODUCT_VERSION` (a new product line from a
      known vendor, so every version of it is new too);
    - the vendor itself isn't recognized -> :data:`CANDIDATE_OTHER`
      (new vendor, a rename, or a typo — needs the most scrutiny).

    ``None`` fields mean "nothing to check" (blank/ANY/NA, or no sidecar
    loaded at all) — never conflated with a confirmed "not found".
    """
    def value(attr: str) -> str:
        raw = str(components.get(attr, "") or "").strip()
        return raw if raw not in ("", "*", "-") else ""

    vendor, product = value("vendor"), value("product")
    if terms is None:
        return {"ok": True, "vendor_known": None, "product_known": None,
                "pair_known": None, "candidate": None, "category": None}

    # vendor_known / product_known are independent, global "does this
    # string exist anywhere in the dictionary" checks; pair_known is the
    # vendor-scoped one — a CPE is fundamentally about the (vendor,
    # product) pair, not either field in isolation.
    vendor_known = (vendor in terms.vendor_set) if vendor else None
    product_known = (product in terms.product_set) if product else None
    pair_known = (vendor in terms.pair_sets
                 and product in terms.pair_sets[vendor]) \
        if (vendor and product) else None

    if vendor and product:
        if pair_known:
            category = CANDIDATE_NEW_VERSION
        elif vendor_known:
            category = CANDIDATE_NEW_PRODUCT_VERSION
        else:
            category = CANDIDATE_OTHER
        candidate = True  # every filled pair is at least a version candidate
    else:
        category = None
        knowns = [k for k in (vendor_known, product_known) if k is not None]
        candidate = (not all(knowns)) if knowns else None
    return {"ok": True, "vendor_known": vendor_known,
            "product_known": product_known, "pair_known": pair_known,
            "candidate": candidate, "category": category}


# -- custom-dictionary inclusion (NIE ceremony, WP5, design 2026-08-15) ----
#
# "Els items marcats com a 'candidats' s'haurien de poder incloure al
# custom dictionary (per defecte MotherHacker)": once a row has a
# notary-validated CPE, a reviewer can mint it into a custom-dictionary
# CSV via the WP2 machinery in `dictionary.py` (`NIERecord`,
# `write_nie_record`) — never a second kind of dictionary or a parallel
# write path, exactly the NIE schema `LayeredDictionary`/`layered_dictionary`
# already consume.

#: MotherHacker is the community layer (open-source, R+I+D) — a single,
#: fixed CSV, never one-per-reviewer. Overridable via `cpegen review
#: --motherhacker-dict` for an alternate location (tests, a second machine).
DEFAULT_MOTHERHACKER_DICT = Path("data/dictionaries/motherhacker.csv")
#: Per-client custom dictionaries (HDATA layer) each get their own CSV
#: under this directory, named after the (slugified) target the reviewer
#: typed. Overridable via `--custom-dict-dir`.
DEFAULT_CUSTOM_DICT_DIR = Path("data/dictionaries/custom")

_MOTHERHACKER_ALIASES = {"motherhacker", "mother_hacker", "mh"}
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    """Free-text target name -> a filesystem-safe, lowercase slug.

    Blank input (or input that slugifies to nothing, e.g. all punctuation)
    falls back to "motherhacker" — never a blank/hidden filename.
    """
    s = _SLUG_RE.sub("_", (name or "").strip().lower()).strip("_")
    return s or "motherhacker"


def nie_target(name: str, motherhacker_path: Path,
               custom_dir: Path) -> tuple[Path, str]:
    """Free-text target -> ``(csv_path, origin_label)``.

    "MotherHacker" (any casing, or blank — the UI's own default) resolves
    to the fixed community CSV with ``origin="motherhacker"`` (the exact
    string :meth:`cpegen.dictionary.LayeredDictionary._layers` already
    special-cases). Any other name is slugified into its own per-client
    CSV under ``custom_dir``, with the slug itself as the origin label —
    this is what a later ``cpegen reclassify --custom-dict ... --origin
    <slug>`` would point back at.
    """
    slug = _slug(name)
    if slug in _MOTHERHACKER_ALIASES:
        return motherhacker_path, "motherhacker"
    return custom_dir / f"{slug}.csv", slug


def handle_nie_add(state: "ReviewState", motherhacker_path: Path,
                   custom_dir: Path, payload: dict) -> dict:
    """Pure handler behind ``POST /api/nie`` — mints one NIE from the
    row's already notary-validated CPE (``row["cpe"]``, set by
    :func:`bind_components`/``apply_verdict``).

    Refuses when the row has no bound CPE yet ("candidate" here means the
    vendor/product fields diverge from the official dictionary, per
    :func:`handle_dictcheck` — it does NOT mean the row is ready to mint;
    the ABNF grammar gate holds for every dictionary layer, not only the
    NVD one, so a NIE always needs a validated formatted string first).
    Re-validates ``row["cpe"]`` defensively (it should already be valid —
    only ``bind_components`` ever sets it — but a NIE is a governance
    write, never a place to trust stale state).
    """
    try:
        index = int(payload.get("index", -1))
    except (TypeError, ValueError):
        index = -1
    if not 0 <= index < len(state.rows):
        return {"ok": False, "error": f"row index out of range: {index}"}
    row = state.rows[index]
    cpe = (row.get("cpe") or "").strip()
    if not cpe:
        return {"ok": False, "error": "row has no notary-validated CPE yet "
                                       "— bind it in step 3 first"}
    result = validate_formatted_string(cpe)
    if not result.ok:
        return {"ok": False, "error": "stored CPE no longer validates: "
                                       + "; ".join(result.errors)}
    target_path, origin = nie_target(str(payload.get("target", "") or ""),
                                     motherhacker_path, custom_dir)
    record = NIERecord(
        cpe=cpe, origin=origin, human_identity=state.identity,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        evidence=str(payload.get("evidence", "") or "").strip(),
        motivating_titles=row.get("title", ""))
    write_nie_record(target_path, record)
    return {"ok": True, "cpe": cpe, "origin": origin, "path": str(target_path)}


# -- advanced review wizard: per-component assist registry (2026-08-21) ----
#
# "Advanced review" (design decided 2026-08-21): a step-by-step wizard —
# vendor -> product -> version (the other 8 components stay plain fields)
# — where every step shows CANDIDATES from specialised helpers. A
# candidate is ``{value, source, evidence, span?}``; the UI labels the
# source (title / dictionary / llm / web / transform), clicking one fills
# the field AND marks the title span, and free text always stays valid.
# Helpers PROPOSE; the notary (`bind_components`) validates — nothing here
# ever produces a CPE string, and an LLM answer is revalidated component
# by component before it is even shown. The server never fetches the web:
# "web" candidates are pre-built search URLs the reviewer opens in a new
# tab and judges. NVD live API was explicitly ruled out (no network).

ASSIST_COMPONENTS = ("vendor", "product", "version")

SOURCE_TITLE = "title"
SOURCE_DICTIONARY = "dictionary"
SOURCE_LLM = "llm"
SOURCE_WEB = "web"
SOURCE_TRANSFORM = "transform"

_WS_SPLIT_RE = re.compile(r"(\s+)")
MAX_NGRAM = 4


def title_tokens(title: str) -> list[str]:
    """Same tokenisation as the UI (``title.split(/(\\s+)/)`` keeping the
    separators as tokens) so a server-side span ``[a, b]`` indexes straight
    into the client's token array."""
    return [t for t in _WS_SPLIT_RE.split(title or "") if t]


def title_ngrams(tokens: list[str], max_n: int = MAX_NGRAM
                 ) -> list[tuple[str, int, int]]:
    """Word n-grams over the non-separator tokens as ``(text, a, b)`` with
    ``a``/``b`` token indices (inclusive) into ``tokens``. Longest first,
    so a 3-word hit ranks above the 1-word hit it contains."""
    words = [(k, t) for k, t in enumerate(tokens) if t.strip()]
    out = []
    for n in range(min(max_n, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            chunk = words[i:i + n]
            text = " ".join(t for _, t in chunk)
            out.append((text, chunk[0][0], chunk[-1][0]))
    return out


def term_key(value: str) -> str:
    """Lookup key shared by dictionary terms and title n-grams: the same
    ``clean()`` the matcher/typeahead use (lowercase, separators folded)
    so "Visual C++" meets ``visual_c\\+\\+`` and "Schneider Electric" meets
    both ``schneider-electric`` and ``schneider_electric``."""
    return clean((value or "").replace("\\", ""))


_ESCAPE_RE = re.compile(r"\\(.)")


def raw_term(value: str) -> str:
    """Dictionary term (formatted-string escaped, e.g. ``visual_c\+\+``)
    -> the RAW value the builder fields hold (``visual_c++``): the builder
    is un-escaped by contract (``bind_components`` -> ``normalize_raw`` ->
    ``WFN.bind`` escapes), so feeding it an escaped term would double-escape
    the CPE."""
    return _ESCAPE_RE.sub(r"\1", value or "")


def _lookup_map(items: list[tuple[str, int]]) -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {}
    for v, n in items:
        key = term_key(v)
        if key:
            out.setdefault(key, []).append((v, n))
    return out


def terms_lookups(terms: TermsIndex) -> dict:
    """Lazily built O(1) lookups over a :class:`TermsIndex` — cached on the
    instance (never serialised): ``vendors``/``products`` by
    :func:`term_key`, and ``owners`` = the inverted ``pairs`` (product ->
    vendors that ship it, for the reverse lookup helper)."""
    cache = getattr(terms, "_assist_lookups", None)
    if cache is not None:
        return cache
    owners: dict[str, list[tuple[str, int]]] = {}
    for vendor, prods in terms.pairs.items():
        for p, n in prods:
            owners.setdefault(term_key(p), []).append((vendor, n))
    for lst in owners.values():
        lst.sort(key=lambda vn: (-vn[1], vn[0]))
    cache = {"vendors": _lookup_map(terms.vendors),
             "products": _lookup_map(terms.products),
             "owners": owners}
    try:
        terms._assist_lookups = cache  # type: ignore[attr-defined]
    except AttributeError:
        pass
    return cache


@dataclass
class AssistContext:
    """Everything a helper may look at. Pure data — helpers never touch
    sockets, disk or the network."""

    component: str
    title: str
    components: dict = field(default_factory=dict)
    terms: TermsIndex | None = None
    llm_entities: dict | None = None   # one cached LLM answer per title
    tokens: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = title_tokens(self.title)

    def value(self, attr: str) -> str:
        raw = str(self.components.get(attr, "") or "").strip()
        return raw if raw not in ("*", "-") else ""


def candidate(value: str, source: str, evidence: str, span=None, **extra) -> dict:
    c = {"value": value, "source": source, "evidence": evidence,
         "span": list(span) if span else None}
    c.update(extra)
    return c


def _scan_title(ctx: AssistContext, lookup: dict, source: str,
                label: str) -> list[dict]:
    """Title n-grams vs one lookup map — the exact tier of the typeahead
    cascade (a whole n-gram equals a term under ``clean()``), never prefix/
    substring: a 2-letter n-gram must not light up half the dictionary."""
    out, seen = [], set()
    for text, a, b in title_ngrams(ctx.tokens):
        for v, n in lookup.get(term_key(text), ()):
            if v in seen:
                continue
            seen.add(v)
            out.append(candidate(raw_term(v), source,
                                 f"title span \"{text}\" = {label} {v} "
                                 f"({n} CPEs)", (a, b), count=n))
    return out


def helper_vendor_title_scan(ctx: AssistContext) -> list[dict]:
    if ctx.terms is None:
        return []
    return _scan_title(ctx, terms_lookups(ctx.terms)["vendors"],
                       SOURCE_TITLE, "vendor")


def helper_vendor_reverse_lookup(ctx: AssistContext) -> list[dict]:
    """Title n-grams vs the aggregated products -> the vendors that own
    them (``TermsIndex.pairs`` inverted). Finds the vendor when only the
    product name is in the title ("Acrobat Reader DC" -> adobe)."""
    if ctx.terms is None:
        return []
    owners = terms_lookups(ctx.terms)["owners"]
    out, seen = [], {}
    for text, a, b in title_ngrams(ctx.tokens):
        for vendor, n in owners.get(term_key(text), ()):
            if vendor in seen:
                continue
            seen[vendor] = True
            out.append(candidate(raw_term(vendor), SOURCE_DICTIONARY,
                                 f"owns product \"{text}\" found in the "
                                 f"title ({n} CPEs)", None, count=n))
    return out


def web_links(component: str, title: str, components: dict) -> list[dict]:
    """Pre-built search URLs. Pure string construction — the server never
    fetches anything; the reviewer opens them in a new tab and judges."""
    from urllib.parse import quote_plus
    product = str(components.get("product", "") or "").strip(" *-")
    vendor = str(components.get("vendor", "") or "").strip(" *-")
    subject = " ".join(x for x in (vendor, product) if x) or title
    if component == "vendor":
        query = f"{product or title} vendor"
    elif component == "product":
        query = f"{vendor} {title}".strip() + " product"
    else:
        query = f"{subject} version"
    nvd_kw = quote_plus(subject)
    return [
        candidate("DuckDuckGo", SOURCE_WEB, query,
                  url="https://duckduckgo.com/?q=" + quote_plus(query)),
        candidate("Google", SOURCE_WEB, query,
                  url="https://www.google.com/search?q=" + quote_plus(query)),
        candidate("NVD CPE search", SOURCE_WEB, subject,
                  url="https://nvd.nist.gov/products/cpe/search/results"
                      f"?namingFormat=2.3&keyword={nvd_kw}"),
    ]


def helper_web_links(ctx: AssistContext) -> list[dict]:
    return web_links(ctx.component, ctx.title, ctx.components)


def _find_span(tokens: list[str], value: str):
    """First title span whose words equal ``value`` under term_key (so an
    LLM/regex value can still mark the title); ``None`` when absent."""
    key = term_key(value)
    if not key:
        return None
    for text, a, b in title_ngrams(tokens, max_n=8):
        if term_key(text) == key:
            return (a, b)
    return None


def helper_llm(ctx: AssistContext) -> list[dict]:
    """Surface the cached LLM entity for this component — revalidated
    through the notary's own component path first (never shown raw,
    never auto-filled: the reviewer clicks it like any other candidate)."""
    ent = ctx.llm_entities or {}
    raw = ent.get(ctx.component)
    if not raw or not isinstance(raw, str):
        return []
    check = bind_components({ctx.component: raw})
    if not check["ok"]:
        return [candidate(raw, SOURCE_LLM,
                          "LLM proposal REJECTED by the notary: "
                          + "; ".join(check["errors"]), None, invalid=True)]
    conf = ent.get("confidence")
    ev = "LLM proposal (revalidated by the notary)"
    if isinstance(conf, (int, float)):
        ev += f", confidence {conf:.2f}"
    return [candidate(raw, SOURCE_LLM, ev, _find_span(ctx.tokens, raw),
                      normalized=check["components"][ctx.component])]


def helper_product_title_scan(ctx: AssistContext) -> list[dict]:
    """Title n-grams vs the chosen vendor's own products (``pairs[vendor]``,
    step 1's answer); falls back to the global aggregate when the vendor is
    blank or unknown."""
    if ctx.terms is None:
        return []
    vendor = ctx.value("vendor")
    if vendor and vendor in ctx.terms.pairs:
        lookup = _lookup_map(ctx.terms.pairs[vendor])
        label = f"product of {vendor}"
    else:
        lookup = terms_lookups(ctx.terms)["products"]
        label = "product (any vendor)"
    return _scan_title(ctx, lookup, SOURCE_TITLE, label)


#: Version shapes found in inventory titles. Order = display order; a
#: token is reported once, under the first pattern that matches it.
VERSION_PATTERNS = (
    ("dotted", re.compile(r"^v?\d+(?:\.\d+)+[a-z0-9._-]*$", re.I)),
    ("year", re.compile(r"^(?:19|20)\d{2}$")),
    ("build", re.compile(r"^\d{4,}$")),
    ("release", re.compile(r"^r\d+[a-z]?$", re.I)),
    ("bare", re.compile(r"^v?\d+[a-z]?$", re.I)),
)
_SP_RE = re.compile(r"\b(sp\s?\d+|service\s+pack\s+\d+)\b", re.I)
_ARCH_RE = re.compile(r"\b(x64|x86|x86_64|amd64|arm64|ia64|win64|win32|32-bit|64-bit)\b", re.I)


def helper_version_regex(ctx: AssistContext) -> list[dict]:
    out, seen = [], set()
    for k, tok in enumerate(ctx.tokens):
        word = tok.strip().strip("()[],;:")
        if not word or not any(ch.isdigit() for ch in word):
            continue
        for label, rx in VERSION_PATTERNS:
            if rx.match(word):
                if word in seen:
                    break
                seen.add(word)
                out.append(candidate(word, SOURCE_TITLE,
                                     f"{label} version token in the title",
                                     (k, k), kind=label))
                break
    return out


def helper_version_transforms(ctx: AssistContext) -> list[dict]:
    """Explicit one-click transforms — buttons, never silent rewrites.
    ``apply`` is the exact field set the click performs."""
    out = []
    version = ctx.value("version")
    if version and re.match(r"^v\d", version, re.I):
        out.append(candidate(version[1:], SOURCE_TRANSFORM,
                             f"strip leading v: {version} -> {version[1:]}",
                             None, apply={"version": version[1:]}))
    m = _SP_RE.search(ctx.title)
    if m:
        sp = re.sub(r"service\s+pack\s+", "sp", m.group(1), flags=re.I)
        sp = re.sub(r"\s+", "", sp).lower()
        out.append(candidate(sp, SOURCE_TRANSFORM,
                             f"\"{m.group(1)}\" -> update = {sp}", None,
                             apply={"update": sp}))
    m = _ARCH_RE.search(ctx.title)
    if m:
        hw = m.group(1).lower()
        out.append(candidate(hw, SOURCE_TRANSFORM,
                             f"\"{m.group(1)}\" -> target_hw = {hw}", None,
                             apply={"target_hw": hw}))
    return out


#: The registry: component -> ordered helpers. Adding a helper = adding a
#: pure function here; the endpoint, the UI labelling and the tests need
#: nothing else. Every helper degrades to ``[]`` with no sidecar / no LLM.
ASSIST_HELPERS: dict[str, list] = {
    "vendor": [helper_vendor_title_scan, helper_vendor_reverse_lookup,
               helper_llm, helper_web_links],
    "product": [helper_product_title_scan, helper_llm, helper_web_links],
    "version": [helper_version_regex, helper_version_transforms, helper_llm,
                helper_web_links],
}


class LLMAssist:
    """One LLM call per title, memoised — serves every wizard step.

    Wraps an :mod:`cpegen.extractor` provider (anthropic / openai /
    lmstudio / mock ...) through :func:`cpegen.extractor.extract`: the
    model returns JSON entities, never a CPE. ``None`` provider = disabled.
    """

    ENTITY_KEYS = ("vendor", "product", "version", "update", "target_sw")

    def __init__(self, provider=None):
        self.provider = provider
        self.cache: dict[str, dict] = {}

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    @property
    def name(self) -> str:
        if self.provider is None:
            return ""
        return getattr(self.provider, "name", None) or type(self.provider).__name__

    def entities(self, title: str) -> dict | None:
        if not self.enabled:
            return None
        if title in self.cache:
            return self.cache[title]
        from .extractor import extract
        ext = extract(self.provider, title)
        if ext.error:
            ent = {"error": ext.error}
        else:
            ent = {k: getattr(ext, k) for k in self.ENTITY_KEYS}
            ent["confidence"] = ext.confidence
        self.cache[title] = ent
        return ent


def handle_assist(terms: TermsIndex | None, payload: dict,
                  llm: LLMAssist | None = None) -> dict:
    """Pure handler behind ``POST /api/assist``.

    ``payload``: ``component`` (vendor|product|version), ``title``, the
    builder ``components`` so far, optional ``llm_entities`` (the answer a
    previous step already cached client-side / in the draft — reused, no
    second call) and ``use_llm`` (default true). Returns ``{ok,
    component, candidates, llm_entities, llm}`` where ``llm`` states
    whether an assistant is configured, so the UI can say why a source is
    absent instead of showing a silent blank.
    """
    component = str(payload.get("component", "") or "")
    if component not in ASSIST_COMPONENTS:
        return {"ok": False, "error": f"unknown component {component!r}; "
                                       f"expected one of {ASSIST_COMPONENTS}"}
    title = str(payload.get("title", "") or "")
    components = payload.get("components") if isinstance(
        payload.get("components"), dict) else {}
    entities = payload.get("llm_entities") if isinstance(
        payload.get("llm_entities"), dict) else None
    use_llm = bool(payload.get("use_llm", True))
    if entities is None and use_llm and llm is not None and llm.enabled:
        entities = llm.entities(title)
    ctx = AssistContext(component=component, title=title,
                        components=components, terms=terms,
                        llm_entities=entities)
    cands: list[dict] = []
    for helper in ASSIST_HELPERS[component]:
        cands.extend(helper(ctx))
    return {"ok": True, "component": component, "candidates": cands,
            "llm_entities": entities,
            "llm": {"enabled": bool(llm and llm.enabled),
                    "provider": llm.name if llm and llm.enabled else "",
                    "error": (entities or {}).get("error", "")},
            "terms": terms is not None}


@dataclass
class ReviewState:
    """The queue rows plus the incremental-save bookkeeping."""

    queue_path: Path
    output_path: Path
    identity: str
    rows: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, queue_path: Path | str, identity: str,
             output_path: Path | str | None = None) -> "ReviewState":
        queue_path = Path(queue_path)
        output_path = Path(output_path) if output_path else queue_path
        if not identity or not identity.strip():
            raise VerdictError("identity is required (spec §6.4: every "
                               "human decision records who took it)")
        # Resume from the output file when it already carries verdicts.
        source = output_path if output_path.exists() else queue_path
        rows: list[dict] = []
        with open(source, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = [f for f in QUEUE_FIELDS if f not in (reader.fieldnames or [])]
            if missing:
                raise VerdictError(
                    f"not an annotation queue (missing columns: {missing})")
            for row in reader:
                rows.append({f: (row.get(f) or "") for f in CSV_FIELDS})
        if not rows:
            raise VerdictError(f"empty queue: {source}")
        return cls(queue_path=queue_path, output_path=output_path,
                   identity=identity.strip(), rows=rows)

    # -- verdict handling -------------------------------------------------

    def apply_verdict(self, index: int, verdict: str, annotated_title: str,
                      notes: str = "", components: dict | None = None) -> dict:
        if not 0 <= index < len(self.rows):
            raise VerdictError(f"row index out of range: {index}")
        if verdict not in VERDICTS:
            raise VerdictError(f"unknown verdict {verdict!r}; "
                               f"expected one of {VERDICTS}")
        annotated_title = (annotated_title or "").strip()
        if verdict == "annotated":
            entities = dict()
            for value, label in ENTITY_RE.findall(annotated_title):
                entities.setdefault(label, value.strip())
            if not entities:
                raise VerdictError(
                    "verdict 'annotated' needs at least one "
                    "[text](cpe_vendor|cpe_product|cpe_version) bracket")
            if "cpe_vendor" not in entities and "cpe_product" not in entities:
                raise VerdictError(
                    "verdict 'annotated' needs a vendor or a product bracket")
        else:
            annotated_title = ""  # never carry stale brackets on non-gold rows
        cpe = ""
        if verdict == "annotated" and components_present(components):
            bound = bind_components(components or {})
            if not bound["ok"]:
                raise VerdictError("CPE does not bind/validate: "
                                   + "; ".join(bound["errors"]))
            cpe = bound["cpe"]  # only a notary-validated string is ever stored
        row = self.rows[index]
        row["cpe"] = cpe
        row["annotated_title"] = annotated_title
        row["verdict"] = verdict
        row["annotator"] = self.identity
        row["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        row["notes"] = (notes or "").strip()
        row["draft"] = ""  # a final verdict retires any in-progress draft
        self.save()
        self.append_history(index, row)
        return dict(row)

    # -- draft persistence (in_progress; portal v2, design 2026-08-14) ----

    def save_progress(self, index: int, annotated_title: str = "",
                      notes: str = "", components: dict | None = None,
                      cpe_text: str = "", extra_marks: dict | None = None,
                      llm_entities: dict | None = None) -> dict:
        """Persist partial work without a final verdict ("save without
        marking done"). Keeps the row pending — `verdict` becomes
        ``in_progress``, which is neither in :data:`VERDICTS` nor counted
        as done by :meth:`progress` — while round-tripping every piece of
        client-side draft state: gold span marks (the same RASA-bracket
        `annotated_title` column a real annotation uses, so the existing
        resume-from-brackets logic restores them unchanged), the builder's
        11 components and the WFN/formatted-string field, and the
        non-gold span marks for the other CPE components (``update``,
        ``edition``, ... — title highlights that only ever feed the
        builder, never the frozen vendor/product/version annotation; kept
        as ``{token_index: component}``) — all three inside the new
        `draft` JSON column — and notes.

        Refuses to downgrade a row that already carries a final verdict —
        re-open it with a real verdict action instead of a draft save.
        """
        if not 0 <= index < len(self.rows):
            raise VerdictError(f"row index out of range: {index}")
        row = self.rows[index]
        if row["verdict"] in ("annotated", "not_software"):
            raise VerdictError(
                "row already has a final verdict; re-annotate it with a "
                "real verdict action instead of a draft save")
        row["verdict"] = IN_PROGRESS
        row["annotated_title"] = (annotated_title or "").strip()
        row["notes"] = (notes or "").strip()
        row["draft"] = json.dumps({
            "components": components or {},
            "cpe_text": (cpe_text or "").strip(),
            "extra_marks": extra_marks or {},
            # the wizard's one-call-per-title LLM answer (2026-08-21), so
            # a resumed draft never pays for a second call
            "llm_entities": llm_entities or {},
        })
        row["annotator"] = self.identity
        row["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save()
        return dict(row)

    # -- verdict history (append-only JSONL beside the output CSV) --------
    #
    # Drafts are not verdicts and are never logged here — only a real
    # `apply_verdict` call appends, so the sidebar's "verdict history"
    # shows human decisions, not every keystroke.

    @property
    def history_path(self) -> Path:
        return self.output_path.with_name(self.output_path.stem + ".history.jsonl")

    def append_history(self, index: int, row: dict) -> None:
        entry = {
            "row_index": index,
            "title": row.get("title", ""),
            "verdict": row.get("verdict", ""),
            "annotator": row.get("annotator", ""),
            "timestamp": row.get("timestamp", ""),
            "notes": row.get("notes", ""),
            "cpe": row.get("cpe", ""),
        }
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def read_history(self, index: int) -> list[dict]:
        """All past verdicts for one row, oldest first."""
        if not self.history_path.exists():
            return []
        out = []
        with open(self.history_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("row_index") == index:
                    out.append(entry)
        return out

    # -- persistence ------------------------------------------------------

    def save(self) -> None:
        """Atomic full rewrite: temp file in the same directory + replace."""
        tmp = self.output_path.with_name(self.output_path.name + ".tmp")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in self.rows:
                writer.writerow(row)
        os.replace(tmp, self.output_path)

    # -- read model for the UI -------------------------------------------

    def progress(self) -> dict:
        counts = {v: 0 for v in VERDICTS}
        for row in self.rows:
            if row["verdict"] in counts:
                counts[row["verdict"]] += 1
        done = counts["annotated"] + counts["not_software"]
        return {"total": len(self.rows), "done": done, **counts}

    def as_payload(self) -> dict:
        return {
            "identity": self.identity,
            "queue": str(self.queue_path),
            "output": str(self.output_path),
            "progress": self.progress(),
            "rows": self.rows,
        }


# -- HTTP layer (thin: parse, delegate, serialize) -------------------------


def handle_state(state: ReviewState) -> dict:
    return state.as_payload()


def handle_verdict(state: ReviewState, payload: dict) -> dict:
    try:
        row = state.apply_verdict(
            index=int(payload.get("index", -1)),
            verdict=str(payload.get("verdict", "")),
            annotated_title=str(payload.get("annotated_title", "")),
            notes=str(payload.get("notes", "")),
            components=payload.get("components")
            if isinstance(payload.get("components"), dict) else None,
        )
    except VerdictError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "row": row, "progress": state.progress()}


def handle_progress(state: ReviewState, payload: dict) -> dict:
    try:
        row = state.save_progress(
            index=int(payload.get("index", -1)),
            annotated_title=str(payload.get("annotated_title", "")),
            notes=str(payload.get("notes", "")),
            components=payload.get("components")
            if isinstance(payload.get("components"), dict) else None,
            cpe_text=str(payload.get("cpe_text", "")),
            extra_marks=payload.get("extra_marks")
            if isinstance(payload.get("extra_marks"), dict) else None,
            llm_entities=payload.get("llm_entities")
            if isinstance(payload.get("llm_entities"), dict) else None,
        )
    except VerdictError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "row": row}


def handle_history(state: ReviewState, index: int) -> dict:
    if not 0 <= index < len(state.rows):
        return {"ok": False, "error": f"row index out of range: {index}"}
    return {"ok": True, "entries": state.read_history(index)}


def handle_unbind(cpe: str) -> dict:
    """Pure handler behind ``POST /api/unbind`` — formatted string ->
    builder components, the mirror of ``bind_components``.

    The editable "WFN" field holds the CPE 2.3 **formatted string**
    (``cpe:2.3:...``): that is the one representation ``WFN.bind()`` /
    ``WFN.unbind()`` / ``validate_formatted_string`` already round-trip
    without any new notary code (reuse, not rewrite). The informal
    ``wfn:[...]`` notation stays a read-only echo of
    ``WFN.to_wfn_string()``, exactly as ``/api/bind`` already returns it.
    """
    cpe = (cpe or "").strip()
    if not cpe:
        return {"ok": False, "errors": ["empty"]}
    result = validate_formatted_string(cpe)
    if not result.ok:
        return {"ok": False, "errors": list(result.errors)}
    try:
        wfn = WFN.unbind(cpe)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)]}
    components = {}
    for attr in CPE_ATTRS:
        value = getattr(wfn, attr)
        if value is Logical.ANY:
            components[attr] = "*"
        elif value is Logical.NA:
            components[attr] = "-"
        else:
            components[attr] = value
    return {"ok": True, "cpe": cpe, "wfn": wfn.to_wfn_string(),
            "components": components}


class _Handler(BaseHTTPRequestHandler):
    state: ReviewState  # set by serve()
    terms: "TermsIndex | None" = None  # set by serve(); None degrades cleanly
    motherhacker_dict_path: Path = DEFAULT_MOTHERHACKER_DICT  # set by serve()
    custom_dict_dir: Path = DEFAULT_CUSTOM_DICT_DIR  # set by serve()
    llm: "LLMAssist | None" = None  # set by serve(); None = no LLM assist

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urlsplit(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send(200, UI_ASSET.read_bytes(), "text/html; charset=utf-8")
        elif parsed.path == "/api/state":
            self._send_json(handle_state(self.state))
        elif parsed.path == "/api/terms":
            qs = parse_qs(parsed.query)
            result = handle_terms(
                self.terms,
                field_name=(qs.get("field") or [""])[0],
                q=(qs.get("q") or [""])[0],
                vendor=(qs.get("vendor") or [""])[0],
            )
            self._send_json(result, 200 if result["ok"] else 400)
        elif parsed.path == "/api/history":
            qs = parse_qs(parsed.query)
            try:
                index = int((qs.get("index") or ["-1"])[0])
            except ValueError:
                index = -1
            result = handle_history(self.state, index)
            self._send_json(result, 200 if result["ok"] else 400)
        elif parsed.path == "/api/dictcheck":
            qs = parse_qs(parsed.query)
            result = handle_dictcheck(self.terms, {
                "vendor": (qs.get("vendor") or [""])[0],
                "product": (qs.get("product") or [""])[0],
            })
            self._send_json(result, 200 if result["ok"] else 400)
        else:
            self._send_json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/api/verdict", "/api/bind", "/api/progress",
                             "/api/unbind", "/api/nie", "/api/assist"):
            self._send_json({"ok": False, "error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "invalid JSON"}, 400)
            return
        if self.path == "/api/bind":
            self._send_json(bind_components(payload.get("components") or {}))
            return
        if self.path == "/api/unbind":
            self._send_json(handle_unbind(str(payload.get("cpe", ""))))
            return
        if self.path == "/api/progress":
            result = handle_progress(self.state, payload)
            self._send_json(result, 200 if result["ok"] else 422)
            return
        if self.path == "/api/nie":
            result = handle_nie_add(self.state, self.motherhacker_dict_path,
                                    self.custom_dict_dir, payload)
            self._send_json(result, 200 if result["ok"] else 422)
            return
        if self.path == "/api/assist":
            result = handle_assist(self.terms, payload, self.llm)
            self._send_json(result, 200 if result["ok"] else 400)
            return
        result = handle_verdict(self.state, payload)
        self._send_json(result, 200 if result["ok"] else 422)

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        pass


def serve(queue_path: Path | str, identity: str, port: int = 8765,
          output_path: Path | str | None = None,
          terms_path: Path | str | None = None,
          dictionary_path: Path | str | None = None,
          motherhacker_dict: Path | str | None = None,
          custom_dict_dir: Path | str | None = None,
          assist_provider: str | None = None,
          assist_model: str | None = None) -> None:
    """Blocking server loop; Ctrl+C stops it (all verdicts already saved).

    ``assist_provider`` (anthropic / openai / lmstudio / mock / replay)
    turns on the wizard's LLM helper — one call per title, memoised;
    ``None`` leaves the wizard fully functional with local helpers only.
    """
    state = ReviewState.load(queue_path, identity=identity,
                             output_path=output_path)
    llm = LLMAssist(None)
    if assist_provider:
        from .extractor import get_provider
        llm = LLMAssist(get_provider(assist_provider, assist_model))
    terms = load_or_build_terms(
        terms_path or DEFAULT_TERMS, dictionary_path or DEFAULT_SNAPSHOT)
    mh_path = Path(motherhacker_dict) if motherhacker_dict else DEFAULT_MOTHERHACKER_DICT
    cd_dir = Path(custom_dict_dir) if custom_dict_dir else DEFAULT_CUSTOM_DICT_DIR
    handler = type("BoundHandler", (_Handler,), {
        "state": state, "terms": terms,
        "motherhacker_dict_path": mh_path, "custom_dict_dir": cd_dir,
        "llm": llm,
    })
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    p = state.progress()
    print(f"cpegen review — {state.queue_path}")
    print(f"  reviewer: {state.identity}")
    print(f"  progress: {p['done']}/{p['total']} done "
          f"({p['annotated']} annotated, {p['not_software']} not-software, "
          f"{p['skipped']} skipped)")
    if terms is None:
        print(f"  terms:    none found — vendor/product fields are plain "
              f"text (build with 'cpegen dict --export-terms')")
    else:
        print(f"  terms:    {len(terms.vendors)} vendors, "
              f"{sum(len(v) for v in terms.pairs.values())} vendor:product "
              f"pairs — typeahead enabled")
    print(f"  dicts:    MotherHacker -> {mh_path}  |  custom -> {cd_dir}/<target>.csv")
    print(f"  assist:   {('LLM helper via ' + llm.name) if llm.enabled else 'local helpers only (no LLM; --assist-provider to enable)'}")
    print(f"  open:     http://127.0.0.1:{port}/   (Ctrl+C to stop; every "
          f"verdict is already on disk)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
