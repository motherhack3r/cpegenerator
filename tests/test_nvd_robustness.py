"""Tests for NVD client robustness: match-string escaping and 404 handling.

Regressions found on the first live run against the NVD API (Windows
inventory, 2026-07-14): unescaped '+' in cpeMatchString made the API
return 404, and the HTTPError killed the run at title 33/82.
"""

import json

import cpegen.nvd as nvd_module
from cpegen.extractor import MockProvider
from cpegen.nvd import NVDClient
from cpegen.pipeline import process_title


class DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"totalResults": 0, "resultsPerPage": 500,
                                    "products": []}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")


def test_match_string_is_escaped(tmp_path, monkeypatch):
    """'visual_c++...' must reach the API as 'visual_c\\+\\+...'."""
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return DummyResponse()

    monkeypatch.setattr(nvd_module.requests, "get", fake_get)
    client = NVDClient(cache_path=tmp_path / "c.json")
    client.min_interval = 0  # no throttling in tests
    client.candidates_for("microsoft", "visual_c++_2010_redistributable")
    # first call of the fallback chain is the vendor:product match string
    assert calls[0]["cpeMatchString"] == \
        "cpe:2.3:*:microsoft:visual_c\\+\\+_2010_redistributable"


def test_404_treated_as_no_results_and_cached(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return DummyResponse(status_code=404)

    monkeypatch.setattr(nvd_module.requests, "get", fake_get)
    client = NVDClient(cache_path=tmp_path / "c.json")
    client.min_interval = 0
    assert client.match_string("cpe:2.3:*:acme:whatever") == []
    # second call must hit the cache, not the API
    assert client.match_string("cpe:2.3:*:acme:whatever") == []
    assert calls["n"] == 1


def test_lookup_error_does_not_kill_the_run(tmp_path, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return DummyResponse(status_code=500)

    monkeypatch.setattr(nvd_module.requests, "get", fake_get)
    client = NVDClient(cache_path=tmp_path / "c.json")
    client.min_interval = 0
    row = process_title("in2code femanager 5.5.1 for typo3",
                        MockProvider(), client)
    assert row.valid  # CPE still produced and validated
    assert row.rule == "M4"  # classified with no candidates (v2 no-signal bucket)
    assert "nvd lookup failed" in row.note
