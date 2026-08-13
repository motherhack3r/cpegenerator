"""Local CPE dictionary snapshot — Phase 7 step 2.

Removes the NVD throttling bottleneck at scale: a one-off full dump of
the CPE Products API 2.0 becomes a local snapshot (plain JSONL, gzipped
at rest — no sqlite: the project mount has no locking support), and the
first-pass lookup answers from memory. The NVD API is only hit for
misses, through the existing cached :class:`cpegen.nvd.NVDClient`.

Three pieces:

- :func:`build_snapshot` — resumable full dump (checkpoint after every
  page; a killed run continues where it left off). The network fetch is
  injectable, so tests run offline.
- :class:`LocalDictionary` — in-memory indexes over the snapshot
  (``(vendor, product)`` pairs, vendor-side and product-side
  representatives), exposing the same ``candidates_for`` contract as
  ``NVDClient``: exact pair first; on miss, the union of the vendor's
  catalog and the product's entries under *other* vendors — the local
  stand-in for the API's keyword fallback, without which the M1C, M2B
  and M3 rules can never fire offline (defect found on the 10k RAW
  pilot, 2026-08-11).
- :class:`HybridDictionary` — local first, wrapped client on miss;
  ``keyword`` always delegates (title scans belong to the API/cache).

WP1 step 2 (2026-08-13) adds the canonicalizing lookup of
`.ideas/CPE_LOOKUP_PLAYBOOK.md`, in pure stdlib and fully offline:

- :class:`PairIndex` — one row per distinct ``(vendor, product)`` with
  its ``clean(vendor + product)`` comparison key, its parts, its entry
  count and whether every entry is deprecated, plus an **inverted bigram
  index** over the keys. The index is the recall pre-filter the playbook
  lists as its highest-impact missing piece (§9.2/§10.1): instead of
  scoring all 150.578 pairs per title, only the pairs that share rare
  bigrams with the query are scored, with a provable no-false-negative
  bound (see :meth:`PairIndex.search`).
- :class:`VendorAliases` — the materialized vendor alias table of §10.3.
  Coexisting canonical variants (``schneider-electric`` **and**
  ``schneider_electric``) fall out of keying vendors by ``clean()``; the
  TFM seed pairs and the legal-suffix trimming rules are candidate
  generators that are only kept when the target vendor really exists in
  the snapshot — never a blind substitution (docs/match-rules.md).
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import time
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .matcher import MIN_DICE, PairResolution, ScoredPair, bigrams, clean, decide
from .nvd import API_URL, DictEntry, NVDClient
from .validator import validate_formatted_string
from .wfn import bind_component, normalize_raw, split_formatted_string

DEFAULT_SNAPSHOT = Path("data/cache/cpe_dictionary.jsonl.gz")
PAGE_SIZE = 10_000          # API maximum for the CPE Products endpoint
CANDIDATE_CAP = 2_000       # same cap as NVDClient pagination
SCORE_CAP = 4_000           # max pairs exactly scored per query (see search)

FetchPage = Callable[[int, int], dict]

# --- vendor alias table seed (docs/match-rules.md, actionable #1) -------
# Nine literal renames recovered from cpe_wfn_vendor() of the TFM's R
# package `mitre`; keys and values are clean() keys. Each one is kept
# only if the target vendor exists in the loaded snapshot.
VENDOR_ALIAS_SEED: dict[str, str] = {
    "hewlettpackard": "hp",
    "advancedmicrodevices": "amd",
    # The TFM mapped ASUSTek to "ASUSTEK"; the NVD's own spelling is
    # "asus" (1.198 CPEs) and "asustek" does not exist — retargeted after
    # checking the 2026-07-02 snapshot, which is exactly the validation
    # step that keeps this table from being a blind rewrite.
    "asustekcomputer": "asus",
    "asustekcomputerinc": "asus",
    "asustekcomputerincorporated": "asus",
    "amazonwebservices": "amazon",
    "adobesystems": "adobe",
    "adobesystemsinc": "adobe",
    "adobesystemsincorporated": "adobe",
    # Both R renames of the TFM land on the same real vendor key, which
    # itself has coexisting variants ("r-project" 32 CPEs, "r_project" 1).
    "rcoreteam": "rproject",
    "therfoundation": "rproject",
    "sapxx": "sap",
    # Kept although it does not validate today: "its" is not an NVD
    # vendor, so :meth:`VendorAliases.build` drops it and reports it.
    # Dropping loudly beats carrying a rename that resolves to nothing.
    "internettestingsystems": "its",
}

# Legal-form suffixes (actionable #2). Applied as a *candidate* alias to
# validate against the snapshot, never as a blind rewrite: the TFM itself
# showed the risk by trimming "software"/"soft" with no end anchor.
LEGAL_SUFFIXES: tuple[str, ...] = (
    "corporations", "corporation", "corp", "incorporated", "inc",
    "company", "international", "technologies", "technology", "limited",
    "ltd", "llc", "gmbh", "foundation", "software", "sa", "sl", "spa",
    "sas", "lp", "bv", "ag", "srl",
)
MIN_ALIAS_STEM = 3          # never trim a vendor down to a stub


# --------------------------------------------------------------- build

def _api_fetch(api_key: str | None) -> FetchPage:
    """Default page fetcher: throttled, with backoff on 429/5xx."""
    import requests

    min_interval = 0.7 if api_key else 6.5
    last = 0.0

    def fetch(start_index: int, page_size: int) -> dict:
        nonlocal last
        headers = {"apiKey": api_key} if api_key else {}
        for attempt in range(5):
            wait = last + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            resp = requests.get(
                API_URL,
                params={"startIndex": start_index,
                        "resultsPerPage": page_size},
                headers=headers, timeout=120)
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                time.sleep(min(30 * (attempt + 1), 120))
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return {}  # unreachable; keeps the type checker honest

    return fetch


def _neo4j_fetch(url: str | None = None, user: str | None = None,
                 password: str | None = None, database: str | None = None,
                 post: Callable[..., dict] | None = None) -> FetchPage:
    """Page fetcher over a local KGCS Neo4j (Platform nodes = CPE dict).

    Speaks the plain Neo4j HTTP transactional API through ``requests`` —
    no driver dependency. Returns pages in the same shape as the NVD
    API, so :func:`build_snapshot` (and its resume logic) is source-
    agnostic. ``post`` is injectable for offline tests.

    Config via env when not passed: ``NEO4J_URL`` (default
    ``http://localhost:7474``), ``NEO4J_USER`` (default ``neo4j``),
    ``NEO4J_PASSWORD``, ``NEO4J_DATABASE`` (default ``neo4j``).
    """
    url = (url or os.environ.get("NEO4J_URL", "http://localhost:7474")).rstrip("/")
    user = user or os.environ.get("NEO4J_USER", "neo4j")
    password = password or os.environ.get("NEO4J_PASSWORD", "")
    database = database or os.environ.get("NEO4J_DATABASE", "neo4j")
    endpoint = f"{url}/db/{database}/tx/commit"

    if post is None:
        import requests

        def post(statement: str, parameters: dict) -> dict:
            resp = requests.post(
                endpoint,
                json={"statements": [{"statement": statement,
                                      "parameters": parameters}]},
                auth=(user, password), timeout=300)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                raise RuntimeError(f"neo4j: {data['errors']}")
            return data

    total: int | None = None

    def fetch(start_index: int, page_size: int) -> dict:
        nonlocal total
        if total is None:
            data = post("MATCH (p:Platform) RETURN count(*)", {})
            total = data["results"][0]["data"][0]["row"][0]
        data = post(
            "MATCH (p:Platform) "
            "RETURN p.cpeUri, p.cpeNameId, p.deprecated, "
            "p.vendor, p.product, p.version "
            "ORDER BY p.cpeNameId SKIP $skip LIMIT $limit",
            {"skip": start_index, "limit": page_size})
        rows = [d["row"] for d in data["results"][0]["data"]]
        products = []
        for uri, name_id, deprecated, vendor, product, version in rows:
            title = " ".join(v for v in (vendor, product, version)
                             if v and v != "*")
            products.append({"cpe": {
                "cpeName": uri or "", "cpeNameId": name_id or "",
                "titles": [{"title": title, "lang": "en"}] if title else [],
                "deprecated": bool(deprecated)}})
        return {"totalResults": total, "resultsPerPage": len(rows),
                "products": products}

    return fetch


def _entry_from_product(p: dict) -> dict:
    titles = p.get("titles", [])
    title = next((t["title"] for t in titles if t.get("lang") == "en"),
                 titles[0]["title"] if titles else "")
    return {"cpeName": p.get("cpeName", ""),
            "cpeNameId": p.get("cpeNameId", ""),
            "title": title,
            "deprecated": bool(p.get("deprecated", False))}


def build_snapshot(out_path: Path = DEFAULT_SNAPSHOT,
                   api_key: str | None = None,
                   fetch: FetchPage | None = None,
                   source: str = "nvd",
                   page_size: int = PAGE_SIZE,
                   progress: Callable[[int, int], None] | None = None,
                   ) -> dict:
    """Dump the full CPE dictionary to ``out_path`` (JSONL, gzipped).

    Resumable: progress is checkpointed to ``<out>.meta.json`` after
    every page and rows are appended to ``<out>.part``; rerunning after
    an interruption continues from the last complete page. On completion
    the part file is compressed into ``out_path`` and removed.

    Returns the final meta dict (total, fetched, invalid, built pages).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = out_path.with_suffix(out_path.suffix + ".part")
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    if fetch is None:
        fetch = (_neo4j_fetch() if source == "neo4j"
                 else _api_fetch(api_key or os.environ.get("NVD_API_KEY")))

    meta = {"done": False, "resume_index": 0, "total": None,
            "fetched": 0, "invalid": 0, "page_size": page_size,
            "source": source}
    if meta_path.exists() and part_path.exists():
        saved = json.loads(meta_path.read_text(encoding="utf-8"))
        if not saved.get("done") and saved.get("page_size") == page_size:
            meta = saved

    mode = "a" if meta["resume_index"] else "w"
    with open(part_path, mode, encoding="utf-8") as out:
        while meta["total"] is None or meta["resume_index"] < meta["total"]:
            data = fetch(meta["resume_index"], page_size)
            meta["total"] = data.get("totalResults", 0)
            products = data.get("products", [])
            for p in products:
                entry = _entry_from_product(p["cpe"] if "cpe" in p else p)
                if not validate_formatted_string(entry["cpeName"]).ok:
                    meta["invalid"] += 1  # kept, but counted: NVD is the
                    # reference — a grammar drift there must be visible
                out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                meta["fetched"] += 1
            got = data.get("resultsPerPage", len(products)) or len(products)
            meta["resume_index"] += got
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            if progress:
                progress(meta["resume_index"], meta["total"])
            if not products:  # server returned an empty page: stop
                break

    with open(part_path, "rb") as src, gzip.open(out_path, "wb") as dst:
        while chunk := src.read(1 << 20):
            dst.write(chunk)
    meta["done"] = True
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    part_path.unlink()
    return meta


# -------------------------------------------------- canonicalizing index

@dataclass
class PairIndex:
    """Distinct ``(vendor, product)`` pairs plus an inverted bigram index.

    One row per pair (150.578 in the 2026-07-02 snapshot), not per CPE
    entry (1.77M): the version adds nothing to a vendor/product
    similarity search and would multiply the work by twelve.
    """

    vendors: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)      # clean(vendor+product)
    nbigrams: array = field(default_factory=lambda: array("i"))
    cpes: array = field(default_factory=lambda: array("i"))
    parts: list[tuple[str, ...]] = field(default_factory=list)
    deprecated: bytearray = field(default_factory=bytearray)
    postings: dict[str, array] = field(default_factory=dict)
    ids: dict[tuple[str, str], int] = field(default_factory=dict)
    scans: int = 0            # queries served
    capped: int = 0           # queries whose exact scoring hit SCORE_CAP

    def __len__(self) -> int:
        return len(self.keys)

    def scored_pair(self, vendor: str, product: str,
                    score: float = 1.0) -> list[ScoredPair]:
        """The known part variants of one pair, as scored candidates."""
        pid = self.ids.get((vendor, product))
        if pid is None:
            return [ScoredPair(vendor, product, "", score)]
        dep = bool(self.deprecated[pid])
        return [ScoredPair(vendor, product, part, score, self.cpes[pid], dep)
                for part in self.parts[pid]]

    def add(self, vendor: str, product: str, parts: tuple[str, ...],
            cpes: int, all_deprecated: bool) -> None:
        pid = len(self.keys)
        self.ids[(vendor, product)] = pid
        key = clean(vendor + product)
        self.vendors.append(vendor)
        self.products.append(product)
        self.keys.append(key)
        self.nbigrams.append(max(len(key) - 1, 0))
        self.cpes.append(cpes)
        self.parts.append(parts)
        self.deprecated.append(1 if all_deprecated else 0)
        for b in {key[i:i + 2] for i in range(len(key) - 1)}:
            bucket = self.postings.get(b)
            if bucket is None:
                bucket = self.postings[b] = array("i")
            bucket.append(pid)

    # ---------------------------------------------------------- search

    def search(self, query: str,
               min_score: float = MIN_DICE) -> list[ScoredPair]:
        """Pairs scoring at least ``min_score`` against a cleaned query.

        The pre-filter is admissible — it cannot drop a pair that would
        have passed the threshold, except through the documented cap.
        Reasoning: a pair can only reach Dice ``T`` if its shared bigram
        mass with the query is at least ``T*(nA+nB)/2``. Posting lists
        are visited from the rarest bigram upwards and the walk stops as
        soon as the query mass still unvisited, ``U``, is too small for
        any pair to reach ``T`` on the unvisited bigrams alone
        (``2U/(nA+nB_min) < T``, with ``nB_min`` the shortest key that
        could still reach ``T``). Everything scanned then carries an
        upper bound ``2*(seen+U)/(nA+nB)`` on its true score; only pairs
        whose bound clears ``T`` are scored exactly.

        The 43 bigrams that occur in more than 10% of the pairs
        (``fi``/``ir``/``rm``/``wa`` — "firmware" — plus ``re``/``er``…)
        are exactly the ones this leaves unvisited, which is where the
        speedup comes from.
        """
        self.scans += 1
        qc = bigrams(query)
        na = sum(qc.values())
        if not na:
            return []
        nb_min = min_score * na / (2 - min_score)
        budget = min_score * (na + nb_min) / 2
        order = sorted(qc, key=lambda b: len(self.postings.get(b, ())))
        unseen = float(na)
        seen: dict[int, int] = {}
        for b in order:
            if unseen < budget:
                break
            unseen -= qc[b]
            bucket = self.postings.get(b)
            if bucket is None:
                continue
            mult = qc[b]
            for pid in bucket:
                seen[pid] = seen.get(pid, 0) + mult
        if not seen:
            return []

        # Length filter: shared mass never exceeds either side's own mass,
        # so a key shorter than ``lo`` or longer than ``hi`` cannot reach
        # ``min_score`` however well it overlaps. Checked first because it
        # is two comparisons and discards most of the scanned pairs.
        lo = min_score * na / (2 - min_score)
        hi = (2 - min_score) * na / min_score
        bounded: list[tuple[float, int]] = []
        nbg = self.nbigrams
        for pid, hit in seen.items():
            nb = nbg[pid]
            if nb < lo or nb > hi:
                continue
            reach = hit + unseen
            if nb < reach:
                reach = nb
            if 2 * reach >= min_score * (na + nb):
                bounded.append((reach / (na + nb), pid))
        if len(bounded) > SCORE_CAP:
            # Deliberate, reported cap: no silent truncation. The bound is
            # monotone in the true score, so the survivors are the most
            # promising ones.
            bounded.sort(key=lambda t: -t[0])
            del bounded[SCORE_CAP:]
            self.capped += 1

        out: list[ScoredPair] = []
        for _, pid in bounded:
            score = _dice_from_counts(qc, na, self.keys[pid],
                                      self.nbigrams[pid])
            if score < min_score:
                continue
            dep = bool(self.deprecated[pid])
            for part in self.parts[pid]:
                out.append(ScoredPair(vendor=self.vendors[pid],
                                      product=self.products[pid],
                                      part=part, score=score,
                                      cpes=self.cpes[pid], deprecated=dep))
        return out


