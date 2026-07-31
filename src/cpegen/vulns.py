"""CVE applicability check: the `cpegen vulns` subcommand.

Python port of the original R prototype (`mitre` cpe branch,
`inst/scripts/is_vulnerable.R`). The R code flattened each CVE's
vulnerable-configuration tree (AND/OR cpe_match nodes) and evaluated the
versionStart/EndIncluding/Excluding ranges locally (`cpelite_check_vers`).
The NVD CVE API 2.0 now does all of that server-side: querying
`/rest/json/cves/2.0?cpeName=<cpe>&isVulnerable` returns exactly the CVEs
whose vulnerable configurations apply to that CPE name, version ranges
included.

Scope: this consumes the *output* of the generation pipeline
(results.csv). Only rows whose CPE passed the ABNF validator are ever
queried; by default only high-confidence dictionary matches (M1/M1A),
because applicability of a CPE that is not in the dictionary is
meaningless. Same JSON cache + throttling approach as the CPE client.
"""

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .matcher import HIGH_CONFIDENCE
from .validator import validate_formatted_string

CVE_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
DEFAULT_CACHE = Path("data/cache/cve_cache.json")
DEFAULT_RULES = ("M1", "M1A")  # dictionary-confirmed CPEs only


@dataclass
class Vulnerability:
    cve_id: str
    severity: str = ""
    score: float | None = None
    description: str = ""


@dataclass
class VulnRow:
    title: str
    cpe: str
    rule: str
    vulnerable: bool = False
    cves: list[Vulnerability] = field(default_factory=list)
    error: str = ""


class CVEClient:
    """Cached, throttled client for the NVD CVE API 2.0."""

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
                self.cache_path.read_text(encoding="utf-8"))
        else:
            self._cache = {}

    def _cache_put(self, query: str, payload: list[dict]) -> None:
        self._cache[query] = payload
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cache), encoding="utf-8")
        tmp.replace(self.cache_path)

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def vulnerabilities_for(self, cpe_name: str) -> list[dict] | None:
        """Raw CVE items applicable to a CPE name (None = offline miss)."""
        query = json.dumps({"cpeName": cpe_name, "isVulnerable": True},
                           sort_keys=True)
        if query in self._cache:
            return self._cache[query]
        if self.offline:
            return None

        headers = {"apiKey": self.api_key} if self.api_key else {}
        items: list[dict] = []
        start = 0
        while True:
            self._throttle()
            resp = requests.get(
                CVE_API_URL,
                params={"cpeName": cpe_name, "isVulnerable": "",
                        "startIndex": start, "resultsPerPage": 200},
                headers=headers, timeout=60)
            if resp.status_code in (403, 429):
                time.sleep(30)
                resp = requests.get(
                    CVE_API_URL,
                    params={"cpeName": cpe_name, "isVulnerable": "",
                            "startIndex": start, "resultsPerPage": 200},
                    headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            items.extend(v["cve"] for v in data.get("vulnerabilities", []))
            total = data.get("totalResults", 0)
            start += data.get("resultsPerPage", 200)
            if start >= total or len(items) >= 2000:
                break
        self._cache_put(query, items)
        return items


def parse_cve_item(item: dict) -> Vulnerability:
    """Extract id, best CVSS score/severity and short description."""
    cve_id = item.get("id", "")
    severity, score = "", None
    metrics = item.get("metrics", {})
    # prefer the newest CVSS version available
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if entries:
            data = entries[0].get("cvssData", {})
            score = data.get("baseScore")
            severity = (data.get("baseSeverity")
                        or entries[0].get("baseSeverity", ""))
            break
    description = next(
        (d["value"] for d in item.get("descriptions", [])
         if d.get("lang") == "en"), "")
    return Vulnerability(cve_id=cve_id, severity=str(severity or ""),
                         score=score, description=description[:200])


def check_results(results_path: Path, client: CVEClient,
                  rules: tuple[str, ...] = DEFAULT_RULES,
                  progress=None) -> list[VulnRow]:
    """Check every eligible row of a pipeline results.csv against the NVD."""
    with open(results_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    eligible = [r for r in rows
                if r.get("cpe") and r.get("rule") in rules
                and validate_formatted_string(r["cpe"]).ok]

    out: list[VulnRow] = []
    for i, r in enumerate(eligible):
        # Prefer the dictionary CPE when the generated one merely matched it.
        cpe = r.get("matched_cpe") or r["cpe"]
        vrow = VulnRow(title=r["title"], cpe=cpe, rule=r["rule"])
        try:
            items = client.vulnerabilities_for(cpe)
        except requests.RequestException as exc:
            vrow.error = f"api error: {exc}"
            items = None
        if items is None and not vrow.error:
            vrow.error = "offline cache miss"
        elif items is not None:
            vrow.cves = [parse_cve_item(it) for it in items]
            vrow.vulnerable = bool(vrow.cves)
        out.append(vrow)
        if progress:
            progress(i + 1, len(eligible))
    return out


def write_csv(vrows: list[VulnRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["title", "cpe", "rule", "vulnerable", "n_cves",
                         "max_score", "cve_ids", "error"])
        for v in vrows:
            scores = [c.score for c in v.cves if c.score is not None]
            writer.writerow([
                v.title, v.cpe, v.rule, v.vulnerable, len(v.cves),
                max(scores) if scores else "",
                ";".join(c.cve_id for c in v.cves), v.error,
            ])
