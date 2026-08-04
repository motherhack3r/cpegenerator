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
- :class:`LocalDictionary` — in-memory ``(vendor, product)`` index over
  the snapshot, exposing the same ``candidates_for`` contract as
  ``NVDClient`` (exact pair first, vendor-only fallback, capped).
- :class:`HybridDictionary` — local first, wrapped client on miss;
  ``keyword`` always delegates (title scans belong to the API/cache).
"""

from __future__ import annotations

import gzip
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .nvd import API_URL, DictEntry, NVDClient
from .validator import validate_formatted_string
from .wfn import bind_component, split_formatted_string

DEFAULT_SNAPSHOT = Path("data/cache/cpe_dictionary.jsonl.gz")
PAGE_SIZE = 10_000          # API maximum for the CPE Products endpoint
CANDIDATE_CAP = 2_000       # same cap as NVDClient pagination

FetchPage = Callable[[int, int], dict]


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


# -------------------------------------------------------------- lookup

@dataclass
class LocalDictionary:
    """In-memory (vendor, product) index over a snapshot file."""

    by_pair: dict[tuple[str, str], list[DictEntry]] = field(
        default_factory=dict)
    by_vendor: dict[str, list[DictEntry]] = field(default_factory=dict)
    size: int = 0
    hits: int = 0
    misses: int = 0

    @classmethod
    def load(cls, path: Path | str = DEFAULT_SNAPSHOT) -> "LocalDictionary":
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        d = cls()
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
                d.by_pair.setdefault((vendor, product), []).append(entry)
                d.by_vendor.setdefault(vendor, []).append(entry)
                d.size += 1
        return d

    def candidates_for(self, vendor: str | None,
                       product: str | None) -> list[DictEntry]:
        """Same contract as NVDClient.candidates_for, minus keyword."""
        results: list[DictEntry] = []
        if vendor and product:
            results = self.by_pair.get(
                (bind_component(vendor), bind_component(product)), [])
        if not results and vendor:
            results = self.by_vendor.get(bind_component(vendor), [])
        if results:
            self.hits += 1
        else:
            self.misses += 1
        return results[:CANDIDATE_CAP]


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

    def keyword(self, keywords: str) -> list[DictEntry]:
        return self.client.keyword(keywords)