def _dict_key(value: str | None) -> str:
    """Free-text attribute value -> the dictionary's own component form.

    ``normalize_raw`` first (lowercase, spaces to underscores) so that a
    caller holding raw text — the agent's tools, a hand-typed query —
    reaches the same index cell as the pipeline, which normalizes before
    binding. Idempotent on already-normalized values.
    """
    if not value:
        return ""
    return bind_component(normalize_raw(value))


def _dice_from_counts(qc: dict, na: int, key: str, nb: int) -> float:
    """Multiset Dice of a pre-counted query against a stored key.

    Identical to ``matcher.dice`` by construction (there is a test), but
    written as a single walk over the key with no ``Counter`` allocation:
    this runs a few thousand times per title and was 58% of lookup time
    when it built two Counters and intersected them.
    """
    if not nb:
        return 0.0
    common = 0
    used: dict[str, int] = {}
    get_q = qc.get
    get_u = used.get
    for i in range(nb):
        b = key[i:i + 2]
        taken = get_u(b, 0)
        if taken < get_q(b, 0):
            used[b] = taken + 1
            common += 1
    return 2 * common / (na + nb)


@dataclass
class VendorAliases:
    """Materialized vendor alias table (playbook §10.3).

    ``variants`` is the table itself: every ``clean()`` vendor key of the
    snapshot mapped to the canonical spellings that share it, ordered by
    CPE volume. This is what makes coexisting variants a lookup instead
    of a runtime problem — ``schneiderelectric`` resolves to BOTH
    ``schneider-electric`` (2.767 CPEs) and ``schneider_electric`` (38),
    and resolving only one would be a silent loss of coverage (§2.1).

    ``seed`` holds the TFM literal renames that survived validation
    against this snapshot; the legal-suffix rules are applied at query
    time by :meth:`resolve` and likewise only accepted when the trimmed
    stem is a vendor the dictionary actually knows.
    """

    variants: dict[str, list[str]] = field(default_factory=dict)
    seed: dict[str, str] = field(default_factory=dict)
    dropped_seed: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, vendor_cpes: dict[str, int]) -> "VendorAliases":
        variants: dict[str, list[str]] = {}
        for vendor in vendor_cpes:
            variants.setdefault(clean(vendor), []).append(vendor)
        for key, names in variants.items():
            names.sort(key=lambda v: (-vendor_cpes[v], v))
        seed, dropped = {}, []
        for src, dst in VENDOR_ALIAS_SEED.items():
            (seed.__setitem__(src, dst) if dst in variants
             else dropped.append(f"{src}->{dst}"))
        return cls(variants=variants, seed=seed, dropped_seed=sorted(dropped))

    def keys_for(self, vendor: str) -> list[str]:
        """Clean vendor keys to try, best first, deduplicated."""
        key = clean(vendor)
        out = [key]
        target = self.seed.get(key)
        if target:
            out.append(target)
        for suffix in LEGAL_SUFFIXES:
            if key.endswith(suffix) and len(key) - len(suffix) >= MIN_ALIAS_STEM:
                stem = key[:-len(suffix)]
                if stem in self.variants and stem not in out:
                    out.append(stem)
        return [k for i, k in enumerate(out) if k not in out[:i]]

    def resolve(self, vendor: str) -> list[str]:
        """Canonical dictionary vendor spellings for a free-text vendor."""
        out: list[str] = []
        for key in self.keys_for(vendor):
            for name in self.variants.get(key, ()):
                if name not in out:
                    out.append(name)
        return out

    def rows(self) -> Iterable[tuple[str, str, int]]:
        """The materialized table, one row per (key, canonical, rank)."""
        for key in sorted(self.variants):
            for rank, name in enumerate(self.variants[key]):
                yield (key, name, rank)


