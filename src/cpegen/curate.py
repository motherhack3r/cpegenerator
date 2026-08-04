"""SCCM catalog curation — steps 1-2 of docs/data-curation-plan.md.

Turns the raw ``products.csv`` export (487k rows, UTF-8, ``;``-separated,
CRLF) into a parsed and syntactically validated catalog:

- step 1 (parse + normalization): drop Excel-corrupted fields
  (``Updated By``), explode the multi-valued ``CPE`` cell into an alias
  set, use ``Vuln DB ID`` as the primary key (deriving a stable surrogate
  when it is missing), keep the revision-trail fields needed by the
  tiering step (``Override *``, ``Created By``);
- step 2 (syntactic validation): every alias must pass the deterministic
  ABNF validator (:mod:`cpegen.validator`). An alias that fails is first
  put through the canonical WFN normalization (NISTIR 7695 binding:
  lowercase, whitespace to ``_``, special characters escaped) and
  revalidated — the export contains tool-generated CPEs with uppercase
  versions, unescaped parentheses and embedded spaces, which are
  un-normalized values, not garbage (decision 2026-08-04). Every
  normalization is logged to ``normalized.log`` with the original alias.
  Aliases that still fail are dropped and logged; a row whose whole alias
  set fails is rejected. Nothing is discarded silently: every rejection
  lands in ``rejects.log`` with a machine-readable reason.

Tiering, NVD contrast and splits (steps 3-5) build on the output of this
module and are intentionally out of scope here.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, TextIO

from .validator import validate_formatted_string
from .wfn import bind_component, normalize_raw, split_formatted_string

# Columns consumed from the export. ``Updated By`` is deliberately absent:
# Excel degraded it to scientific notation (see data-curation-plan.md).
REQUIRED_COLUMNS = (
    "CPE",
    "Edition",
    "Title",
    "Product",
    "Product Version",
    "Vendor",
    "Vuln DB ID",
    "Created By",
)

# Aliases are comma-separated, but a comma inside a CPE component is
# escaped as ``\,`` — split only on unescaped commas.
_ALIAS_SPLIT = re.compile(r"(?<!\\),")


@dataclass
class CatalogRow:
    """One parsed-and-validated catalog entry (steps 1-2 output)."""

    key: str                       # Vuln DB ID, or derived surrogate
    key_source: str                # "vulndb" | "derived"
    title: str
    product: str
    version: str
    vendor: str
    edition: str
    cpes: list[str]                # validated alias set, source order kept
    created_by: str                # "" when the export left it empty
    has_override: bool             # any "Override *" column non-empty
    dropped_aliases: list[str] = field(default_factory=list)
    n_normalized: int = 0          # aliases salvaged by canonicalization


@dataclass
class Reject:
    """One rejection, auditable in rejects.log."""

    step: str        # "parse" | "validate"
    reason: str      # machine-readable, e.g. "no_cpe", "abnf:<first error>"
    key: str         # row key when known, "" otherwise
    line: int        # 1-based physical line of the source row
    detail: str      # the offending value (alias or title)


@dataclass
class CurationStats:
    """Counters for the MANIFEST and the run summary."""

    rows_read: int = 0
    rows_kept: int = 0
    rows_rejected_no_cpe: int = 0
    rows_rejected_all_aliases_invalid: int = 0
    rows_malformed: int = 0
    aliases_seen: int = 0
    aliases_valid: int = 0
    aliases_normalized: int = 0
    aliases_dropped: int = 0
    aliases_deduped: int = 0
    keys_derived: int = 0
    keys_duplicated: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(vars(self))


def split_aliases(cell: str) -> list[str]:
    """Explode the multi-valued CPE cell into a deduplicated alias list."""
    out: list[str] = []
    for raw in _ALIAS_SPLIT.split(cell):
        alias = raw.strip()
        if alias and alias not in out:
            out.append(alias)
    return out


def _unescape_permissive(comp: str) -> str:
    """Drop backslashes, keeping the escaped characters as literals."""
    out: list[str] = []
    i = 0
    while i < len(comp):
        if comp[i] == "\\" and i + 1 < len(comp):
            out.append(comp[i + 1])
            i += 2
        else:
            out.append(comp[i])
            i += 1
    return "".join(out)


def canonicalize_alias(alias: str) -> str | None:
    """Rebind a near-miss alias to its canonical WFN formatted string.

    Deterministic salvage for tool-generated CPEs that fail the grammar
    only because their values are un-normalized (uppercase, unescaped
    specials, embedded whitespace). Returns ``None`` when the alias does
    not even have the ``cpe:2.3:`` shape with 11 components — those are
    beyond salvage. The caller must still revalidate the result.
    """
    comps = split_formatted_string(alias.strip())
    if len(comps) != 13 or comps[0].lower() != "cpe" or comps[1] != "2.3":
        return None
    values: list[str] = []
    for comp in comps[2:]:
        if comp in ("*", "-"):
            values.append(comp)
            continue
        raw = normalize_raw(_unescape_permissive(comp))
        if not raw:
            return None
        values.append(bind_component(raw))
    return "cpe:2.3:" + ":".join(values)


def _derived_key(title: str, cpe_cell: str) -> str:
    """Stable surrogate key for rows missing ``Vuln DB ID``."""
    payload = f"{title}\x1f{cpe_cell}".encode("utf-8")
    return "d_" + hashlib.sha1(payload).hexdigest()[:32]


def curate_rows(
    reader: Iterator[list[str]],
    header: list[str],
    on_reject: Callable[[Reject], None],
    stats: CurationStats,
    on_normalize: Callable[[str, str, str, int], None] | None = None,
) -> Iterator[CatalogRow]:
    """Run steps 1-2 over raw csv rows, yielding validated catalog rows."""
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"input is missing expected columns: {missing}")
    idx = {c: header.index(c) for c in REQUIRED_COLUMNS}
    override_idx = [i for i, c in enumerate(header) if c.startswith("Override")]
    seen_keys: set[str] = set()

    for line, row in enumerate(reader, start=2):  # line 1 is the header
        stats.rows_read += 1
        if len(row) != len(header):
            stats.rows_malformed += 1
            on_reject(Reject("parse", "malformed_row", "", line,
                             f"{len(row)} fields, expected {len(header)}"))
            continue

        cpe_cell = row[idx["CPE"]].strip()
        title = row[idx["Title"]].strip()
        vulndb = row[idx["Vuln DB ID"]].strip()
        if vulndb:
            key, key_source = vulndb, "vulndb"
        else:
            key, key_source = _derived_key(title, cpe_cell), "derived"
            stats.keys_derived += 1
        if key in seen_keys:
            stats.keys_duplicated += 1
            on_reject(Reject("parse", "duplicate_key", key, line, title))
            continue

        if not cpe_cell:
            stats.rows_rejected_no_cpe += 1
            on_reject(Reject("parse", "no_cpe", key, line, title))
            continue

        aliases = split_aliases(cpe_cell)
        raw_count = len(_ALIAS_SPLIT.split(cpe_cell))
        stats.aliases_deduped += raw_count - len(aliases)
        stats.aliases_seen += len(aliases)

        valid: list[str] = []
        dropped: list[str] = []
        n_normalized = 0
        for alias in aliases:
            result = validate_formatted_string(alias)
            if result.ok:
                if alias not in valid:
                    valid.append(alias)
                    stats.aliases_valid += 1
                continue
            canonical = canonicalize_alias(alias)
            if canonical is not None and validate_formatted_string(canonical).ok:
                stats.aliases_normalized += 1
                n_normalized += 1
                if on_normalize:
                    on_normalize(alias, canonical, key, line)
                if canonical not in valid:
                    valid.append(canonical)
                    stats.aliases_valid += 1
                continue
            dropped.append(alias)
            stats.aliases_dropped += 1
            on_reject(Reject("validate", f"abnf:{result.errors[0]}",
                             key, line, alias))

        if not valid:
            stats.rows_rejected_all_aliases_invalid += 1
            on_reject(Reject("validate", "all_aliases_invalid", key, line,
                             cpe_cell))
            continue

        seen_keys.add(key)
        stats.rows_kept += 1
        yield CatalogRow(
            key=key,
            key_source=key_source,
            title=title,
            product=row[idx["Product"]].strip(),
            version=row[idx["Product Version"]].strip(),
            vendor=row[idx["Vendor"]].strip(),
            edition=row[idx["Edition"]].strip(),
            cpes=valid,
            created_by=row[idx["Created By"]].strip(),
            has_override=any(row[i].strip() for i in override_idx),
            dropped_aliases=dropped,
            n_normalized=n_normalized,
        )


OUTPUT_FIELDS = (
    "key", "key_source", "title", "product", "version", "vendor",
    "edition", "n_aliases", "cpes", "created_by", "has_override",
    "n_normalized_aliases", "n_dropped_aliases",
)


def write_catalog_row(writer: csv.writer, r: CatalogRow) -> None:
    writer.writerow([
        r.key, r.key_source, r.title, r.product, r.version, r.vendor,
        r.edition, len(r.cpes), ",".join(r.cpes), r.created_by,
        int(r.has_override), r.n_normalized, len(r.dropped_aliases),
    ])


def _write_reject(log: TextIO, rej: Reject) -> None:
    log.write(json.dumps(vars(rej), ensure_ascii=False) + "\n")


def curate_file(
    input_path: Path,
    output_dir: Path,
    limit: int | None = None,
    progress: Callable[[int], None] | None = None,
) -> CurationStats:
    """Curate ``products.csv`` into ``catalog_parsed.csv`` + ``rejects.log``.

    Also drops ``curation_metrics.json`` with the counters, so the run is
    auditable and the future MANIFEST can cite exact numbers.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "catalog_parsed.csv"
    rejects_path = output_dir / "rejects.log"
    normalized_path = output_dir / "normalized.log"
    metrics_path = output_dir / "curation_metrics.json"
    stats = CurationStats()

    with open(input_path, encoding="utf-8", newline="") as fin, \
            open(catalog_path, "w", encoding="utf-8", newline="") as fcat, \
            open(rejects_path, "w", encoding="utf-8") as flog, \
            open(normalized_path, "w", encoding="utf-8") as fnorm:
        reader = csv.reader(fin, delimiter=";")
        header = next(reader)
        writer = csv.writer(fcat)
        writer.writerow(OUTPUT_FIELDS)

        def on_normalize(original: str, canonical: str, key: str,
                         line: int) -> None:
            fnorm.write(json.dumps(
                {"key": key, "line": line, "original": original,
                 "canonical": canonical}, ensure_ascii=False) + "\n")

        rows = curate_rows(reader, header,
                           lambda rej: _write_reject(flog, rej), stats,
                           on_normalize=on_normalize)
        for n, row in enumerate(rows, start=1):
            write_catalog_row(writer, row)
            if progress and n % 20000 == 0:
                progress(n)
            if limit is not None and n >= limit:
                break

    source = hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
    metrics_path.write_text(json.dumps(
        {"source": str(input_path), "source_sha256": source,
         "stats": stats.as_dict()}, indent=2) + "\n", encoding="utf-8")
    return stats
