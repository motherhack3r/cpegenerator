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
          f"{len(d.by_vendor)} vendors")
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
                   choices=["anthropic", "openai", "mock", "replay"],
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