@dataclass
class Lookup:
    """What the notary needs for one row: candidates plus resolution."""

    candidates: list[DictEntry] = field(default_factory=list)
    resolution: PairResolution | None = None
    source: str = "miss"   # pair | alias | dice | union | api | miss


# -------------------------------------------------------------- lookup

@dataclass
class LocalDictionary:
    """In-memory indexes over a snapshot file.

    ``by_pair`` holds every entry (all versions) keyed by
    ``(vendor, product)`` — the M1/M1A/M1B path needs the full version
    list. ``vendor_reps`` and ``product_reps`` hold ONE representative
    entry per distinct ``(vendor, product)`` pair, keyed by vendor and
    by product respectively: classification of the non-pair rules (M1C,
    M2, M2B, M3) only compares vendor/product fields, so one entry per
    pair carries the full signal at a fraction of the candidate volume
    (e.g. vendor ``hp``: 22k entries but far fewer distinct products —
    an un-deduplicated vendor fallback both blew past CANDIDATE_CAP and
    biased the similarity search to an arbitrary slice).
    """

    by_pair: dict[tuple[str, str], list[DictEntry]] = field(
        default_factory=dict)
    vendor_reps: dict[str, list[DictEntry]] = field(default_factory=dict)
    product_reps: dict[str, list[DictEntry]] = field(default_factory=dict)
    index: PairIndex = field(default_factory=PairIndex)
    aliases: VendorAliases = field(default_factory=VendorAliases)
    size: int = 0
    hits: int = 0
    misses: int = 0
    # lookup provenance counters (WP1 measurement)
    pair_hits: int = 0
    alias_hits: int = 0
    dice_hits: int = 0

    @classmethod
    def load(cls, path: Path | str = DEFAULT_SNAPSHOT,
             build_index: bool = True) -> "LocalDictionary":
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        d = cls()
        parts: dict[tuple[str, str], set[str]] = {}
        live: dict[tuple[str, str], int] = {}
        vendor_cpes: dict[str, int] = {}
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                raw = json.loads(line)
                entry = DictEntry(cpe_name=raw["cpeName"],
                                  cpe_name_id=raw["cpeNameId"],
                                  title=raw["title"],
                                  deprecated=raw["deprecated"])
                comps = split_formatted_string(entry.cpe_name)
                if len(comps) != 13:
                    continue  # counted as invalid at build time
                vendor, product = comps[3], comps[4]
                pair = (vendor, product)
                bucket = d.by_pair.setdefault(pair, [])
                if not bucket:  # first sighting of this pair
                    d.vendor_reps.setdefault(vendor, []).append(entry)
                    d.product_reps.setdefault(product, []).append(entry)
                    parts[pair] = set()
                    live[pair] = 0
                bucket.append(entry)
                parts[pair].add(comps[2])
                if not entry.deprecated:
                    live[pair] += 1
                vendor_cpes[vendor] = vendor_cpes.get(vendor, 0) + 1
                d.size += 1
        d.aliases = VendorAliases.build(vendor_cpes)
        if build_index:
            for pair, entries in d.by_pair.items():
                d.index.add(pair[0], pair[1],
                            tuple(sorted(parts[pair])), len(entries),
                            all_deprecated=live[pair] == 0)
        return d

    # ------------------------------------------------- canonical lookup

    def resolve(self, query: str, title: str = "") -> PairResolution:
        """Rank dictionary pairs against a free-text query (clean+Dice).

        ``query`` is raw text (a title, or ``vendor + product``); it is
        cleaned here so the key is symmetric with the dictionary side.
        """
        cleaned = clean(query)
        if not cleaned:
            return PairResolution(query=cleaned)
        return decide(self.index.search(cleaned), title or query,
                      query=cleaned)

    def entries_for_pair(self, vendor: str, product: str) -> list[DictEntry]:
        return self.by_pair.get((vendor, product), [])[:CANDIDATE_CAP]

    def lookup(self, vendor: str | None, product: str | None,
               title: str = "", query_mode: str = "both") -> Lookup:
        """The full WP1 lookup: exact pair -> alias -> clean+Dice -> union.

        Cheapest first, and each stage is only reached when the previous
        one found nothing, so the canonicalization cost is paid only by
        the rows that actually need it.

        ``query_mode`` selects what the Dice stage compares against the
        dictionary key: the raw ``title`` (what the playbook validated),
        the extracted ``entities`` (``vendor + product``, free of version
        noise), or ``both`` — title first, entities only when the title
        did not produce an accepted resolution.
        """
        bv = _dict_key(vendor)
        bp = _dict_key(product)
        evidence = title or f"{vendor or ''} {product or ''}"

        if bv and bp:
            exact = self.entries_for_pair(bv, bp)
            if exact:
                self.hits += 1
                self.pair_hits += 1
                # Same decision code as every other stage (shared, never a
                # copy): it is what corrects ``part`` and raises the
                # versioned-family flag on an otherwise perfect hit.
                res = decide(self.index.scored_pair(bv, bp), evidence,
                             query=clean(f"{vendor} {product}"))
                return Lookup(exact, res, "pair")
            # Vendor alias table: same product, canonical vendor spelling.
            for canonical in self.aliases.resolve(vendor or ""):
                if canonical == bv:
                    continue
                hit = self.entries_for_pair(canonical, bp)
                if hit:
                    self.hits += 1
                    self.alias_hits += 1
                    res = decide(self.index.scored_pair(canonical, bp),
                                 evidence, query=clean(vendor or ""))
                    return Lookup(hit, res, "alias")

        entities = f"{vendor or ''} {product or ''}".strip()
        queries: list[str] = []
        if query_mode in ("title", "both") and title:
            queries.append(title)
        if query_mode in ("entities", "both") and entities:
            queries.append(entities)
        if not queries:
            queries = [evidence]

        resolution = PairResolution()
        for query in queries:
            candidate = self.resolve(query, title=evidence)
            if candidate.score > resolution.score:
                resolution = candidate
            if resolution.accepted:
                break
        if resolution.accepted and resolution.winner is not None:
            w = resolution.winner
            entries = self.entries_for_pair(w.vendor, w.product)
            if entries:
                self.hits += 1
                self.dice_hits += 1
                return Lookup(entries, resolution, "dice")

        union = self.candidates_for(vendor, product)
        return Lookup(union, resolution, "union" if union else "miss")

    def candidates_for(self, vendor: str | None,
                       product: str | None) -> list[DictEntry]:
        """Same contract as NVDClient.candidates_for.

        Exact pair first (all versions). On pair miss, the union of the
        vendor's product representatives and the product's entries under
        other vendors — the offline equivalent of the API's vendor
        prefix + keyword fallbacks, and the candidate set the M1C, M2,
        M2B and M3 rules need to be reachable at all.
        """
        if vendor and product:
            results = self.by_pair.get(
                (bind_component(vendor), bind_component(product)), [])
            if results:
                self.hits += 1
                return results[:CANDIDATE_CAP]
        union: list[DictEntry] = []
        seen: set[str] = set()
        if vendor:
            for e in self.vendor_reps.get(bind_component(vendor), []):
                if e.cpe_name not in seen:
                    seen.add(e.cpe_name)
                    union.append(e)
        if product:
            for e in self.product_reps.get(bind_component(product), []):
                if e.cpe_name not in seen:
                    seen.add(e.cpe_name)
                    union.append(e)
        if union:
            self.hits += 1
        else:
            self.misses += 1
        return union[:CANDIDATE_CAP]


