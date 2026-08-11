"""Phase-4 agent: an LLM tool-use loop over the deterministic tools.

The agent receives one software title (plus the fast-pass result when
escalating), reasons with native tool calling, and terminates by calling
``submit``. The loop enforces the project invariant: whatever the agent
submits is re-validated by the ABNF validator and re-classified by the
M1-M3 matcher in code. The LLM proposes; the code validates and decides.

Provider-neutral message format used internally:
    {"role": "user"|"assistant"|"tool", "content": str,
     "tool_calls": [{"id", "name", "args"}],   # assistant only
     "tool_call_id": str}                       # tool results only
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import requests

from .extractor import DEFAULT_ANTHROPIC_MODEL, DEFAULT_OPENAI_MODEL, MockProvider
from .matcher import classify
from .tools import TOOL_SCHEMAS, ToolBox, build_wfn_from_args
from .validator import validate_formatted_string

MAX_TURNS = 8

AGENT_SYSTEM_PROMPT = """\
You are a CPE 2.3 generation agent for corporate software inventory.
Given ONE free-text software title, produce the entities of the correct
CPE name, grounded in the official NVD dictionary.

Method:
1. Extract candidate vendor/product/version (+update, target_sw) from the
   title. Suffixes like beta/rc/build belong in "update", not "version".
2. Use search_dictionary to check how the vendor and product are actually
   spelled in the dictionary (commercial names often differ: "Zoho Corp"
   is "zohocorp"). Prefer dictionary spellings when they clearly refer to
   the same software.
3. Use bind_and_validate to see the exact CPE your entities produce and
   fix any grammar errors it reports.
4. Use classify_match to check the match quality; if it returns M2/M2B/M3/M4,
   consider alternative vendor/product spellings and try again (you have a
   limited budget of turns, spend it wisely).
5. Call submit with your best entities and an honest confidence in [0,1].

Rules:
- Tools are the source of truth; never claim dictionary contents you have
  not observed in a tool result.
- Do not invent vendors or products that are neither in the title nor in
  the dictionary results.
- If the title is not identifiable software (driver bundle, KB update,
  hardware noise), submit with low confidence and say so in the note.
- Always call submit before running out of turns; never answer in plain
  text only.
"""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class AgentResult:
    """Outcome of one agent run over one title."""

    title: str
    vendor: str = ""
    product: str = ""
    version: str = ""
    update: str = ""
    target_sw: str = ""
    confidence: float = 0.0
    cpe: str = ""
    valid: bool = False
    validation_errors: str = ""
    rule: str = ""
    rule_name: str = ""
    match_similarity: float = 0.0
    matched_cpe: str = ""
    turns: int = 0
    note: str = ""
    error: str = ""


# --------------------------------------------------------------- providers


class AnthropicToolProvider:
    """Native tool use via the Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("CPEGEN_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

    def chat(self, messages: list[dict]) -> ModelReply:
        api_messages = []
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                content = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    content.append({"type": "tool_use", "id": tc["id"],
                                    "name": tc["name"], "input": tc["args"]})
                api_messages.append({"role": "assistant", "content": content})
            elif m["role"] == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result",
                                 "tool_use_id": m["tool_call_id"],
                                 "content": m["content"]}],
                })
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": self.model,
                "max_tokens": 1024,
                "system": AGENT_SYSTEM_PROMPT,
                "tools": TOOL_SCHEMAS,
                "messages": api_messages,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = ModelReply()
        for block in data.get("content", []):
            if block["type"] == "text":
                reply.text += block["text"]
            elif block["type"] == "tool_use":
                reply.tool_calls.append(
                    ToolCall(block["id"], block["name"], block["input"] or {}))
        return reply


class OpenAIToolProvider:
    """Function calling via any OpenAI-compatible chat endpoint."""

    name = "openai"

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None):
        self.model = model or os.environ.get("CPEGEN_MODEL", DEFAULT_OPENAI_MODEL)
        self.base_url = (base_url or os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "none")

    def chat(self, messages: list[dict]) -> ModelReply:
        api_messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                api_messages.append({
                    "role": "assistant",
                    "content": m.get("content") or None,
                    "tool_calls": [{
                        "id": tc["id"], "type": "function",
                        "function": {"name": tc["name"],
                                     "arguments": json.dumps(tc["args"])},
                    } for tc in m["tool_calls"]],
                })
            elif m["role"] == "tool":
                api_messages.append({"role": "tool",
                                     "tool_call_id": m["tool_call_id"],
                                     "content": m["content"]})
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        tools = [{"type": "function",
                  "function": {"name": t["name"], "description": t["description"],
                               "parameters": t["input_schema"]}}
                 for t in TOOL_SCHEMAS]
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "content-type": "application/json"},
            json={"model": self.model, "messages": api_messages, "tools": tools},
            timeout=180,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        reply = ModelReply(text=msg.get("content") or "")
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            reply.tool_calls.append(ToolCall(tc["id"], tc["function"]["name"], args))
        return reply


