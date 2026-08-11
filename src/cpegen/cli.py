"""Single CLI entry point for CPEgenerator v2.

Usage:
    python -m cpegen validate "cpe:2.3:a:vendor:product:1.0:*:*:*:*:*:*:*"
    python -m cpegen run --input data/gold/cpes_rasa_vpv_100.csv \
        --output out/ --provider anthropic
    python -m cpegen run --input ... --agent        # escalate non-M1x rows
    python -m cpegen agent --input ...              # agent on every title
    python -m cpegen inventory --output inventory.csv   # local software
    python -m cpegen vulns --input out/run1/results.csv # CVE applicability
    python -m cpegen run --input ... --provider mock --offline   # dry run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import run
from .validator import validate_formatted_string


def cmd_validate(args: argparse.Namespace) -> int:
    exit_code = 0
    for cpe in args.cpe:
        result = validate_formatted_string(cpe)
        if result.ok:
            print(f"VALID    {cpe}")
        else:
            exit_code = 1
            print(f"INVALID  {cpe}")
            for err in result.errors:
                print(f"         - {err}")
    return exit_code


def cmd_run(args: argparse.Namespace) -> int:
    def progress(done: int, total: int) -> None:
        print(f"\r[{done}/{total}] processed", end="", file=sys.stderr, flush=True)

    if getattr(args, "agent_mode", None):
        agent_mode = args.agent_mode
    else:
        agent_mode = "escalate" if getattr(args, "agent", False) else "off"

    rows, report = run(
        input_path=Path(args.input),
        output_dir=Path(args.output),
        provider_name=args.provider,
        model=args.model,
        offline=args.offline,
        limit=args.limit,
        cache_path=Path(args.cache) if args.cache else None,
        agent_mode=agent_mode,
        max_turns=getattr(args, "max_turns", 8),
        dictionary_path=Path(args.dict) if getattr(args, "dict", None) else None,
        resume=getattr(args, "resume", False),
        progress=progress,
    )
    print(file=sys.stderr)
    print(f"Results: {Path(args.output) / 'results.csv'}")
    if report:
        print(f"Report:  {Path(args.output) / 'report.md'}")
        print()
        print(report.to_markdown())
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    from .inventory import collect, write_csv

    items = collect(keep_noise=args.keep_noise)
    out = Path(args.output)
    write_csv(items, out)
    print(f"Inventory: {len(items)} items -> {out}")
    print(f"Next: python -m cpegen run --input {out} --output out/inventory_run")
    return 0


def cmd_curate(args: argparse.Namespace) -> int:
    from .curate import curate_file

    def progress(done: int) -> None:
        print(f"\r[{done}] rows curated", end="", file=sys.stderr, flush=True)

    stats = curate_file(Path(args.input), Path(args.output),
                        limit=args.limit, progress=progress)
    print(file=sys.stderr)
    s = stats.as_dict()
    print(f"Curated {s['rows_kept']}/{s['rows_read']} rows -> "
          f"{Path(args.output) / 'catalog_parsed.csv'}")
    print(f"Aliases: {s['aliases_valid']} valid "
          f"({s['aliases_normalized']} salvaged by WFN normalization), "
          f"{s['aliases_dropped']} dropped (ABNF), "
          f"{s['aliases_deduped']} deduped")
    print(f"Rejected rows: {s['rows_rejected_no_cpe']} no CPE, "
          f"{s['rows_rejected_all_aliases_invalid']} all aliases invalid, "
          f"{s['keys_duplicated']} duplicate keys, "
          f"{s['rows_malformed']} malformed "
          f"-> {Path(args.output) / 'rejects.log'}")
    return 0


def cmd_dict(args: argparse.Namespace) -> int:
    from .dictionary import DEFAULT_SNAPSHOT, LocalDictionary, build_snapshot

    path = Path(args.snapshot or DEFAULT_SNAPSHOT)
    if args.build:
        def progress(done: int, total: int) -> None:
            print(f"\r[{done}/{total}] dictionary entries", end="",
                  file=sys.stderr, flush=True)

        source = "neo4j" if args.from_neo4j else "nvd"
        meta = build_snapshot(path, source=source, progress=progress)
        print(file=sys.stderr)
        print(f"Snapshot ({source}): {meta['fetched']} entries "
              f"({meta['invalid']} failed ABNF, kept+counted) -> {path}")
        return 0
    if not path.exists():
        print(f"No snapshot at {path}. Build one with: "
              f"cpegen dict --build   (needs network; NVD_API_KEY "
              f"recommended: ~3 min vs ~30 min)")
        return 1
    d = LocalDictionary.load(path)
    print(f"Snapshot {path}: {d.size} entries, "
          f"{len(d.by_pair)} vendor:product pairs, "
          f"{len(d.vendor_reps)} vendors, {len(d.product_reps)} products")
    return 0


def cmd_tier(args: argparse.Namespace) -> int:
    from .tiering import tier_file

    def progress(done: int) -> None:
        print(f"\r[{done}] rows tiered", end="", file=sys.stderr, flush=True)

    stats = tier_file(Path(args.input), Path(args.output),
                      dictionary_path=Path(args.dict) if args.dict else None,
                      progress=progress)
    print(file=sys.stderr)
    print(f"Tier A: {stats['tier_a']}  Tier B: {stats['tier_b']} "
          f"(of which human-created: {stats['tier_b_human_created']})  "
          f"Quarantine: {stats['quarantine']}")
    if stats["dictionary"]:
        print(f"Contrast vs {stats['dictionary_size']} dictionary entries: "
              f"{stats['aliases_in_dict']}/{stats['aliases_contrasted']} "
              f"aliases exact in dict ({stats['aliases_deprecated']} "
              f"deprecated), {stats['aliases_pair_known']} pairs known")
    print(f"-> {Path(args.output)}/catalog_tier_[ab].csv, quarantine.csv, "
          f"tier_metrics.json")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    from .splits import DEFAULT_FRACTIONS, split_catalog

    fractions = None
    if args.fractions:
        parts = [float(x) for x in args.fractions.split(",")]
        if len(parts) != 3:
            print("--fractions needs three comma-separated values "
                  "(benchmark_gold,test,train)")
            return 1
        fractions = dict(zip(("benchmark_gold", "test", "train"), parts))
    stats = split_catalog(Path(args.tier_a), Path(args.tier_b),
                          Path(args.output), seed=args.seed,
                          fractions=fractions)
    c = stats["counts"]
    print(f"Splits (seed {stats['seed']}, {stats['families']} product "
          f"families over {stats['rows']} rows):")
    for name, n in c.items():
        print(f"  {name}: {n}")
    print(f"-> {Path(args.output) / 'splits'}/, MANIFEST.md")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    import json as _json
    import os

    from .benchmark import run_benchmark

    if args.no_reasoning:
        extra = _json.loads(os.environ.get("CPEGEN_OPENAI_EXTRA") or "{}")
        extra.setdefault("reasoning", "off")
        os.environ["CPEGEN_OPENAI_EXTRA"] = _json.dumps(extra)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    summaries = run_benchmark(
        input_path=Path(args.input), output_dir=Path(args.output),
        models=models, modes=modes, provider_name=args.provider,
        dictionary_path=Path(args.dict) if args.dict else None,
        offline=args.offline, limit=args.limit,
        cache_path=Path(args.cache) if args.cache else None,
        log=lambda msg: print(msg, file=sys.stderr))
    print(f"{len(summaries)} combos -> "
          f"{Path(args.output) / 'bench_report.md'}")
    for s in summaries:
        print(f"  {s['model']} [{s['mode']}]: "
              f"product F1 strict {s.get('product_f1_strict', 0):.3f}, "
              f"p50 {s['latency_ms_p50']} ms")
    return 0


def cmd_titles(args: argparse.Namespace) -> int:
    from .titles import extract_titles

    def progress(done: int) -> None:
        print(f"\r[{done}] rows scanned", end="", file=sys.stderr, flush=True)

    stats = extract_titles(
        Path(args.input), Path(args.output),
        cols=[c.strip() for c in args.cols.split(",") if c.strip()],
        version_col=args.version_col, sep=args.sep,
        keep_noise=args.keep_noise, progress=progress)
    print(file=sys.stderr)
    print(f"Titles: {stats['written']} written from {stats['rows_read']} "
          f"rows ({stats['duplicates']} duplicates, {stats['noise']} noise, "
          f"{stats['garbage']} garbage, {stats['too_short']} too short) "
          f"-> {args.output}")
    return 0


def cmd_escalate(args: argparse.Namespace) -> int:
    from .cascade import escalate_results

    def progress(done: int, total: int) -> None:
        print(f"\r[{done}/{total}] escalated", end="", file=sys.stderr,
              flush=True)

    stats = escalate_results(
        fast_results=Path(args.input), output_dir=Path(args.output),
        model=args.model, provider_name=args.provider,
        offline=args.offline,
        cache_path=Path(args.cache) if args.cache else None,
        dictionary_path=Path(args.dict) if args.dict else None,
        limit=args.limit, progress=progress)
    print(file=sys.stderr)
    print(f"Cascade: {stats['tail']}/{stats['rows']} rows in the tail, "
          f"{stats['escalated_done']} escalated; M1x "
          f"{stats['m1x_before']} -> {stats['m1x_after']}")
    for t, n in list(stats["transitions"].items())[:8]:
        print(f"  {n:6d}  {t}")
    print(f"-> {Path(args.output) / 'results_merged.csv'}")
    return 0


def cmd_reclassify(args: argparse.Namespace) -> int:
    from .dictionary import HybridDictionary, LocalDictionary
    from .nvd import NVDClient
    from .pipeline import reclassify_results

    def progress(done: int, total: int) -> None:
        print(f"\r[{done}/{total}] reclassified", end="", file=sys.stderr,
              flush=True)

    nvd = NVDClient(Path(args.cache) if args.cache
                    else Path("data/cache/nvd_cache.json"),
                    offline=args.offline)
    lookup = (HybridDictionary(LocalDictionary.load(Path(args.dict)), nvd)
              if args.dict else nvd)
    stats = reclassify_results(Path(args.input), Path(args.output), lookup,
                               progress=progress)
    print(file=sys.stderr)
    print(f"Reclassified {stats['reclassified']}/{stats['rows']} rows "
          f"({stats['unchanged_invalid']} without valid CPE, "
          f"{stats['cpe_mismatch']} rebuild mismatches)")
    for t, n in sorted(stats["transitions"].items(), key=lambda x: -x[1])[:12]:
        print(f"  {n:6d}  {t}")
    print(f"-> {Path(args.output) / 'results.csv'}")
    return 0


def cmd_vulns(args: argparse.Namespace) -> int:
    from .vulns import CVEClient, check_results, write_csv

    def progress(done: int, total: int) -> None:
        print(f"\r[{done}/{total}] checked", end="", file=sys.stderr, flush=True)

    client = CVEClient(cache_path=Path(args.cache) if args.cache else
                       Path("data/cache/cve_cache.json"),
                       offline=args.offline)
    rules = tuple(r.strip().upper() for r in args.rules.split(","))
    vrows = check_results(Path(args.input), client, rules=rules,
                          progress=progress)
    print(file=sys.stderr)
    out = Path(args.output)
    write_csv(vrows, out)
    n_vuln = sum(1 for v in vrows if v.vulnerable)
    n_err = sum(1 for v in vrows if v.error)
    print(f"Checked {len(vrows)} CPEs (rules {','.join(rules)}): "
          f"{n_vuln} vulnerable, {n_err} errors -> {out}")
    return 0


def _add_common_run_args(p: argparse.ArgumentParser, default_output: str) -> None:
    p.add_argument("--input", required=True,
                   help="CSV: title[,rasa_annotation] per row (no header)")
    p.add_argument("--output", default=default_output,
                   help="output directory (results.csv, report.md)")
    p.add_argument("--provider", default=None,
                   choices=["anthropic", "openai", "lmstudio", "mock",
                            "replay"],
                   help="LLM provider (default: CPEGEN_PROVIDER or anthropic)")
    p.add_argument("--model", default=None,
                   help="model override (default: CPEGEN_MODEL or provider "
                        "default); for --provider replay: path to the "
                        "extractions JSON")
    p.add_argument("--offline", action="store_true",
                   help="never hit the NVD API; use only the local cache")
    p.add_argument("--limit", type=int, default=None,
                   help="process only the first N titles")
    p.add_argument("--cache", default=None, help="path to the NVD JSON cache")
    p.add_argument("--max-turns", type=int, default=8, dest="max_turns",
                   help="agent turn budget per title (default 8)")
    p.add_argument("--dict", default=None,
                   help="local CPE dictionary snapshot (see 'cpegen dict "
                        "--build'); NVD API is then only hit on misses")
    p.add_argument("--resume", action="store_true",
                   help="skip titles already present in the output "
                        "results.csv (long runs survive interruptions)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cpegen",
        description="Generate and validate CPE 2.3 names from software titles "
                    "(LLM proposes, deterministic code validates).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate CPE 2.3 formatted strings")
    p_val.add_argument("cpe", nargs="+", help="formatted string(s) to validate")
    p_val.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="run the full pipeline on a titles CSV")
    _add_common_run_args(p_run, default_output="out")
    p_run.add_argument("--agent", action="store_true",
                       help="escalate non-M1x rows to the tool-use agent (Phase 4)")
    p_run.set_defaults(func=cmd_run)

    p_agent = sub.add_parser(
        "agent", help="run the tool-use agent on every title (benchmark arm C)")
    _add_common_run_args(p_agent, default_output="out_agent")
    p_agent.set_defaults(func=cmd_run, agent_mode="all")

    p_inv = sub.add_parser(
        "inventory",
        help="collect the local software inventory (Windows registry / dpkg / rpm)")
    p_inv.add_argument("--output", default="data/inventory/inventory.csv",
                       help="output CSV (title,name,version,vendor,source)")
    p_inv.add_argument("--keep-noise", action="store_true", dest="keep_noise",
                       help="keep KB updates, hotfixes and other inventory noise")
    p_inv.set_defaults(func=cmd_inventory)

    p_cur = sub.add_parser(
        "curate",
        help="parse + ABNF-validate an SCCM products.csv export "
             "(steps 1-2 of docs/data-curation-plan.md)")
    p_cur.add_argument("--input", required=True,
                       help="products.csv export (UTF-8, ';'-separated)")
    p_cur.add_argument("--output", default="data/curated",
                       help="output directory (catalog_parsed.csv, "
                            "rejects.log, curation_metrics.json)")
    p_cur.add_argument("--limit", type=int, default=None,
                       help="keep only the first N curated rows")
    p_cur.set_defaults(func=cmd_curate)

    p_dic = sub.add_parser(
        "dict",
        help="build or inspect the local CPE dictionary snapshot "
             "(full NVD dump; first-pass lookups then skip the API)")
    p_dic.add_argument("--build", action="store_true",
                       help="download the full CPE dictionary (resumable)")
    p_dic.add_argument("--from-neo4j", action="store_true", dest="from_neo4j",
                       help="build from the local KGCS Neo4j (Platform "
                            "nodes) via the HTTP API instead of the NVD "
                            "API; env: NEO4J_URL/NEO4J_USER/NEO4J_PASSWORD"
                            "/NEO4J_DATABASE")
    p_dic.add_argument("--snapshot", default=None,
                       help="snapshot path (default "
                            "data/cache/cpe_dictionary.jsonl.gz)")
    p_dic.set_defaults(func=cmd_dict)

    p_tier = sub.add_parser(
        "tier",
        help="tier the curated catalog (A/B/quarantine) and contrast it "
             "against the local dictionary (steps 3-4 of the curation plan)")
    p_tier.add_argument("--input", default="data/curated/catalog_parsed.csv",
                        help="catalog_parsed.csv from 'cpegen curate'")
    p_tier.add_argument("--output", default="data/curated",
                        help="output directory")
    p_tier.add_argument("--dict", default="data/cache/cpe_dictionary.jsonl.gz",
                        help="local dictionary snapshot; pass '' to skip "
                             "the contrast")
    p_tier.set_defaults(func=cmd_tier)

    p_spl = sub.add_parser(
        "split",
        help="product-disjoint benchmark_gold/test/train splits over the "
             "tiered catalog (step 5 of the curation plan)")
    p_spl.add_argument("--tier-a", default="data/curated/catalog_tier_a.csv",
                       dest="tier_a")
    p_spl.add_argument("--tier-b", default="data/curated/catalog_tier_b.csv",
                       dest="tier_b")
    p_spl.add_argument("--output", default="data/curated",
                       help="output directory (splits/ + MANIFEST.md)")
    p_spl.add_argument("--seed", type=int, default=20260804)
    p_spl.add_argument("--fractions", default=None,
                       help="benchmark_gold,test,train (default 0.1,0.1,0.8)")
    p_spl.set_defaults(func=cmd_split)

    p_ben = sub.add_parser(
        "bench",
        help="Phase-7 benchmark: extraction modes x models over a gold "
             "set (resumable; one directory per combo)")
    p_ben.add_argument("--input", default="data/gold/cpes_rasa_vpv_1k.csv",
                       help="gold CSV (title,annotated_title)")
    p_ben.add_argument("--output", default="out/bench",
                       help="output directory")
    p_ben.add_argument("--models", required=True,
                       help="comma-separated model keys (as served by the "
                            "provider, e.g. LM Studio keys)")
    p_ben.add_argument("--modes", default="single,per-field",
                       help="comma-separated: single, per-field")
    p_ben.add_argument("--provider", default="lmstudio",
                       choices=["anthropic", "openai", "lmstudio", "mock",
                                "replay"])
    p_ben.add_argument("--dict", default="data/cache/cpe_dictionary.jsonl.gz",
                       help="local dictionary snapshot ('' to disable)")
    p_ben.add_argument("--offline", action="store_true",
                       help="never hit the NVD API on dictionary misses")
    p_ben.add_argument("--limit", type=int, default=None,
                       help="only the first N titles (smoke runs)")
    p_ben.add_argument("--cache", default=None,
                       help="path to the NVD JSON cache")
    p_ben.add_argument("--no-reasoning", action="store_true",
                       dest="no_reasoning",
                       help="send {\"reasoning\": \"off\"} to the endpoint "
                            "(LM Studio); models that reject the field "
                            "fall back automatically. Reasoning-on wastes "
                            "~5x latency and can eat the whole max_tokens "
                            "budget thinking (empty content -> row error)")
    p_ben.set_defaults(func=cmd_bench)

    p_tit = sub.add_parser(
        "titles",
        help="extract deduplicated free-text titles from a raw SCCM "
             "export (input prep for the Phase-7 mass run)")
    p_tit.add_argument("--input", required=True, help="raw export CSV")
    p_tit.add_argument("--output", required=True,
                       help="output titles CSV (one per row)")
    p_tit.add_argument("--cols", required=True,
                       help="comma-separated columns composing the title, "
                            "e.g. CompanyName,ProductName,ProductVersion "
                            "or ProductName00")
    p_tit.add_argument("--version-col", default=None, dest="version_col",
                       help="version column, appended only when not "
                            "already inside the composed title")
    p_tit.add_argument("--sep", default=",", help="input delimiter")
    p_tit.add_argument("--keep-noise", action="store_true",
                       dest="keep_noise",
                       help="keep KB/hotfix/language-pack noise")
    p_tit.set_defaults(func=cmd_titles)

    p_esc = sub.add_parser(
        "escalate",
        help="cascade: re-run the non-M1x tail of a results.csv with a "
             "bigger model and merge (decision 2026-08-05)")
    p_esc.add_argument("--input", required=True,
                       help="fast-pass results.csv")
    p_esc.add_argument("--output", required=True, help="output directory")
    p_esc.add_argument("--model", required=True,
                       help="big model key (e.g. qwen3-8b)")
    p_esc.add_argument("--provider", default="lmstudio",
                       choices=["anthropic", "openai", "lmstudio", "mock",
                                "replay"])
    p_esc.add_argument("--dict", default="data/cache/cpe_dictionary.jsonl.gz")
    p_esc.add_argument("--offline", action="store_true")
    p_esc.add_argument("--cache", default=None)
    p_esc.add_argument("--limit", type=int, default=None)
    p_esc.set_defaults(func=cmd_escalate)

    p_rec = sub.add_parser(
        "reclassify",
        help="re-run dictionary lookup + M1-M3 classification over an "
             "existing results.csv without re-extracting (matcher or "
             "dictionary fixes should not cost GPU hours)")
    p_rec.add_argument("--input", required=True,
                       help="results.csv from a previous run")
    p_rec.add_argument("--output", required=True, help="output directory")
    p_rec.add_argument("--dict", default="data/cache/cpe_dictionary.jsonl.gz")
    p_rec.add_argument("--offline", action="store_true")
    p_rec.add_argument("--cache", default=None)
    p_rec.set_defaults(func=cmd_reclassify)

    p_vul = sub.add_parser(
        "vulns",
        help="check pipeline results against CVE vulnerable configurations "
             "(NVD CVE API 2.0)")
    p_vul.add_argument("--input", required=True,
                       help="results.csv produced by 'cpegen run'")
    p_vul.add_argument("--output", default="out/vulns.csv",
                       help="output CSV with CVEs per CPE")
    p_vul.add_argument("--rules", default="M1,M1A",
                       help="comma-separated match rules to check (default M1,M1A)")
    p_vul.add_argument("--offline", action="store_true",
                       help="never hit the NVD API; use only the local cache")
    p_vul.add_argument("--cache", default=None,
                       help="path to the CVE JSON cache")
    p_vul.set_defaults(func=cmd_vulns)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
