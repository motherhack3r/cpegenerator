"""End-to-end pipeline: title -> extraction -> WFN -> validation -> lookup
-> M1-M3 classification, with optional Phase-4 agent escalation.

Invariant (non-negotiable): no CPE leaves this pipeline without passing
the deterministic ABNF validator. If a bound string fails validation the
row is flagged and carries no CPE.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path

from .agent import AgentResult, get_agent_provider, run_agent
from .extractor import Extraction, extract, get_provider
from .matcher import HIGH_CONFIDENCE, classify
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


def process_title(title: str, provider, nvd: NVDClient) -> RowResult:
    """Run the fast single-shot pipeline on one title."""
    row = RowResult(title=title)

    ext = extract(provider, title)
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

    # Dictionary lookup + M1-M3 classification.
    vendor = wfn.vendor if isinstance(wfn.vendor, str) else None
    product = wfn.product if isinstance(wfn.product, str) else None
    try:
        candidates = nvd.candidates_for(vendor, product)
    except Exception as exc:  # degrade to no candidates, keep the run alive
        candidates = []
        row.note = f"nvd lookup failed: {exc}"
    match = classify(wfn, candidates)
    row.rule = match.rule
    row.rule_name = match.rule_name
    row.match_similarity = round(match.similarity, 4)
    row.matched_cpe = match.matched_cpe or ""
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
    toolbox = ToolBox(nvd=nvd)
    agent_provider = (get_agent_provider(provider_name, model=model)
                      if agent_mode in ("escalate", "all") else None)
    provider = get_provider(provider_name, model=model) if agent_mode != "all" else None

    gold = load_gold(input_path)
    if limit:
        gold = gold[:limit]

    rows: list[RowResult] = []
    for i, g in enumerate(gold):
        if agent_mode == "all":
            row = agent_row(run_agent(g.title, agent_provider, toolbox,
                                      max_turns=max_turns))
        else:
            row = process_title(g.title, provider, nvd)
            if agent_mode == "escalate" and needs_escalation(row):
                row = escalate_title(row, agent_provider, toolbox, max_turns)
        rows.append(row)
        if progress:
            progress(i + 1, len(gold))

    # results CSV
    results_path = output_dir / "results.csv"
    with open(results_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    report = None
    has_annotations = any(g.vendor or g.product for g in gold)
    if has_annotations:
        report = evaluate(rows, gold)
        (output_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    return rows, report
