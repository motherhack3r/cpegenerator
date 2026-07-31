"""Tests for the inventory collector and the CVE applicability check."""

import csv
import json

from cpegen.goldset import load_gold
from cpegen.inventory import (InventoryItem, curate, is_noise,
                              parse_dpkg_output, parse_rpm_output, write_csv)
from cpegen.vulns import CVEClient, check_results, parse_cve_item
from cpegen.vulns import write_csv as write_vulns_csv


# --------------------------------------------------------------- inventory

def test_parse_dpkg_output():
    text = "openssl:amd64\t3.0.2-0ubuntu1\tUbuntu Developers\ncurl\t7.81.0\t\n"
    items = parse_dpkg_output(text)
    assert items[0].name == "openssl"  # architecture suffix stripped
    assert items[0].version == "3.0.2-0ubuntu1"
    assert items[1].name == "curl"
    assert items[0].source == "dpkg"


def test_parse_rpm_output():
    text = "httpd\t2.4.57-1.el9\tRed Hat, Inc.\n"
    items = parse_rpm_output(text)
    assert items[0].name == "httpd"
    assert items[0].vendor == "Red Hat, Inc."
    assert items[0].source == "rpm"


def test_noise_detection():
    assert is_noise(InventoryItem("Security Update for Microsoft Office (KB2837593)"))
    assert is_noise(InventoryItem("Update for Windows (KB4023057)"))
    assert is_noise(InventoryItem("Microsoft Office Language Pack 2013"))
    assert not is_noise(InventoryItem("Mozilla Firefox 115.0"))
    assert not is_noise(InventoryItem("7-Zip 22.01 (x64)"))


def test_curate_dedup_and_noise():
    items = [
        InventoryItem("Firefox", "115.0", "Mozilla"),
        InventoryItem("firefox", "115.0", "Mozilla"),      # dup (case)
        InventoryItem("", "1.0", "Ghost"),                  # empty name
        InventoryItem("Hotfix for Windows (KB123456)"),     # noise
        InventoryItem("VLC media player", "3.0.18"),
    ]
    out = curate(items)
    names = [i.name for i in out]
    assert names == ["Firefox", "VLC media player"]


def test_curate_keep_noise():
    items = [InventoryItem("Hotfix for Windows (KB123456)")]
    assert len(curate(items, keep_noise=True)) == 1


def test_title_composition():
    assert InventoryItem("Mozilla Firefox", "115.0").title == "Mozilla Firefox 115.0"
    # version already embedded in the name: don't repeat it
    assert InventoryItem("7-Zip 22.01 (x64)", "22.01").title == "7-Zip 22.01 (x64)"


def test_inventory_csv_feeds_the_pipeline(tmp_path):
    """The inventory CSV must be loadable by the run loader (header skipped)."""
    out = tmp_path / "inventory.csv"
    write_csv([InventoryItem("Mozilla Firefox", "115.0", "Mozilla", "hklm64")], out)
    records = load_gold(out)
    assert len(records) == 1
    assert records[0].title == "Mozilla Firefox 115.0"
    assert records[0].vendor is None  # no annotations: nothing to evaluate


# ------------------------------------------------------------------- vulns

CVE_ITEM = {
    "id": "CVE-2023-0001",
    "descriptions": [{"lang": "en", "value": "Buffer overflow in femanager."}],
    "metrics": {"cvssMetricV31": [{"cvssData": {
        "baseScore": 9.8, "baseSeverity": "CRITICAL"}}]},
}


def test_parse_cve_item():
    v = parse_cve_item(CVE_ITEM)
    assert v.cve_id == "CVE-2023-0001"
    assert v.score == 9.8
    assert v.severity == "CRITICAL"
    assert "femanager" in v.description


def test_parse_cve_item_no_metrics():
    v = parse_cve_item({"id": "CVE-2023-0002"})
    assert v.score is None
    assert v.severity == ""


def make_results_csv(tmp_path, rows):
    path = tmp_path / "results.csv"
    fieldnames = ["title", "cpe", "rule", "matched_cpe"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_check_results_only_eligible_rules(tmp_path):
    cpe = "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"
    results = make_results_csv(tmp_path, [
        {"title": "a", "cpe": cpe, "rule": "M1", "matched_cpe": cpe},
        {"title": "b", "cpe": cpe, "rule": "M3", "matched_cpe": ""},
        {"title": "c", "cpe": "", "rule": "M1", "matched_cpe": ""},
    ])
    client = CVEClient(cache_path=tmp_path / "cve.json", offline=True)
    # seed the cache so the M1 row resolves offline
    query = json.dumps({"cpeName": cpe, "isVulnerable": True}, sort_keys=True)
    client._cache_put(query, [CVE_ITEM])

    vrows = check_results(results, client)
    assert len(vrows) == 1  # only the M1 row with a CPE
    assert vrows[0].vulnerable
    assert vrows[0].cves[0].cve_id == "CVE-2023-0001"


def test_check_results_offline_miss_flagged(tmp_path):
    cpe = "cpe:2.3:a:google:protobuf:3.6.1:*:*:*:*:*:*:*"
    results = make_results_csv(tmp_path, [
        {"title": "a", "cpe": cpe, "rule": "M1", "matched_cpe": cpe},
    ])
    client = CVEClient(cache_path=tmp_path / "cve.json", offline=True)
    vrows = check_results(results, client)
    assert vrows[0].error == "offline cache miss"
    assert not vrows[0].vulnerable


def test_check_results_prefers_dictionary_cpe(tmp_path):
    gen = "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:*:*:*"
    dic = "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"
    results = make_results_csv(tmp_path, [
        {"title": "a", "cpe": gen, "rule": "M1A", "matched_cpe": dic},
    ])
    client = CVEClient(cache_path=tmp_path / "cve.json", offline=True)
    query = json.dumps({"cpeName": dic, "isVulnerable": True}, sort_keys=True)
    client._cache_put(query, [])
    vrows = check_results(results, client)
    assert vrows[0].cpe == dic
    assert vrows[0].error == ""  # cache hit (empty list = no CVEs)
    assert not vrows[0].vulnerable


def test_vulns_csv_output(tmp_path):
    cpe = "cpe:2.3:a:in2code:femanager:5.5.1:*:*:*:*:typo3:*:*"
    results = make_results_csv(tmp_path, [
        {"title": "a", "cpe": cpe, "rule": "M1", "matched_cpe": cpe},
    ])
    client = CVEClient(cache_path=tmp_path / "cve.json", offline=True)
    query = json.dumps({"cpeName": cpe, "isVulnerable": True}, sort_keys=True)
    client._cache_put(query, [CVE_ITEM])
    vrows = check_results(results, client)
    out = tmp_path / "vulns.csv"
    write_vulns_csv(vrows, out)
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert rows[0]["n_cves"] == "1"
    assert rows[0]["max_score"] == "9.8"
    assert "CVE-2023-0001" in rows[0]["cve_ids"]
