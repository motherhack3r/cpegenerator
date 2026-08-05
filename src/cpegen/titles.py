"""RAW title preparation — Phase 7 step 4 input (docs/data-curation-plan.md).

Turns a raw SCCM export into the one-title-per-row CSV that
``cpegen run`` consumes: compose the title from one or more columns
(``CompanyName ProductName ProductVersion`` on ``v_SoftwareProduct``,
``ProductName00`` [+ version] on the installed-software summary), drop
garbage placeholders (``-``, ``---``), deduplicate case-insensitively
and filter inventory noise (KB updates, hotfixes, language packs —
the same patterns as ``cpegen inventory``).

Deterministic and streaming: same input, same flags -> byte-identical
output, whatever its size.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable

from .inventory import NOISE_PATTERNS

GARBAGE_VALUES = {"", "-", "--", "---", "n/a", "null", "unknown"}


def _clean(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value.lower() in GARBAGE_VALUES else value


def compose_title(row: dict, cols: list[str],
                  version_col: str | None = None) -> str:
    """Join the selected columns into one free-text title.

    The version column is appended only when its value is not already
    contained in the composed text (display names often embed it).
    """
    parts = [v for c in cols if (v := _clean(row.get(c)))]
    title = " ".join(parts)
    if not title:
        return ""  # a bare version is not a title (v_SoftwareProduct
        # is full of '-,-,"2, 6, 700, 0"' rows)
    if version_col:
        version = _clean(row.get(version_col))
        if version and version.lower() not in title.lower():
            title = f"{title} {version}"
    return " ".join(title.split())  # collapse internal whitespace


def _is_noise(title: str) -> bool:
    return any(p.search(title) for p in NOISE_PATTERNS)


def extract_titles(input_path: Path, output_path: Path, cols: list[str],
                   version_col: str | None = None, sep: str = ",",
                   keep_noise: bool = False, min_length: int = 3,
                   progress: Callable[[int], None] | None = None) -> dict:
    """Write the deduplicated titles CSV; return the counters."""
    stats = {"rows_read": 0, "garbage": 0, "too_short": 0, "noise": 0,
             "duplicates": 0, "written": 0}
    seen: set[str] = set()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig: the SCCM exports carry a BOM.
    with open(input_path, encoding="utf-8-sig", newline="") as fin, \
            open(output_path, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin, delimiter=sep)
        missing = [c for c in cols + ([version_col] if version_col else [])
                   if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"input is missing columns {missing}; found "
                f"{reader.fieldnames}")
        writer = csv.writer(fout)
        for row in reader:
            stats["rows_read"] += 1
            if progress and stats["rows_read"] % 50000 == 0:
                progress(stats["rows_read"])
            title = compose_title(row, cols, version_col)
            if not title:
                stats["garbage"] += 1
                continue
            if len(title) < min_length:
                stats["too_short"] += 1
                continue
            if not keep_noise and _is_noise(title):
                stats["noise"] += 1
                continue
            key = title.lower()
            if key in seen:
                stats["duplicates"] += 1
                continue
            seen.add(key)
            stats["written"] += 1
            writer.writerow([title])

    metrics_path = output_path.with_suffix(output_path.suffix + ".metrics.json")
    metrics_path.write_text(json.dumps(
        {"source": str(input_path), "cols": cols, "version_col": version_col,
         "keep_noise": keep_noise, "stats": stats}, indent=2) + "\n",
        encoding="utf-8")
    return stats
