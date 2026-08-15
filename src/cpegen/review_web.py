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
                      cpe_text: str = "", extra_marks: dict | None = None
                      ) -> dict:
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
                             "/api/unbind", "/api/nie"):
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
        result = handle_verdict(self.state, payload)
        self._send_json(result, 200 if result["ok"] else 422)

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        pass


def serve(queue_path: Path | str, identity: str, port: int = 8765,
          output_path: Path | str | None = None,
          terms_path: Path | str | None = None,
          dictionary_path: Path | str | None = None,
          motherhacker_dict: Path | str | None = None,
          custom_dict_dir: Path | str | None = None) -> None:
    """Blocking server loop; Ctrl+C stops it (all verdicts already saved)."""
    state = ReviewState.load(queue_path, identity=identity,
                             output_path=output_path)
    terms = load_or_build_terms(
        terms_path or DEFAULT_TERMS, dictionary_path or DEFAULT_SNAPSHOT)
    mh_path = Path(motherhacker_dict) if motherhacker_dict else DEFAULT_MOTHERHACKER_DICT
    cd_dir = Path(custom_dict_dir) if custom_dict_dir else DEFAULT_CUSTOM_DICT_DIR
    handler = type("BoundHandler", (_Handler,), {
        "state": state, "terms": terms,
        "motherhacker_dict_path": mh_path, "custom_dict_dir": cd_dir,
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
    print(f"  open:     http://127.0.0.1:{port}/   (Ctrl+C to stop; every "
          f"verdict is already on disk)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
