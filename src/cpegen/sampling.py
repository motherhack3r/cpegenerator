"""WP3 — stratified sampling and pre-annotation queues (Fase 9.3, spec #5).

Builds the two annotation-ready queues (``gold-rawTFM``, ``gold-rawPC``)
from titles already on disk — no run of the RAW is needed, only the
:mod:`cpegen.title_features` signals over the prepared title list
(``cpegen titles``/``cpegen inventory`` output).

Two stages, deliberately separated by cost:

1. :func:`sample_stratified` — ~70 random + ~30 hard titles out of the
   whole population, using only :func:`cpegen.title_features.is_hard`
   (no dictionary, no GPU): cheap enough to run over 90k+ titles.
2. :func:`build_queue_rows` — for the ~100 SAMPLED titles only, the full
   :func:`cpegen.title_features.features` signals plus a pre-annotation
   suggestion from the dictionary's clean+Dice lookup
   (:meth:`cpegen.dictionary.LocalDictionary.resolve`) — deterministic
   code, never an LLM call, offering Humbert a starting point he
   confirms or corrects, never a silent answer.

The queue is a CSV Humbert edits directly: ``annotated_title`` follows
the same RASA-bracket format :mod:`cpegen.goldset` already parses
(``[vendor](cpe_vendor) [product](cpe_product) [version](cpe_version)``)
so a frozen queue becomes a gold CSV with no format conversion — the
``suggested_*``/``dice``/``margin``/``decision`` columns are hints only,
deliberately left OUT of ``annotated_title`` (canonical dictionary
spelling rarely matches the raw title's own substring, so auto-filling
brackets around it would plant wrong "ground truth" instead of speeding
up the human).
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .title_features import features, is_hard

QUEUE_FIELDS = (
    "title", "origin", "stratum",
    "has_parens", "has_arch_locale_tokens", "vendor_in_alias_table",
    "versioned_family", "length", "n_numeric_tokens", "direct_dice_ge_085",
    "suggested_vendor", "suggested_product", "suggested_part",
    "dice", "margin", "decision", "review_reason", "runner_up",
    # blank for Humbert; annotated_title follows the goldset RASA format.
    "annotated_title", "verdict", "annotator", "timestamp", "notes",
)


@dataclass
class SampleResult:
    """One stratified draw over a title population."""

    random_titles: list[str] = field(default_factory=list)
    hard_titles: list[str] = field(default_factory=list)
    population: int = 0
    hard_population: int = 0
    seed: int = 0

    @property
    def titles(self) -> list[str]:
        """Random first, then hard — the order the queue CSV is written in."""
        return self.random_titles + self.hard_titles


def read_titles(path: Path | str) -> list[str]:
    """Read a one-title-per-row or inventory-style CSV into a title list.

    Accepts both shapes already in the repo: the header-less single
    column ``cpegen titles`` writes, and the ``title,name,version,
    vendor,source`` header ``cpegen inventory`` writes (same convention
    :func:`cpegen.goldset.load_gold` uses).
    """
    titles: list[str] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if not row or not row[0].strip():
                continue
            if i == 0 and row[0].strip().lower() == "title":
                continue  # header row (cpegen inventory)
            titles.append(row[0].strip())
    return titles


def sample_stratified(titles: Iterable[str], seed: int,
                      n_random: int = 70, n_hard: int = 30) -> SampleResult:
    """~``n_random`` random + ~``n_hard`` hard titles, deterministic.

    Deduplicated (case-sensitive; upstream dedup is already
    case-insensitive) and order-independent of the input's own order —
    only ``seed`` controls the draw. The hard and random pools are
    disjoint (a hard title drawn first is removed from the random pool)
    so the two strata never double-count the same row. When the
    population is smaller than the nominal target (a small ``rawPC``
    inventory, say), the draw is simply capped at what exists — reported
    via :attr:`SampleResult.population`/``hard_population``, never
    padded or silently short without a way to tell.
    """
    ordered = list(dict.fromkeys(t for t in titles if t and t.strip()))
    hard_pool = [t for t in ordered if is_hard(t)]
    rng = random.Random(seed)

    shuffled_hard = list(hard_pool)
    rng.shuffle(shuffled_hard)
    hard_sample = shuffled_hard[:n_hard]

    hard_set = set(hard_sample)
    remaining = [t for t in ordered if t not in hard_set]
    rng.shuffle(remaining)
    random_sample = remaining[:n_random]

    return SampleResult(random_titles=random_sample, hard_titles=hard_sample,
                        population=len(ordered), hard_population=len(hard_pool),
                        seed=seed)


def _suggestion_row(title: str, origin: str, stratum: str, dictionary) -> dict:
    feats = features(title, dictionary=dictionary)
    row = {
        "title": title, "origin": origin, "stratum": stratum,
        "has_parens": feats["has_parens"],
        "has_arch_locale_tokens": feats["has_arch_locale_tokens"],
        "vendor_in_alias_table": feats["vendor_in_alias_table"],
        "versioned_family": feats["versioned_family"],
        "length": feats["length"],
        "n_numeric_tokens": feats["n_numeric_tokens"],
        "direct_dice_ge_085": feats["direct_dice_ge_085"],
        "suggested_vendor": "", "suggested_product": "", "suggested_part": "",
        "dice": "", "margin": "", "decision": "", "review_reason": "",
        "runner_up": "",
        "annotated_title": "", "verdict": "", "annotator": "",
        "timestamp": "", "notes": "",
    }
    if dictionary is None:
        return row
    resolution = dictionary.resolve(title, title=title)
    if resolution.winner is not None:
        w = resolution.winner
        row["suggested_vendor"] = w.vendor
        row["suggested_product"] = w.product
        row["suggested_part"] = w.part
        row["dice"] = round(resolution.score, 4)
        row["margin"] = round(resolution.margin, 4)
        row["decision"] = resolution.decision
        row["review_reason"] = resolution.reason
    if resolution.runner_up is not None:
        ru = resolution.runner_up
        row["runner_up"] = f"{ru.vendor}:{ru.product} ({ru.score:.4f})"
    return row


def build_queue_rows(sample: SampleResult, origin: str,
                     dictionary=None) -> list[dict]:
    """Full features + pre-annotation suggestion for each sampled title.

    ``dictionary`` is an optional loaded
    :class:`cpegen.dictionary.LocalDictionary` — with none, every
    suggestion column stays blank and every dictionary-dependent feature
    reports ``False`` (never a crash; see :mod:`cpegen.title_features`).
    """
    rows = [_suggestion_row(t, origin, "random", dictionary)
           for t in sample.random_titles]
    rows += [_suggestion_row(t, origin, "hard", dictionary)
            for t in sample.hard_titles]
    return rows


def write_queue_csv(rows: list[dict], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
