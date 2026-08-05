"""Two-model cascade — Phase 7 mass run (decision 2026-08-05).

The inverted-hybrid thesis made literal: a small fast model does the
bulk (``cpegen run``), and this module re-runs only the unresolved tail
(rows that did not reach an M1x rule) with a bigger model, then merges.

Everything is resumable: the escalation reuses the pipeline's streaming
resume, so a killed multi-day run continues where it stopped. The merge
never discards information — the merged CSV keeps every fast-pass
column and adds ``escalated_by`` (empty for rows the fast model already
resolved) plus the fast pass's original rule in ``fast_rule`` when a
row was escalated.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Callable

from .pipeline import run

RESOLVED_RULES = ("M1", "M1A", "M1B", "M1C")


def _is_resolved(row: dict) -> bool:
    return row.get("rule", "") in RESOLVED_RULES


def escalate_results(fast_results: Path, output_dir: Path,
                     model: str, provider_name: str = "lmstudio",
                     offline: bool = False,
                     cache_path: Path | None = None,
                     dictionary_path: Path | None = None,
                     limit: int | None = None,
                     progress: Callable[[int, int], None] | None = None,
                     ) -> dict:
    """Re-run the non-M1x tail of ``fast_results`` with ``model``.

    Writes ``escalate_titles.csv`` (the tail), ``escalated/results.csv``
    (the big model's pass, resumable) and ``results_merged.csv`` (one
    row per original title, escalated rows replacing fast ones).
    Returns the stats dict, including the rule-transition counter.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(fast_results, newline="", encoding="utf-8") as fh:
        fast_rows = list(csv.DictReader(fh))
    if not fast_rows:
        raise ValueError(f"no rows in {fast_results}")

    tail = [r for r in fast_rows if not _is_resolved(r)]
    titles_path = output_dir / "escalate_titles.csv"
    with open(titles_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for r in tail:
            writer.writerow([r["title"]])

    run(input_path=titles_path, output_dir=output_dir / "escalated",
        provider_name=provider_name, model=model, offline=offline,
        limit=limit, cache_path=cache_path,
        dictionary_path=dictionary_path, resume=True, progress=progress)

    escalated: dict[str, dict] = {}
    with open(output_dir / "escalated" / "results.csv", newline="",
              encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            escalated[row["title"]] = row

    transitions: Counter = Counter()
    merged_path = output_dir / "results_merged.csv"
    fieldnames = list(fast_rows[0].keys()) + ["escalated_by"]
    stats = {"rows": len(fast_rows), "tail": len(tail),
             "escalated_done": 0, "m1x_before": 0, "m1x_after": 0}
    with open(merged_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for fast in fast_rows:
            if _is_resolved(fast):
                stats["m1x_before"] += 1
                stats["m1x_after"] += 1
                writer.writerow({**fast, "escalated_by": ""})
                continue
            esc = escalated.get(fast["title"])
            if esc is None:  # tail not (yet) processed: keep the fast row
                writer.writerow({**fast, "escalated_by": ""})
                continue
            stats["escalated_done"] += 1
            transitions[f"{fast.get('rule') or '—'}→{esc.get('rule') or '—'}"] += 1
            if _is_resolved(esc):
                stats["m1x_after"] += 1
            out = {k: esc.get(k, "") for k in fast_rows[0].keys()}
            out["fast_rule"] = fast.get("rule", "")
            out["escalated_by"] = model
            writer.writerow(out)

    stats["transitions"] = dict(transitions.most_common())
    return stats
