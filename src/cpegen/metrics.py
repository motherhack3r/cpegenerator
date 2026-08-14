"""Evaluation metrics: entity-level NER evaluation (MUC / SemEval'13),
exact-CPE accuracy and M1-M3 distribution.

Entity evaluation follows the MUC categories as popularized by SemEval-2013
task 9.1 (see D. S. Batista, "Named-Entity evaluation metrics based on
entity-level", 2018-05-09):

- COR (correct):   gold and prediction are the same
- INC (incorrect): both present but no overlap at all
- PAR (partial):   both present and they overlap (shared tokens or one
                   contains the other) without being identical
- MIS (missing):   gold entity not predicted
- SPU (spurious):  predicted entity with no gold counterpart

POSSIBLE = COR + INC + PAR + MIS      (gold annotations in play)
ACTUAL   = COR + INC + PAR + SPU      (system annotations produced)

Two schemes are reported per entity:
- strict:  P = COR / ACTUAL,              R = COR / POSSIBLE
- partial: P = (COR + 0.5*PAR) / ACTUAL,  R = (COR + 0.5*PAR) / POSSIBLE

Note: in this pipeline each entity type is a fixed slot of the extraction
(vendor/product/version/target_sw), so the entity *type* can never be
wrong; the SemEval "type" and "exact" schemes collapse into "strict" and
only strict/partial are meaningful. Comparison is done on normalized
values (lowercase, whitespace -> underscore), i.e. what ends up in the CPE.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .goldset import GoldRecord
from .wfn import normalize_raw

ENTITIES = ("vendor", "product", "version", "target_sw")

# 2023 baseline over ~526k real inventory titles (docs/match-rules.md)
BASELINE_2023 = {
    "M1": 1.18, "M1A": 1.91, "M1B": 0.76, "M1C": 1.04,
    "M2": 53.28, "M2B": 3.52, "M3": 38.31,
    # M4 is a v2 addition (no-signal bucket, split out of the baseline's
    # M3 on 2026-08-11): compare v2's M3+M4 against the baseline's M3.
    "M4": None,
}
BASELINE_HIGH_CONFIDENCE = 4.89  # M1+M1A+M1B+M1C (%)


def compare_entity(gold: str | None, pred: str | None) -> str | None:
    """MUC category for one gold/predicted pair of normalized values.

    Returns 'COR', 'INC', 'PAR', 'MIS', 'SPU' or None (both absent).
    """
    if gold is None and pred is None:
        return None
    if pred is None:
        return "MIS"
    if gold is None:
        return "SPU"
    if gold == pred:
        return "COR"
    if _overlaps(gold, pred):
        return "PAR"
    return "INC"


def _overlaps(a: str, b: str) -> bool:
    """Partial-boundary criterion: shared tokens or containment.

    Values are already normalized (underscores as separators), so token
    overlap approximates the surface-boundary overlap of SemEval.
    """
    if a in b or b in a:
        return True
    return bool(set(a.split("_")) & set(b.split("_")))


@dataclass
class EntityEval:
    """MUC counts and SemEval strict/partial metrics for one entity type."""

    cor: int = 0
    inc: int = 0
    par: int = 0
    mis: int = 0
    spu: int = 0

    def add(self, category: str) -> None:
        setattr(self, category.lower(), getattr(self, category.lower()) + 1)

    @property
    def possible(self) -> int:
        return self.cor + self.inc + self.par + self.mis

    @property
    def actual(self) -> int:
        return self.cor + self.inc + self.par + self.spu

    # -- strict scheme -------------------------------------------------

    @property
    def strict_precision(self) -> float:
        return self.cor / self.actual if self.actual else 0.0

    @property
    def strict_recall(self) -> float:
        return self.cor / self.possible if self.possible else 0.0

    @property
    def strict_f1(self) -> float:
        p, r = self.strict_precision, self.strict_recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    # -- partial scheme ------------------------------------------------

    @property
    def partial_precision(self) -> float:
        return (self.cor + 0.5 * self.par) / self.actual if self.actual else 0.0

    @property
    def partial_recall(self) -> float:
        return (self.cor + 0.5 * self.par) / self.possible if self.possible else 0.0

    @property
    def partial_f1(self) -> float:
        p, r = self.partial_precision, self.partial_recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class Report:
    n: int = 0
    entity_counts: dict = field(
        default_factory=lambda: {e: EntityEval() for e in ENTITIES})
    cpe_exact: int = 0
    cpe_valid: int = 0
    rule_counts: Counter = field(default_factory=Counter)
    extraction_errors: int = 0
    # WP2: which dictionary layer (nvd | motherhacker | <origin> | miss)
    # answered each row. Reported alongside M1-M3, never folded into it —
    # the M scale stays uniform whichever layers were consulted.
    dictionary_source_counts: Counter = field(default_factory=Counter)

    def add_entities(self, gold: GoldRecord, predicted: dict) -> None:
        """Update MUC categories for one title."""
        self.n += 1
        for ent in ENTITIES:
            g = getattr(gold, ent)
            g = normalize_raw(g) if g else None
            p = predicted.get(ent)
            p = normalize_raw(p) if p else None
            category = compare_entity(g, p)
            if category:
                self.entity_counts[ent].add(category)

    def to_markdown(self) -> str:
        lines = ["# Informe MVP — CPEgenerator v2", ""]
        lines.append(f"Títols processats: **{self.n}** "
                     f"(errors d'extracció: {self.extraction_errors})")
        lines.append("")
        lines.append("## Avaluació NER a nivell d'entitat (MUC / SemEval'13)")
        lines.append("")
        lines.append("| Entitat | COR | INC | PAR | MIS | SPU "
                     "| P strict | R strict | F1 strict "
                     "| P partial | R partial | F1 partial |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for ent in ENTITIES:
            c = self.entity_counts[ent]
            lines.append(
                f"| {ent} | {c.cor} | {c.inc} | {c.par} | {c.mis} | {c.spu} "
                f"| {c.strict_precision:.3f} | {c.strict_recall:.3f} "
                f"| {c.strict_f1:.3f} "
                f"| {c.partial_precision:.3f} | {c.partial_recall:.3f} "
                f"| {c.partial_f1:.3f} |")
        lines.append("")
        lines.append("> strict: només COR compta; partial: COR + 0,5·PAR "
                     "(solapament de tokens o contenció). El tipus d'entitat "
                     "és fix per camp, així que els esquemes SemEval 'type' i "
                     "'exact' coincideixen amb 'strict'.")
        lines.append("")
        lines.append("## CPE complet")
        lines.append("")
        pct_valid = 100 * self.cpe_valid / self.n if self.n else 0
        pct_exact = 100 * self.cpe_exact / self.n if self.n else 0
        lines.append(f"- CPEs sintàcticament vàlids (validador ABNF): "
                     f"**{self.cpe_valid}/{self.n}** ({pct_valid:.1f}%)")
        lines.append(f"- CPE exacte vs gold (v:p:v + target_sw): "
                     f"**{self.cpe_exact}/{self.n}** ({pct_exact:.1f}%)")
        lines.append("")
        lines.append("## Distribució M1–M3 (vs línia base 2023)")
        lines.append("")
        lines.append("| Regla | Count | % | Base 2023 % |")
        lines.append("|---|---:|---:|---:|")
        total = sum(self.rule_counts.values()) or 1
        for rule in ("M1", "M1A", "M1B", "M1C", "M2", "M2B", "M3", "M4"):
            cnt = self.rule_counts.get(rule, 0)
            base = BASELINE_2023.get(rule)
            base_s = f"{base:.2f}%" if base is not None else "— (dins M3)"
            lines.append(f"| {rule} | {cnt} | {100 * cnt / total:.1f}% "
                         f"| {base_s} |")
        hi = sum(self.rule_counts.get(r, 0) for r in ("M1", "M1A", "M1B", "M1C"))
        lines.append("")
        lines.append(f"**Resolució automàtica d'alta confiança (M1x): "
                     f"{100 * hi / total:.1f}%** (base 2023: "
                     f"{BASELINE_HIGH_CONFIDENCE}% sobre inventari brut)")
        lines.append("")
        if self.dictionary_source_counts:
            lines.append("## Procedència del diccionari (WP2)")
            lines.append("")
            lines.append("| Capa | Count | % |")
            lines.append("|---|---:|---:|")
            dtotal = sum(self.dictionary_source_counts.values()) or 1
            for source, cnt in sorted(self.dictionary_source_counts.items(),
                                      key=lambda x: -x[1]):
                label = source or "(miss)"
                lines.append(f"| {label} | {cnt} | "
                             f"{100 * cnt / dtotal:.1f}% |")
            lines.append("")
        lines.append("> Nota: la base 2023 es va mesurar sobre ~526k títols bruts "
                     "d'SCCM; el gold set són títols nets estil NVD. Les xifres són "
                     "orientatives fins que el benchmark corri sobre títols bruts "
                     "(Fase 1 del ROADMAP).")
        return "\n".join(lines)
