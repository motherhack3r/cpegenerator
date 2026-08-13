"""Deterministic tools exposed to the Phase-4 agent.

The agent's LLM only reasons and decides which tool to call; every tool
here is deterministic code and is the single source of truth. The LLM
never validates, never classifies and never emits a final CPE by itself.

Tools:
- bind_and_validate: entities -> bound CPE 2.3 string + ABNF validation
- search_dictionary: CPE dictionary lookup — exact pair, vendor alias
                     table and clean+Dice canonicalization (WP1 step 4)
- classify_match:    M1-M3 classification of entities vs the dictionary
- submit:            final answer (entities + confidence); ends the loop

WP1 step 4 (2026-08-13): the agent used to see a strictly weaker
dictionary than the fast pass — a prefix lookup over raw values, with no
canonicalization. It now goes through the same
:meth:`cpegen.dictionary.LocalDictionary.lookup` the pipeline uses, so
the tool answers "the dictionary spells this ``rockwellautomation``"
instead of "no results", and reports the score, the margin, the ``part``
and the decision band the notary will apply. Same code, not a copy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .dictionary import lookup_for
from .matcher import classify
from .nvd import NVDClient
from .validator import validate_formatted_string
from .wfn import WFN, Logical, normalize_raw

MAX_DICT_RESULTS = 20

ENTITY_PROPERTIES = {
    "vendor": {"type": "string", "description": "vendor as in the CPE dictionary"},
    "product": {"type": "string", "description": "product name only"},
    "version": {"type": "string", "description": "version string; no beta/rc suffixes"},
    "update": {"type": "string", "description": "update/patch level (beta, rc2, sp1...)"},
    "target_sw": {"type": "string", "description": "software ecosystem (wordpress, node.js...)"},
}

TOOL_SCHEMAS = [
    {
        "name": "bind_and_validate",
        "description": (
            "Build the WFN from raw entities, bind it to a CPE 2.3 formatted "
            "string and run the deterministic ABNF validator. Returns the exact "
            "CPE that would be produced and any grammar errors. Always call this "
            "before submitting."
        ),
        "input_schema": {
            "type": "object",
            "properties": dict(ENTITY_PROPERTIES),
            "required": ["vendor", "product"],
        },
    },
    {
        "name": "search_dictionary",
        "description": (
            "Search the CPE dictionary. Provide vendor and/or product (any "
            "spelling: the lookup canonicalizes), and optionally the raw "
            "title to let it match on the whole string; or keyword for a "
            "free-text title search. Besides the entries it returns the "
            "canonical vendor:product the dictionary actually uses, the "
            "similarity score, the margin over the runner-up, the CPE part "
            "and the decision band. Use it to ground spelling: 'Rockwell "
            "Automation' is 'rockwellautomation', 'zoho corp' is 'zohocorp'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "product": {"type": "string"},
                "title": {"type": "string", "description": "raw title, if you have it"},
                "keyword": {"type": "string", "description": "free-text title search"},
            },
        },
    },
    {
        "name": "classify_match",
        "description": (
            "Classify the entities against the dictionary with the M1-M3 rules "
            "(deterministic; your confidence is echoed back but never affects the rule). Returns the rule (M1/M1A/M1B/M1C = high-confidence "
            "match or valid new-CPE candidate; M2/M2B/M3/M4 = weak or no candidate) and "
            "the matched dictionary CPE if any."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **ENTITY_PROPERTIES,
                "title": {"type": "string", "description": "raw title, if you have it"},
                "confidence": {"type": "number", "description": "your confidence in [0,1]"},
            },
            "required": ["vendor", "product", "confidence"],
        },
    },
    {
        "name": "submit",
        "description": (
            "Submit your final answer for this title. Only submit after "
            "bind_and_validate reports a valid CPE. The pipeline re-validates "
            "and re-classifies deterministically; your entities are a proposal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                **ENTITY_PROPERTIES,
                "confidence": {"type": "number", "description": "overall confidence in [0,1]"},
                "note": {"type": "string", "description": "one-line reasoning summary"},
            },
            "required": ["vendor", "confidence"],
        },
    },
]


def _dict_answer(entries, resolution, source: str) -> dict:
    """Shape a dictionary answer for the model.

    Deprecated entries are listed but marked, not hidden (decision
    2026-08-12): the agent must be able to see that the only entry for a
    pair is deprecated instead of concluding the pair does not exist.
    """
    out: dict = {
        "source": source,
        "total": len(entries),
        "entries": [
            {"cpe": e.cpe_name, "title": e.title,
             **({"deprecated": True} if e.deprecated else {})}
            for e in entries[:MAX_DICT_RESULTS]
        ],
    }
    if resolution is not None and resolution.winner is not None:
        w = resolution.winner
        out["canonical"] = {
            "vendor": w.vendor, "product": w.product, "part": w.part,
            "dice": round(w.score, 4), "margin": round(resolution.margin, 4),
            "decision": resolution.decision,
            "accepted": resolution.accepted,
            "deprecated": w.deprecated,
        }
        if resolution.review_reasons:
            out["canonical"]["review_reason"] = resolution.reason
        out["runners_up"] = [
            {"vendor": c.vendor, "product": c.product, "part": c.part,
             "dice": round(c.score, 4)}
            for c in resolution.candidates[1:4]
        ]
    return out


def build_wfn_from_args(args: dict) -> WFN:
    """Deterministically build a WFN from tool-call entity arguments."""

    def norm(key: str) -> str | Logical:
        val = args.get(key)
        if val is None or not str(val).strip():
            return Logical.ANY
        return normalize_raw(str(val))

    return WFN(
        part="a",
        vendor=norm("vendor"),
        product=norm("product"),
        version=norm("version"),
        update=norm("update"),
        target_sw=norm("target_sw"),
    )


@dataclass
class ToolBox:
    """Executes tool calls against the deterministic implementations."""

    nvd: NVDClient

    def execute(self, name: str, args: dict) -> str:
        """Run one tool call; always returns a JSON string for the model."""
        try:
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                return json.dumps({"error": f"unknown tool {name!r}"})
            return json.dumps(handler(args))
        except Exception as exc:  # never crash the loop on a tool error
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    # ------------------------------------------------------------- tools

    def _tool_bind_and_validate(self, args: dict) -> dict:
        wfn = build_wfn_from_args(args)
        cpe = wfn.bind()
        result = validate_formatted_string(cpe)
        return {"cpe": cpe, "valid": result.ok, "errors": result.errors}

    def _tool_search_dictionary(self, args: dict) -> dict:
        vendor = args.get("vendor")
        product = args.get("product")
        title = str(args.get("title") or "")
        keyword = args.get("keyword")
        if keyword:
            entries = self.nvd.keyword(str(keyword))
            return _dict_answer(entries, None, "keyword")
        vendor = normalize_raw(str(vendor)) if vendor else None
        product = normalize_raw(str(product)) if product else None
        if not vendor and not product and not title:
            return {"error": "provide vendor, product, title or keyword"}
        lookup = lookup_for(self.nvd, vendor, product, title=title)
        return _dict_answer(lookup.candidates, lookup.resolution,
                            lookup.source)

    def _tool_classify_match(self, args: dict) -> dict:
        wfn = build_wfn_from_args(args)
        vendor = wfn.vendor if isinstance(wfn.vendor, str) else None
        product = wfn.product if isinstance(wfn.product, str) else None
        title = str(args.get("title") or "")
        lookup = lookup_for(self.nvd, vendor, product, title=title)
        # Confidence is validated and echoed back, but never used in the
        # classification (deterministic cascade; decision 2026-07-24).
        confidence = float(args.get("confidence", 0.0))
        # The very same call the notary makes — shared code, never a
        # reimplementation, so the agent cannot be told one verdict and
        # the pipeline record another.
        match = classify(wfn, lookup.candidates, title=title,
                         resolution=lookup.resolution, ranges=lookup.ranges)
        return {
            "rule": match.rule,
            "rule_name": match.rule_name,
            "high_confidence": match.high_confidence,
            "similarity": round(match.similarity, 4),
            "confidence_reported": confidence,
            "matched_cpe": match.matched_cpe,
            "canonical_vendor": match.canonical_vendor,
            "canonical_product": match.canonical_product,
            "part": match.part,
            "dice": match.dice,
            "margin": match.margin,
            "decision": match.decision,
            "deprecated": match.deprecated,
            "version_source": match.version_source,
            "review_reason": match.review_reason,
            "detail": match.detail,
        }

    def _tool_submit(self, args: dict) -> dict:
        # The loop intercepts 'submit'; this is only a fallback echo.
        return {"submitted": True}
