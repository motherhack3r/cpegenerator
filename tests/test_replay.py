"""Tests for the replay provider (pre-computed extractions)."""

import json

import pytest

from cpegen.extractor import ReplayProvider, extract, get_provider


def make_replay_file(tmp_path):
    path = tmp_path / "extractions.json"
    path.write_text(json.dumps({
        "Git 2.54.0": {"vendor": "git-scm", "product": "git",
                       "version": "2.54.0", "update": None,
                       "target_sw": None, "confidence": 0.9},
    }), encoding="utf-8")
    return path


def test_replay_known_title(tmp_path):
    provider = ReplayProvider(model=str(make_replay_file(tmp_path)))
    ext = extract(provider, "Git 2.54.0")
    assert ext.vendor == "git-scm"
    assert ext.version == "2.54.0"
    assert ext.confidence == 0.9
    assert ext.error is None


def test_replay_unknown_title_yields_error_row(tmp_path):
    provider = ReplayProvider(model=str(make_replay_file(tmp_path)))
    ext = extract(provider, "Unknown Software 1.0")
    # empty JSON -> no vendor/product -> downstream flags the row
    assert ext.vendor is None and ext.product is None


def test_replay_requires_path(monkeypatch):
    monkeypatch.delenv("CPEGEN_REPLAY_FILE", raising=False)
    with pytest.raises(RuntimeError):
        ReplayProvider()


def test_replay_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CPEGEN_REPLAY_FILE", str(make_replay_file(tmp_path)))
    monkeypatch.setenv("CPEGEN_PROVIDER", "replay")
    provider = get_provider(None)
    assert provider.name == "replay"
    assert extract(provider, "Git 2.54.0").product == "git"
