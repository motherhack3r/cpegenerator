"""LLM few-shot entity extraction: title -> vendor/product/version/target_sw.

The LLM only *proposes* raw entities as JSON. It never emits a CPE
string: the WFN is built and validated deterministically downstream
(see docs/lessons-learned.md - the 2023 LSTM lesson).

Providers:
- ``anthropic``  - Claude via the Anthropic Messages API (ANTHROPIC_API_KEY)
- ``openai``     - any OpenAI-compatible endpoint: OpenAI, Ollama,
                   LM Studio, vLLM... (OPENAI_BASE_URL, OPENAI_API_KEY)
- ``mock``       - deterministic offline heuristic, for tests and dry runs
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import requests

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are an expert in software inventory and the NIST CPE 2.3 dictionary.
Given ONE free-text software title, extract the entities needed to build
a CPE name. Respond with a single JSON object, nothing else:

{"vendor": string|null, "product": string|null, "version": string|null,
 "update": string|null, "target_sw": string|null, "confidence": number}

Rules:
- vendor: the organization/author as it would appear in the CPE dictionary
  (e.g. "Zoho Corp" -> "zohocorp" if you know the dictionary form; otherwise
  the literal vendor token from the title, lowercased).
- product: the product name only, without vendor, version or platform.
- version: the version string only (digits/dots/identifiers). Suffixes like
  "beta", "rc2", "build 125482" go to "update", not "version".
- target_sw: the software ecosystem/platform if implied ("for typo3",
  "for node.js", "plugin for wordpress" -> "typo3", "node.js", "wordpress").
- Use null when an entity is absent. Do not invent values.
- confidence: your overall confidence in [0,1].
- Copy tokens from the title (lowercase); do not translate or expand.

Examples:
Title: "in2code femanager 5.5.1 for typo3"
{"vendor": "in2code", "product": "femanager", "version": "5.5.1", "update": null, "target_sw": "typo3", "confidence": 0.97}

Title: "gecad technologies axigen mail server 3.0 beta"
{"vendor": "gecad", "product": "axigen mail server", "version": "3.0", "update": "beta", "target_sw": null, "confidence": 0.9}

Title: "Microsoft Visual C++ 2013 Redistributable (x64) - 12.0.30501"
{"vendor": "microsoft", "product": "visual c++ 2013 redistributable", "version": "12.0.30501", "update": null, "target_sw": null, "confidence": 0.85}

Title: "riot.js riot-compiler 3.1.2 for node.js"
{"vendor": "riot.js", "product": "riot-compiler", "version": "3.1.2", "update": null, "target_sw": "node.js", "confidence": 0.95}
"""


@dataclass
class Extraction:
    """Raw entities proposed by the LLM for one title."""

    title: str
    vendor: str | None = None
    product: str | None = None
    version: str | None = None
    update: str | None = None
    target_sw: str | None = None
    confidence: float = 0.0
    error: str | None = None


def _parse_response(title: str, text: str) -> Extraction:
    """Parse the model's JSON strictly; salvage a JSON object if wrapped."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return Extraction(title=title, error=f"no JSON in response: {text[:120]!r}")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return Extraction(title=title, error=f"bad JSON: {exc}")

    def clean(key: str) -> str | None:
        val = data.get(key)
        if val is None or not isinstance(val, str) or not val.strip():
            return None
        return val.strip().lower()

    conf = data.get("confidence", 0.0)
    try:
        conf = max(0.0, min(1.0, float(conf)))
    except (TypeError, ValueError):
        conf = 0.0
    return Extraction(
        title=title,
        vendor=clean("vendor"),
        product=clean("product"),
        version=clean("version"),
        update=clean("update"),
        target_sw=clean("target_sw"),
        confidence=conf,
    )


class AnthropicProvider:
    """Claude via the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("CPEGEN_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

    def complete(self, title: str) -> str:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": f"Title: {title!r}"}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


class OpenAICompatProvider:
    """Any OpenAI-compatible chat endpoint (OpenAI, Ollama, LM Studio, vLLM)."""

    name = "openai"

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None):
        self.model = model or os.environ.get("CPEGEN_MODEL", DEFAULT_OPENAI_MODEL)
        self.base_url = (base_url or os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "none")

    def complete(self, title: str) -> str:
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Title: {title!r}"},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class MockProvider:
    """Deterministic offline extractor for tests and plumbing dry runs.

    Simple positional heuristic over the gold-set title shape
    (vendor product... version [suffix] [for target]); NOT a baseline,
    only proves the pipeline end-to-end without network access.
    """

    name = "mock"

    _VERSION_RE = re.compile(r"^v?\d+(\.\d+)*([a-z0-9._-]*)$")
    _UPDATE_WORDS = {"beta", "alpha", "rc", "release", "build", "sp", "patch"}

    def complete(self, title: str) -> str:
        text = title.strip().lower()
        target_sw = None
        m = re.search(r"\bfor ([a-z0-9._+-]+)\s*$", text)
        if m:
            target_sw = m.group(1)
            text = text[: m.start()].strip()

        tokens = text.split()
        version = None
        update = None
        ver_idx = None
        for i, tok in enumerate(tokens):
            if self._VERSION_RE.match(tok) and any(c.isdigit() for c in tok):
                version = tok
                ver_idx = i
                break
        if ver_idx is not None:
            rest = tokens[ver_idx + 1 :]
            if rest and rest[0].rstrip("0123456789") in self._UPDATE_WORDS:
                update = " ".join(rest[:1])
            tokens = tokens[:ver_idx]

        vendor = tokens[0] if tokens else None
        product = " ".join(tokens[1:]) if len(tokens) > 1 else None
        return json.dumps(
            {
                "vendor": vendor,
                "product": product,
                "version": version,
                "update": update,
                "target_sw": target_sw,
                "confidence": 0.5,
            }
        )


class ReplayProvider:
    """Replays pre-computed extractions from a JSON file: {title: entities}.

    Enables reproducible benchmark reruns and offline validation runs
    (e.g. extractions produced once by an expensive model, or by a human).
    Path comes from --model, or the CPEGEN_REPLAY_FILE env variable.
    """

    name = "replay"

    def __init__(self, model: str | None = None):
        from pathlib import Path
        path = model or os.environ.get("CPEGEN_REPLAY_FILE", "")
        if not path:
            raise RuntimeError(
                "replay provider needs a JSON path (--model or CPEGEN_REPLAY_FILE)")
        self.path = Path(path)
        self._data: dict = json.loads(self.path.read_text(encoding="utf-8"))

    def complete(self, title: str) -> str:
        entry = self._data.get(title)
        if entry is None:
            return "{}"  # -> extraction error: title absent from replay file
        return json.dumps(entry)


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAICompatProvider,
    "mock": MockProvider,
    "replay": ReplayProvider,
}


def get_provider(name: str | None = None, model: str | None = None):
    """Instantiate a provider by name (or CPEGEN_PROVIDER, default anthropic)."""
    name = (name or os.environ.get("CPEGEN_PROVIDER", "anthropic")).lower()
    if name not in PROVIDERS:
        raise ValueError(f"unknown provider {name!r}; choose from {sorted(PROVIDERS)}")
    if name == "mock":
        return MockProvider()
    return PROVIDERS[name](model=model)


def extract(provider, title: str, retries: int = 2) -> Extraction:
    """Run one extraction with basic retry on transport errors."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            text = provider.complete(title)
            return _parse_response(title, text)
        except (requests.RequestException, KeyError, IndexError) as exc:
            last_err = str(exc)
            time.sleep(min(2**attempt, 8))
    return Extraction(title=title, error=f"provider failed: {last_err}")