class HybridDictionary:
    """Local snapshot first; the (cached, throttled) NVD API on miss.

    Exposes the exact interface the pipeline, tools and agent consume:
    ``candidates_for`` and ``keyword``.
    """

    def __init__(self, local: LocalDictionary, client: NVDClient):
        self.local = local
        self.client = client
        self.api_fallbacks = 0

    def candidates_for(self, vendor: str | None,
                       product: str | None) -> list[DictEntry]:
        results = self.local.candidates_for(vendor, product)
        if results:
            return results
        self.api_fallbacks += 1
        return self.client.candidates_for(vendor, product)

    def lookup(self, vendor: str | None, product: str | None,
               title: str = "") -> Lookup:
        result = self.local.lookup(vendor, product, title=title)
        if result.candidates:
            return result
        self.api_fallbacks += 1
        return Lookup(self.client.candidates_for(vendor, product),
                      result.resolution, "api")

    def keyword(self, keywords: str) -> list[DictEntry]:
        return self.client.keyword(keywords)


def lookup_for(client, vendor: str | None, product: str | None,
               title: str = "") -> Lookup:
    """Uniform lookup over any dictionary-ish client.

    ``NVDClient`` has no canonicalization layer, so it degrades to plain
    candidates with no resolution — the pipeline keeps working without a
    local snapshot, only without the WP1 gains.
    """
    fn = getattr(client, "lookup", None)
    if fn is not None:
        return fn(vendor, product, title=title)
    return Lookup(client.candidates_for(vendor, product), None, "api")


def write_alias_table(local: LocalDictionary, out_path: Path) -> int:
    """Materialize the vendor alias table to CSV (playbook §10.3).

    Only keys with more than one canonical spelling, or with a validated
    seed rename pointing at them, are written: those are the rows that
    carry information a bare ``clean()`` does not already give.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    targets = set(local.aliases.seed.values())
    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["clean_key", "canonical_vendor", "rank", "origin"])
        for key, name, rank in local.aliases.rows():
            variants = local.aliases.variants[key]
            if len(variants) == 1 and key not in targets:
                continue
            origin = "seed" if key in targets else "variant"
            writer.writerow([key, name, rank, origin])
            written += 1
        for src, dst in sorted(local.aliases.seed.items()):
            for rank, name in enumerate(local.aliases.variants[dst]):
                writer.writerow([src, name, rank, "seed-rename"])
                written += 1
    return written
