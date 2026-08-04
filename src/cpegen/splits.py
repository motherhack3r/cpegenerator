"""Product-disjoint dataset splits — step 5 of docs/data-curation-plan.md.

The non-negotiable rule: if the curated catalog serves both as the
benchmark gold and as a future train set, the partition must be by
*product*, never by row — versions of the same product on both sides of
a split would leak trivially (the 2023 domain-shift lesson, inverted).

"Product" here is stricter than the ``product`` text column: two rows
belong to the same product family when their alias sets share any
(vendor, product) CPE pair. Families are the connected components of the
row–pair graph (union-find), so vendor aliases (``woocommerce`` /
``automattic``) and product renames (``solr`` / ``apache_solr``) can
never straddle a split.

Assignment is deterministic: components are shuffled with a fixed seed
and dealt greedily to ``benchmark_gold`` then ``test`` until their row
targets are met; the remainder is ``train``. Same inputs + same seed =
byte-identical splits. Everything is recorded in ``MANIFEST.md``:
source hashes, seed, fractions, counts.

Quarantined rows never enter the splits.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Iterable

from .tiering import CONTRAST_FIELDS
from .curate import OUTPUT_FIELDS
from .wfn import split_formatted_string

_ALIAS_SPLIT = re.compile(r"(?<!\\),")

SPLIT_NAMES = ("benchmark_gold", "test", "train")
DEFAULT_FRACTIONS = {"benchmark_gold": 0.10, "test": 0.10, "train": 0.80}
DEFAULT_SEED = 20260804

SPLIT_FIELDS = list(OUTPUT_FIELDS) + list(CONTRAST_FIELDS) + ["tier"]


def _pairs(cpes_cell: str) -> list[tuple[str, str]]:
    pairs = []
    for alias in _ALIAS_SPLIT.split(cpes_cell):
        comps = split_formatted_string(alias)
        if len(comps) == 13:
            pairs.append((comps[3], comps[4]))
    return pairs


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict = {}

    def find(self, x):
        root = x
        while self.parent.setdefault(root, root) != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _read_rows(tier_paths: dict[str, Path]) -> Iterable[dict]:
    for tier, path in tier_paths.items():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["tier"] = tier
                yield row


def split_catalog(tier_a: Path, tier_b: Path, output_dir: Path,
                  seed: int = DEFAULT_SEED,
                  fractions: dict[str, float] | None = None) -> dict:
    """Write product-disjoint splits + MANIFEST.md; return the metrics."""
    fractions = fractions or dict(DEFAULT_FRACTIONS)
    if abs(sum(fractions.values()) - 1.0) > 1e-9:
        raise ValueError(f"fractions must sum to 1, got {fractions}")
    output_dir = Path(output_dir)
    splits_dir = output_dir / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)

    # Pass 1: union products into families through shared rows.
    uf = _UnionFind()
    rows: list[dict] = []
    for row in _read_rows({"A": Path(tier_a), "B": Path(tier_b)}):
        pairs = _pairs(row["cpes"]) or [("__row__", row["key"])]
        row["_family"] = pairs[0]
        for other in pairs[1:]:
            uf.union(pairs[0], other)
        rows.append(row)

    families: dict = {}
    for row in rows:
        root = uf.find(row["_family"])
        families.setdefault(root, []).append(row)

    # Pass 2: deterministic greedy deal, largest targets last (train).
    order = sorted(families.keys())  # stable base order
    random.Random(seed).shuffle(order)
    total = len(rows)
    targets = {name: int(total * fractions[name]) for name in SPLIT_NAMES}
    counts = {name: 0 for name in SPLIT_NAMES}
    assignment: dict = {}
    for root in order:
        size = len(families[root])
        for name in ("benchmark_gold", "test"):
            if counts[name] + size <= targets[name] or (
                    counts[name] == 0 and name != "train"):
                assignment[root] = name
                break
        else:
            assignment[root] = "train"
        counts[assignment[root]] += size

    writers = {}
    files = {}
    try:
        for name in SPLIT_NAMES:
            f = open(splits_dir / f"{name}.csv", "w", newline="",
                     encoding="utf-8")
            files[name] = f
            writers[name] = csv.writer(f)
            writers[name].writerow(SPLIT_FIELDS)
        for root in sorted(families.keys(), key=str):
            name = assignment[root]
            for row in families[root]:
                writers[name].writerow([row.get(f, "") for f in SPLIT_FIELDS])
    finally:
        for f in files.values():
            f.close()

    stats = {
        "seed": seed, "fractions": fractions, "rows": total,
        "families": len(families),
        "counts": counts,
        "sources": {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                    for p in (tier_a, tier_b)},
    }
    (splits_dir / "split_metrics.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    _write_manifest(output_dir, stats)
    return stats


def _write_manifest(output_dir: Path, stats: dict) -> None:
    """MANIFEST.md — comptes, decisions, seed i hash de les fonts (ca)."""
    c = stats["counts"]
    fr = stats["fractions"]
    lines = [
        "# MANIFEST — data/curated/splits/",
        "",
        "Particions **disjuntes per família de producte** (components",
        "connexes dels parells vendor:product dels alias sets — cap",
        "versió d'un mateix producte pot creuar splits). Regenerable amb:",
        "",
        "```",
        f"cpegen split --seed {stats['seed']}",
        "```",
        "",
        f"- Seed: `{stats['seed']}`",
        f"- Files: {stats['rows']} (quarantena exclosa)",
        f"- Famílies de producte: {stats['families']}",
        "",
        "| Split | Files | Fracció objectiu |",
        "|---|---|---|",
    ]
    for name in SPLIT_NAMES:
        lines.append(f"| {name} | {c[name]} | {fr[name]:.0%} |")
    lines += ["", "## Fonts (sha256)", ""]
    for src, digest in stats["sources"].items():
        lines.append(f"- `{src}`: `{digest}`")
    lines += ["", "Mètriques detallades: `splits/split_metrics.json`,",
              "`tier_metrics.json`, `curation_metrics.json`."]
    (output_dir / "MANIFEST.md").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8")
