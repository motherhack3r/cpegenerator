"""NVD CPE API 2.0 client with persistent local cache and rate throttling.

- Endpoint: https://services.nvd.nist.gov/rest/json/cpes/2.0
- Without NVD_API_KEY: 5 requests / 30 s (public limit) -> 6.5 s spacing.
- With key: 50 requests / 30 s -> 0.7 s spacing.
- Cache: a plain JSON file at data/cache/nvd_cache.json keyed by the
  exact query; hits never touch the network, so re-runs are free and the
  pipeline can run fully offline once the cache is warm. (JSON instead of
  sqlite: works on any filesystem, including network mounts without
  locking support, and stays diffable.)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .wfn import bind_component

API_URL = "https://services.nvd.nist.gov/rest/json/cpes/2.0"
DEFAULT_CACHE = Path("data/cache/nvd_cache.json")


@dataclass
class DictEntry:
    """One CPE dictionary entry relevant to matching."""

    cpe_name: str  # formatted string
    cpe_name_id: str
    title: str
    deprecated: bool


class NVDClient:
    """Thin, cached, throttled client for the CPE Products API."""

    def __init__(self, cache_path: Path | str = DEFAULT_CACHE,
                 api_key: str | None = None, offline: bool = False):
        self.api_key = api_key or os.environ.get("NVD_API_KEY")
        self.offline = offline
        self.min_interval = 0.7 if self.api_key else 6.5
        self._last_request = 0.0
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            self._cache: dict[str, list[dict]] = json.loads(
                self.cache_path.read_text(encoding="utf-8")
            )
        else:
            self._cache = {}

    # ------------------------------------------------------------ cache

    def _cache_get(self, query: str) -> list[dict] | None:
        return self._cache.get(query)

    def _cache_put(self, query: str, products: list[dict]) -> None:
        self._cache[query] = products
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cache), encoding="utf-8")
        tmp.replace(self.cache_path)

    # -------------------------------------------------------------- api

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _request(self, params: dict) -> list[dict]:
        query = json.dumps(params, sort_keys=True)
        cached = self._cache_get(query)
        if cached is not None:
            return cached
        if self.offline:
            return []  # cache miss in offline mode: no candidates

        headers = {"apiKey": self.api_key} if self.api_key else {}
        products: list[dict] = []
        start = 0
        while True:
            self._throttle()
            resp = requests.get(
                API_URL,
                params={**params, "startIndex": start, "resultsPerPage": 500},
                headers=headers,
                timeout=60,
            )
            if resp.status_code in (403, 429):  # rate limited: back off once
                time.sleep(30)
                resp = requests.get(
                    API_URL,
                    params={**params, "startIndex": start, "resultsPerPage": 500},
                    headers=headers,
                    timeout=60,
                )
            if resp.status_code == 404:
                # NVD replies 404 for match strings it cannot parse or
                # resolve: treat as "no dictionary entries", cache it and
                # never kill a long run over one odd title.
                products = []
                break
            resp.raise_for_status()
            data = resp.json()
            products.extend(p["cpe"] for p in data.get("products", []))
            total = data.get("totalResults", 0)
            start += data.get("resultsPerPage", 500)
            if start >= total or len(products) >= 2000:
                break
        self._cache_put(query, products)
        return products

    # ---------------------------------------------------------- lookups

    @staticmethod
    def _to_entries(products: list[dict]) -> list[DictEntry]:
        entries = []
        for p in products:
            titles = p.get("titles", [])
            title = next(
                (t["title"] for t in titles if t.get("lang") == "en"),
                titles[0]["title"] if titles else "",
            )
            entries.append(
                DictEntry(
                    cpe_name=p.get("cpeName", ""),
                    cpe_name_id=p.get("cpeNameId", ""),
                    title=title,
                    deprecated=bool(p.get("deprecated", False)),
                )
            )
        return entries

    def match_string(self, cpe_match_string: str) -> list[DictEntry]:
        """Dictionary entries matching a (possibly partial) CPE name."""
        return self._to_entries(self._request({"cpeMatchString": cpe_match_string}))

    def keyword(self, keywords: str) -> list[DictEntry]:
        """Dictionary entries whose titles/refs contain all keywords."""
        return self._to_entries(self._request({"keywordSearch": keywords}))

    def candidates_for(self, vendor: str | None, product: str | None) -> list[DictEntry]:
        """Candidate entries for matching: vendor:product prefix search,
        falling back to keyword search when the prefix yields nothing."""
        results: list[DictEntry] = []
        # bind_component escapes specials (+, ~, ...): the API rejects
        # match strings that break the CPE grammar (e.g. visual_c++_...)
        if vendor and product:
            results = self.match_string(
                f"cpe:2.3:*:{bind_component(vendor)}:{bind_component(product)}")
        if not results and vendor:
            results = self.match_string(f"cpe:2.3:*:{bind_component(vendor)}")
        if not results and product:
            kw = " ".join(w for w in (vendor, product) if w)
            results = self.keyword(kw.replace("_", " "))
        return results
