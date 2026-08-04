"""Phase-7 benchmark harness: extraction modes x models over a gold set.

Runs the fast pipeline once per (model, mode) combo — mode ``single``
(one JSON call per title) vs ``per-field`` (one minimal call per
entity) — and aggregates, per combo: MUC/SemEval strict & partial F1
per field, full-CPE validity/exactness, M1-M3 distribution, latency
percentiles and token usage. Output: one directory per combo (the usual
``results.csv`` + ``report.md``) plus ``bench_summary.csv`` and
``bench_report.md`` with the comparison table.

Resumable by design: a combo whose ``summary.json`` already exists is
skipped and its saved summary reused — a crashed overnight matrix
continues where it stopped. Model load into LM Studio happens
just-in-time on the first request of each combo (that first title's
latency is the load cost; the report uses the median, not the mean,
for exactly this reason).
"""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Callable

from .metrics import ENTITIES
from .pipeline import run

MODES = ("single", "per-field")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", name.lower()).strip("_")


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return values[idx]


def _summarize(model: str, mode: str, rows, report, wall_s: float) -> dict:
    lat = [r.latency_ms for r in rows]
    high = sum(1 for r in rows if r.rule in ("M1", "M1A", "M1B", "M1C"))
    summary = {
        "model": model, "mode": mode, "n": len(rows),
        "extraction_errors": report.extraction_errors if report else 0,
        "cpe_valid": report.cpe_valid if report else 0,
        "cpe_exact": report.cpe_exact if report else 0,
        "m1x": high,
        "latency_ms_p50": _percentile(lat, 0.50),
        "latency_ms_p95": _percentile(lat, 0.95),
        "tokens_in": sum(r.tokens_in for r in rows),
        "tokens_out": sum(r.tokens_out for r in rows),
        "wall_s": round(wall_s, 1),
    }
    for ent in ENTITIES:
        c = report.entity_counts[ent] if report else None
        summary[f"{ent}_f1_strict"] = round(c.strict_f1, 4) if c else 0.0
        summary[f"{ent}_f1_partial"] = round(c.partial_f1, 4) if c else 0.0
    return summary


def run_benchmark(input_path: Path, output_dir: Path, models: list[str],
                  modes: list[str] | None = None,
                  provider_name: str = "openai",
                  dictionary_path: Path | None = None,
                  offline: bool = False, limit: int | None = None,
                  cache_path: Path | None = None,
                  log: Callable[[str], None] | None = None) -> list[dict]:
    """Run the full matrix; returns one summary dict per combo."""
    modes = list(modes or MODES)
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        raise ValueError(f"unknown modes {unknown}; choose from {MODES}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log = log or (lambda msg: None)

    summaries: list[dict] = []
    for model in models:
        for mode in modes:
            combo_dir = output_dir / f"{_slug(model)}__{_slug(mode)}"
            marker = combo_dir / "summary.json"
            if marker.exists():
                summaries.append(json.loads(marker.read_text(
                    encoding="utf-8")))
                log(f"skip {model} [{mode}]: summary.json exists")
                continue
            log(f"run  {model} [{mode}] -> {combo_dir}")
            t0 = time.monotonic()
            rows, report = run(
                input_path=Path(input_path), output_dir=combo_dir,
                provider_name=provider_name, model=model,
                offline=offline, limit=limit, cache_path=cache_path,
                dictionary_path=dictionary_path, extract_mode=mode)
            summary = _summarize(model, mode, rows, report,
                                 time.monotonic() - t0)
            marker.write_text(json.dumps(summary, indent=2) + "\n",
                              encoding="utf-8")
            summaries.append(summary)

    _write_outputs(output_dir, summaries)
    return summaries


SUMMARY_COLUMNS = (
    ["model", "mode", "n", "extraction_errors"]
    + [f"{e}_f1_strict" for e in ENTITIES]
    + [f"{e}_f1_partial" for e in ENTITIES]
    + ["cpe_valid", "cpe_exact", "m1x",
       "latency_ms_p50", "latency_ms_p95", "tokens_in", "tokens_out",
       "wall_s"])


def _write_outputs(output_dir: Path, summaries: list[dict]) -> None:
    with open(output_dir / "bench_summary.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        w.writerows({k: s.get(k, "") for k in SUMMARY_COLUMNS}
                    for s in summaries)

    lines = ["# Benchmark Fase 7 — modes d'extracció × models", ""]
    if summaries:
        n = summaries[0]["n"]
        lines += [f"Títols per combinació: **{n}**. Latència en ms per "
                  "títol (p50/p95; la primera petició paga la càrrega "
                  "JIT del model). F1 a nivell d'entitat MUC/SemEval'13 "
                  "(`docs/evaluation.md`).", ""]
    lines += ["| Model | Mode | F1s vendor | F1s product | F1s version "
              "| F1p v/p/v | CPE vàlid | CPE exacte | M1x | p50 ms "
              "| p95 ms | tok in/out |",
              "|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|"]
    ranked = sorted(summaries,
                    key=lambda s: (s.get("product_f1_strict", 0),
                                   s.get("vendor_f1_strict", 0)),
                    reverse=True)
    for s in ranked:
        f1p = "/".join(f"{s.get(f'{e}_f1_partial', 0):.2f}"
                       for e in ("vendor", "product", "version"))
        lines.append(
            f"| {s['model']} | {s['mode']} "
            f"| {s.get('vendor_f1_strict', 0):.3f} "
            f"| {s.get('product_f1_strict', 0):.3f} "
            f"| {s.get('version_f1_strict', 0):.3f} "
            f"| {f1p} "
            f"| {s['cpe_valid']}/{s['n']} | {s['cpe_exact']}/{s['n']} "
            f"| {s['m1x']} | {s['latency_ms_p50']} | {s['latency_ms_p95']} "
            f"| {s['tokens_in']}/{s['tokens_out']} |")
    lines += ["", "Detall per combinació: `<model>__<mode>/results.csv` "
              "i `report.md`. Ordenat per F1 strict de product."]
    (output_dir / "bench_report.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")
