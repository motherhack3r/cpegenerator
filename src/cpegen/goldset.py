"""Gold-set loading: RASA-style annotated titles.

Format (data/gold/*.csv, no header):
    title,annotated_title
    in2code femanager 5.5.1 for typo3,[in2code](cpe_vendor) [femanager](cpe_product) [5.5.1](cpe_version) for typo3

Also accepts the output of `cpegen inventory` (header row + title-first
columns without annotations); such rows simply carry no gold entities.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

_ENTITY_RE = re.compile(r"\[([^\]]+)\]\((cpe_vendor|cpe_product|cpe_version)\)")
_TARGET_RE = re.compile(r"\bfor ([a-z0-9._+-]+)\s*$")


@dataclass
class GoldRecord:
    """One annotated title with its ground-truth entities."""

    title: str
    vendor: str | None
    product: str | None
    version: str | None
    target_sw: str | None  # deduced deterministically from the title tail


def parse_annotation(title: str, annotated: str) -> GoldRecord:
    entities: dict[str, str] = {}
    for value, label in _ENTITY_RE.findall(annotated):
        key = label.removeprefix("cpe_")
        # keep the first occurrence per entity type
        entities.setdefault(key, value.strip().lower())
    target = None
    m = _TARGET_RE.search(title.strip().lower())
    if m:
        target = m.group(1)
    return GoldRecord(
        title=title,
        vendor=entities.get("vendor"),
        product=entities.get("product"),
        version=entities.get("version"),
        target_sw=target,
    )


def load_gold(path: Path | str) -> list[GoldRecord]:
    records = []
    with open(path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if not row or not row[0].strip():
                continue
            if i == 0 and row[0].strip().lower() == "title":
                continue  # header row from `cpegen inventory` output
            annotated = row[1] if len(row) > 1 else ""
            records.append(parse_annotation(row[0], annotated))
    return records