class MockAgentProvider:
    """Deterministic scripted agent for offline tests and dry runs.

    Turn 1: extract entities heuristically, bind_and_validate + search.
    Turn 2: classify_match.
    Turn 3: submit. Exercises the whole loop without any network.
    """

    name = "mock"

    def __init__(self, model: str | None = None):
        self._extractor = MockProvider()

    def chat(self, messages: list[dict]) -> ModelReply:
        title = next(m["content"] for m in messages if m["role"] == "user")
        # first line of the user message carries the title
        title = title.splitlines()[0].removeprefix("Title: ").strip()
        ext = json.loads(self._extractor.complete(title))
        args = {k: v for k, v in ext.items()
                if k in ("vendor", "product", "version", "update", "target_sw")
                and v}
        n_assistant = sum(1 for m in messages if m["role"] == "assistant")
        if n_assistant == 0:
            return ModelReply(tool_calls=[
                ToolCall("t1", "bind_and_validate", dict(args)),
                ToolCall("t2", "search_dictionary",
                         {k: args[k] for k in ("vendor", "product") if k in args}),
            ])
        if n_assistant == 1:
            return ModelReply(tool_calls=[
                ToolCall("t3", "classify_match", {**args, "confidence": 0.85})])
        return ModelReply(tool_calls=[
            ToolCall("t4", "submit",
                     {**args, "confidence": 0.85, "note": "mock scripted run"})])


AGENT_PROVIDERS = {
    "anthropic": AnthropicToolProvider,
    "openai": OpenAIToolProvider,
    "mock": MockAgentProvider,
}


def get_agent_provider(name: str | None = None, model: str | None = None):
    name = (name or os.environ.get("CPEGEN_PROVIDER", "anthropic")).lower()
    if name not in AGENT_PROVIDERS:
        raise ValueError(f"unknown agent provider {name!r}; "
                         f"choose from {sorted(AGENT_PROVIDERS)}")
    return AGENT_PROVIDERS[name](model=model)


# -------------------------------------------------------------------- loop


def _finalize(result: AgentResult, args: dict, toolbox: ToolBox) -> AgentResult:
    """Deterministic gate on the submitted entities: validate + classify."""
    result.vendor = str(args.get("vendor") or "")
    result.product = str(args.get("product") or "")
    result.version = str(args.get("version") or "")
    result.update = str(args.get("update") or "")
    result.target_sw = str(args.get("target_sw") or "")
    result.note = str(args.get("note") or "")
    try:
        result.confidence = max(0.0, min(1.0, float(args.get("confidence", 0.0))))
    except (TypeError, ValueError):
        result.confidence = 0.0

    if not result.vendor and not result.product:
        result.error = "agent submitted no vendor/product"
        return result

    wfn = build_wfn_from_args(args)
    cpe = wfn.bind()
    validation = validate_formatted_string(cpe)
    result.valid = validation.ok
    if not validation.ok:
        result.validation_errors = "; ".join(validation.errors)
        return result  # invalid CPE never leaves the pipeline
    result.cpe = cpe

    vendor = wfn.vendor if isinstance(wfn.vendor, str) else None
    product = wfn.product if isinstance(wfn.product, str) else None
    try:
        candidates = toolbox.nvd.candidates_for(vendor, product)
    except Exception as exc:  # degrade to no candidates, keep the run alive
        candidates = []
        result.note = (result.note + " | " if result.note else "") +             f"nvd lookup failed: {exc}"
    match = classify(wfn, candidates)
    result.rule = match.rule
    result.rule_name = match.rule_name
    result.match_similarity = round(match.similarity, 4)
    result.matched_cpe = match.matched_cpe or ""
    return result


def run_agent(title: str, provider, toolbox: ToolBox,
              fast_pass_context: str = "", max_turns: int = MAX_TURNS) -> AgentResult:
    """Run the tool-use loop for one title until submit or budget exhausted."""
    result = AgentResult(title=title)
    user = f"Title: {title}"
    if fast_pass_context:
        user += f"\n\nFast-pass result (single-shot extraction): {fast_pass_context}"
    user += f"\n\nYou have {max_turns} turns. Call submit with your final answer."
    messages: list[dict] = [{"role": "user", "content": user}]

    for turn in range(1, max_turns + 1):
        result.turns = turn
        try:
            reply = provider.chat(messages)
        except requests.RequestException as exc:
            result.error = f"provider error: {exc}"
            return result

        messages.append({
            "role": "assistant",
            "content": reply.text,
            "tool_calls": [{"id": tc.id, "name": tc.name, "args": tc.args}
                           for tc in reply.tool_calls],
        })

        if not reply.tool_calls:
            # plain text without submit: nudge once, then give up
            if turn >= max_turns:
                break
            messages.append({"role": "user", "content":
                             "You must use the tools and finish with submit."})
            continue

        for tc in reply.tool_calls:
            if tc.name == "submit":
                return _finalize(result, tc.args, toolbox)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": toolbox.execute(tc.name, tc.args),
            })

    result.error = f"agent did not submit within {max_turns} turns"
    return result
