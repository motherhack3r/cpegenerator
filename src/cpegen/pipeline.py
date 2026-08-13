"""End-to-end pipeline: title -> extraction -> WFN -> validation -> lookup
-> M1-M3 classification, with optional Phase-4 agent escalation.

Invariant (non-negotiable): no CPE leaves this pipeline without passing
the deterministic ABNF validator. If a bound string fails validation the
row is flagged and carries no CPE.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .agent import AgentResult, get_agent_provider, run_agent
from .dictionary import Lookup, lookup_for
from .extractor import Extraction, extract, extract_per_field, get_provider
from .matcher import HIGH_CONFIDENCE, canonicalize, classify
from .goldset import GoldRecord, load_gold
from .metrics import Report
from .nvd import NVDClient
from .tools import ToolBox
from .validator import validate_formatted_string
from .wfn import WFN, Logical, normalize_raw


@dataclass
class RowResult:
    title: str
    vendor: str = ""
    product: str = ""
    version: str = ""
    update: str = ""
    target_sw: str = ""
    confidence: float = 0.0
    cpe: str = ""
    valid: bool = False
    validation_errors: str = ""
    rule: str = ""
    rule_name: str = ""
    match_similarity: float = 0.0
    matched_cpe: str = ""
    error: str = ""
    stage: str = "fast"      # which pass produced this row: fast | agent
    fast_rule: str = ""      # rule from the fast pass when escalated
    agent_turns: int = 0
    note: str = ""
    latency_ms: int = 0      # wall time of the extraction call(s)
    tokens_in: int = 0       # usage reported by the provider, when any
    tokens_out: int = 0
    # --- canonicalization layer (WP1 step 2, 2026-08-13) ---
    # vendor/product above stay exactly as the reader extracted them (the
    # NER evaluation reads them); the canonical columns say what the
    # dictionary calls the same thing, and cpe carries the canonical form.
    canonical_vendor: str = ""
    canonical_product: str = ""
    part: str = ""
    dice: float = 0.0
    margin: float = 0.0
    decision: str = ""       # auto | flagged | review | weak | none
    deprecated: bool = False
    lookup_source: str = ""  # pair | alias | dice | union | api | miss
    needs_review: bool = False
    review_reason: str = ""
    version_source: str = ""  # dict | range | outside | unknown


def build_wfn(ext: Extraction) -> WFN | None:
    """Deterministically build a WFN from raw extracted entities."""
    if not ext.vendor and not ext.product:
        return None

    def norm(value: str | None) -> str | Logical:
        return normalize_raw(value) if value else Logical.ANY

    return WFN(
        part="a",  # inventory titles are applications; o/h handled in later phases
        vendor=norm(ext.vendor),
        product=norm(ext.product),
        version=norm(ext.version),
        update=norm(ext.update),
        target_sw=norm(ext.target_sw),
    )


def process_title(title: str, provider, nvd: NVDClient,
                  extract_fn=extract) -> RowResult:
    """Run the fast pipeline on one title (single-shot or per-field)."""
    row = RowResult(title=title)

    t0 = time.monotonic()
    ext = extract_fn(provider, title)
    row.latency_ms = int((time.monotonic() - t0) * 1000)
    usage = getattr(provider, "last_usage", None) or {}
    row.tokens_in = usage.get("in", 0)
    row.tokens_out = usage.get("out", 0)
    if ext.error:
        row.error = ext.error
        return row
    row.vendor = ext.vendor or ""
    row.product = ext.product or ""
    row.version = ext.version or ""
    row.update = ext.update or ""
    row.target_sw = ext.target_sw or ""
    row.confidence = ext.confidence

    wfn = build_wfn(ext)
    if wfn is None:
        row.error = "no vendor/product extracted"
        return row

    # The gate: deterministic ABNF validation. LLM proposes, code validates.
    candidate = wfn.bind()
    result = validate_formatted_string(candidate)
    row.valid = result.ok
    if not result.ok:
        row.validation_errors = "; ".join(result.errors)
        return row  # invalid CPE never leaves the pipeline
    row.cpe = candidate

    # Dictionary lookup (exact pair -> vendor alias -> clean+Dice) and
    # M1-M4 classification on the canonicalized WFN.
    vendor = wfn.vendor if isinstance(wfn.vendor, str) else None
    product = wfn.product if isinstance(wfn.product, str) else None
    try:
        lk = lookup_for(nvd, vendor, product, title=title)
    except Exception as exc:  # degrade to no candidates, keep the run alive
        lk = Lookup([], None, "error")
        row.note = f"nvd lookup failed: {exc}"
    match = classify(wfn, lk.candidates, title=title,
                     resolution=lk.resolution, ranges=lk.ranges)
    apply_match(row, match, wfn, lk)
    return row


def apply_match(row: RowResult, match, wfn: WFN, lk: Lookup) -> RowResult:
    """Copy a MatchResult onto a row, re-binding the canonical CPE.

    The invariant is unchanged: the canonical string goes through the
    ABNF validator again, and a row that fails it keeps the CPE it had.
    """
    row.rule = match.rule
    row.rule_name = match.rule_name
    row.match_similarity = round(match.similarity, 4)
    row.matched_cpe = match.matched_cpe or ""
    row.canonical_vendor = match.canonical_vendor
    row.canonical_product = match.canonical_product
    row.part = match.part
    row.dice = match.dice
    row.margin = match.margin
    row.decision = match.decision
    row.deprecated = match.deprecated
    row.lookup_source = lk.source
    row.review_reason = match.review_reason
    row.needs_review = match.needs_review
    row.version_source = match.version_source

    effective = canonicalize(wfn, lk.resolution)
    canonical = effective.bind()
    if canonical != row.cpe:
        result = validate_formatted_string(canonical)
        if result.ok:
            row.cpe = canonical
        else:  # never emit an unvalidated CPE; keep the previous one
            row.note = (row.note + "; " if row.note else "") + \
                "canonical CPE failed validation"
    return row


def agent_row(res: AgentResult) -> RowResult:
    """Convert an AgentResult into a pipeline RowResult."""
    return RowResult(
        title=res.title, vendor=res.vendor, product=res.product,
        version=res.version, update=res.update, target_sw=res.target_sw,
        confidence=res.confidence, cpe=res.cpe, valid=res.valid,
        validation_errors=res.validation_errors, rule=res.rule,
        rule_name=res.rule_name, match_similarity=res.match_similarity,
        matched_cpe=res.matched_cpe, error=res.error,
        stage="agent", agent_turns=res.turns, note=res.note,
    )


def needs_escalation(row: RowResult) -> bool:
    """Fast-pass rows that did not reach a high-confidence M1x result."""
    return bool(row.error) or not row.valid or row.rule not in HIGH_CONFIDENCE


def escalate_title(row: RowResult, agent_provider, toolbox: ToolBox,
                   max_turns: int) -> RowResult:
    """Run the agent on one escalated title, keeping fast-pass provenance."""
    context = ""
    if not row.error:
        context = (f"vendor={row.vendor!r} product={row.product!r} "
                   f"version={row.version!r} update={row.update!r} "
                   f"target_sw={row.target_sw!r} -> rule {row.rule or 'none'}")
    res = run_agent(row.title, agent_provider, toolbox,
                    fast_pass_context=context, max_turns=max_turns)
    new_row = agent_row(res)
    new_row.fast_rule = row.rule
    if new_row.error and not row.error:
        # agent failed outright: keep the fast-pass result, note the failure
        row.note = f"agent failed: {new_row.error}"
        return row
    return new_row


def evaluate(rows: list[RowResult], gold: list[GoldRecord]) -> Report:
    """Score pipeline output against the gold set."""
    report = Report()
    gold_by_title = {g.title: g for g in gold}
    for row in rows:
        g = gold_by_title.get(row.title)
        if g is None:
            continue
        if row.error:
            report.extraction_errors += 1
        report.add_entities(g, {
            "vendor": row.vendor or None,
            "product": row.product or None,
            "version": row.version or None,
            "target_sw": row.target_sw or None,
        })
        if row.valid:
            report.cpe_valid += 1
        # Gold CPE built with the same deterministic normalization.
        gold_wfn = WFN(
            part="a",
            vendor=normalize_raw(g.vendor) if g.vendor else Logical.ANY,
            product=normalize_raw(g.product) if g.product else Logical.ANY,
            version=normalize_raw(g.version) if g.version else Logical.ANY,
            target_sw=normalize_raw(g.target_sw) if g.target_sw else Logical.ANY,
        )
        # Compare on v:p:v + target_sw (update excluded: gold lacks update)
        gen = WFN.unbind(row.cpe) if row.cpe else None
        if gen is not None and (
            (gen.vendor, gen.product, gen.version, gen.target_sw)
            == (gold_wfn.vendor, gold_wfn.product, gold_wfn.version, gold_wfn.target_sw)
        ):
            report.cpe_exact += 1
        if row.rule:
            report.rule_counts[row.rule] += 1
    return report


def run(input_path: Path, output_dir: Path, provider_name: str | None = None,
        model: str | None = None, offline: bool = False,
        limit: int | None = None, cache_path: Path | None = None,
        agent_mode: str = "off", max_turns: int = 8,
        dictionary_path: Path | None = None,
        extract_mode: str = "single",
        resume: bool = False,
        progress=None) -> tuple[list[RowResult], Report | None]:
    """Run the pipeline over a CSV of titles; evaluate if annotations exist.

    agent_mode:
        "off"      - fast single-shot pass only (MVP behaviour)
        "escalate" - fast pass, then the agent on every non-M1x row
        "all"      - agent on every title (benchmark arm C)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    nvd = NVDClient(cache_path or Path("data/cache/nvd_cache.json"),
                    offline=offline)
    if dictionary_path is not None:
        from .dictionary import HybridDictionary, LocalDictionary
        nvd = HybridDictionary(LocalDictionary.load(dictionary_path), nvd)
    toolbox = ToolBox(nvd=nvd)
    agent_provider = (get_agent_provider(provider_name, model=model)
                      if agent_mode in ("escalate", "all") else None)
    provider = get_provider(provider_name, model=model) if agent_mode != "all" else None

    gold = load_gold(input_path)
    if limit:
        gold = gold[:limit]

    # Streaming write with optional resume: every processed row lands on
    # disk immediately, so a killed multi-day RAW run continues where it
    # stopped (titles already present in results.csv are skipped).
    results_path = output_dir / "results.csv"
    done: set[str] = set()
    if resume and results_path.exists():
        with open(results_path, newline="", encoding="utf-8") as fh:
            for prev in csv.DictReader(fh):
                done.add(prev["title"])

    fieldnames = list(asdict(RowResult(title="")).keys())
    rows: list[RowResult] = []
    with open(results_path, "a" if done else "w", newline="",
              encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not done:
            writer.writeheader()
        for i, g in enumerate(gold):
            if g.title in done:
                if progress:
                    progress(i + 1, len(gold))
                continue
            if agent_mode == "all":
                row = agent_row(run_agent(g.title, agent_provider, toolbox,
                                          max_turns=max_turns))
            else:
                extract_fn = (extract_per_field if extract_mode == "per-field"
                              else extract)
                row = process_title(g.title, provider, nvd,
                                    extract_fn=extract_fn)
                if agent_mode == "escalate" and needs_escalation(row):
                    row = escalate_title(row, agent_provider, toolbox,
                                         max_turns)
            rows.append(row)
            writer.writerow(asdict(row))
            fh.flush()
            if progress:
                progress(i + 1, len(gold))

    report = None
    has_annotations = any(g.vendor or g.product for g in gold)
    if has_annotations and rows:
        # On resume, only freshly processed rows are evaluated.
        report = evaluate(rows, [g for g in gold if g.title not in done])
        (output_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    return rows, report


def reclassify_results(results_path: Path, output_dir: Path, nvd,
                       progress=None) -> dict:
    """Re-run dictionary lookup + M1-M3 classification over an existing
    results.csv WITHOUT re-extracting.

    The extractions (vendor/product/version/update/target_sw) stored in
    the rows are reused verbatim: the WFN is rebuilt deterministically,
    revalidated, and reclassified against the (possibly fixed or
    refreshed) dictionary. Rows without a valid CPE are copied through
    untouched. Motivation: a classification-layer fix should not cost
    hours of GPU re-extraction (10k RAW pilot, 2026-08-11).

    Returns stats including the rule transition counts.
    """
    from .extractor import Extraction

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(results_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # A results.csv written before WP1 has none of the canonicalization
    # columns; add them rather than crash the writer.
    for name in asdict(RowResult(title="")):
        if name not in fieldnames:
            fieldnames.append(name)

    transitions: dict[str, int] = {}
    sources: dict[str, int] = {}
    decisions: dict[str, int] = {}
    stats = {"rows": len(rows), "reclassified": 0, "unchanged_invalid": 0,
             "cpe_mismatch": 0, "canonicalized": 0, "needs_review": 0,
             "transitions": transitions, "lookup_sources": sources,
             "decisions": decisions}
    out_path = output_dir / "results.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows):
            if row.get("valid") != "True" or not row.get("cpe"):
                stats["unchanged_invalid"] += 1
                writer.writerow(row)
                if progress:
                    progress(i + 1, len(rows))
                continue
            ext = Extraction(
                title=row["title"],
                vendor=row.get("vendor") or None,
                product=row.get("product") or None,
                version=row.get("version") or None,
                update=row.get("update") or None,
                target_sw=row.get("target_sw") or None)
            wfn = build_wfn(ext)
            # A previous reclassify may have written a *canonical* CPE,
            # which no longer rebuilds from the stored entities. That is
            # expected and keeps the pass idempotent; only an unexplained
            # mismatch is counted and passed through untouched.
            explained = bool(row.get("canonical_vendor"))
            if wfn is None or (wfn.bind() != row["cpe"] and not explained):
                stats["cpe_mismatch"] += 1
                writer.writerow(row)
                if progress:
                    progress(i + 1, len(rows))
                continue
            vendor = wfn.vendor if isinstance(wfn.vendor, str) else None
            product = wfn.product if isinstance(wfn.product, str) else None
            try:
                lk = lookup_for(nvd, vendor, product, title=row["title"])
            except Exception as exc:
                lk = Lookup([], None, "error")
                row["note"] = f"nvd lookup failed: {exc}"
            match = classify(wfn, lk.candidates, title=row["title"],
                             resolution=lk.resolution, ranges=lk.ranges)
            old_rule = row.get("rule", "")
            if old_rule != match.rule:
                key = f"{old_rule or '(none)'} -> {match.rule}"
                transitions[key] = transitions.get(key, 0) + 1

            out = RowResult(title=row["title"], cpe=row["cpe"])
            apply_match(out, match, wfn, lk)
            if out.cpe != row["cpe"]:
                stats["canonicalized"] += 1
            if out.needs_review:
                stats["needs_review"] += 1
            sources[lk.source] = sources.get(lk.source, 0) + 1
            decisions[out.decision or "(none)"] = \
                decisions.get(out.decision or "(none)", 0) + 1
            row.update({
                "cpe": out.cpe, "rule": out.rule, "rule_name": out.rule_name,
                "match_similarity": str(out.match_similarity),
                "matched_cpe": out.matched_cpe,
                "canonical_vendor": out.canonical_vendor,
                "canonical_product": out.canonical_product,
                "part": out.part, "dice": str(out.dice),
                "margin": str(out.margin), "decision": out.decision,
                "deprecated": str(out.deprecated),
                "lookup_source": out.lookup_source,
                "needs_review": str(out.needs_review),
                "review_reason": out.review_reason,
                "version_source": out.version_source,
            })
            stats["reclassified"] += 1
            writer.writerow(row)
            if progress:
                progress(i + 1, len(rows))
    return stats
