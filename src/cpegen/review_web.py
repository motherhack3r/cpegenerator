"""WP3/Fase A — local web UI for annotation queues (``cpegen review``).

A zero-dependency (stdlib ``http.server``) localhost server that turns the
WP3 annotation queue CSVs into a visual, keyboard-friendly review flow.
The UI is ergonomics, never authority:

- it READS the queue CSV exactly as ``cpegen sample`` wrote it
  (:data:`cpegen.sampling.QUEUE_FIELDS`);
- it WRITES the same columns back (``annotated_title`` in the RASA-bracket
  format :func:`cpegen.goldset.parse_annotation` already parses, plus
  ``verdict``/``annotator``/``timestamp``/``notes``) — a reviewed queue is
  freezable with no format conversion, identical to hand-editing the CSV;
- every verdict is stamped with the reviewer identity (``--identity``,
  required — spec §6.4/N11) and a UTC timestamp;
- saves are incremental and atomic (temp file + ``os.replace``): closing
  the browser or killing the server never loses confirmed rows.

Phases (decision 2026-08-14): this annotation mode is Fase A; Fase B will
reuse the same module for the WP5 ``needs_review``/NIE flow; Fase C (the
multi-user community/client dictionary platform) is a separate
post-publication product for which A/B act as the validated prototype.

The server binds 127.0.0.1 only. No network is ever required: the HTML
asset is self-contained (web fonts degrade to system fallbacks offline).
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .sampling import QUEUE_FIELDS

UI_ASSET = Path(__file__).with_name("review_ui.html")

# Same shape goldset._ENTITY_RE accepts; kept local so review_web never
# imports a private name, and a test asserts the two stay in sync.
ENTITY_RE = re.compile(r"\[([^\]]+)\]\((cpe_vendor|cpe_product|cpe_version)\)")

VERDICTS = ("annotated", "not_software", "skipped")


class VerdictError(ValueError):
    """A verdict payload that must not be written to the queue."""


@dataclass
class ReviewState:
    """The queue rows plus the incremental-save bookkeeping."""

    queue_path: Path
    output_path: Path
    identity: str
    rows: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, queue_path: Path | str, identity: str,
             output_path: Path | str | None = None) -> "ReviewState":
        queue_path = Path(queue_path)
        output_path = Path(output_path) if output_path else queue_path
        if not identity or not identity.strip():
            raise VerdictError("identity is required (spec §6.4: every "
                               "human decision records who took it)")
        # Resume from the output file when it already carries verdicts.
        source = output_path if output_path.exists() else queue_path
        rows: list[dict] = []
        with open(source, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = [f for f in QUEUE_FIELDS if f not in (reader.fieldnames or [])]
            if missing:
                raise VerdictError(
                    f"not an annotation queue (missing columns: {missing})")
            for row in reader:
                rows.append({f: (row.get(f) or "") for f in QUEUE_FIELDS})
        if not rows:
            raise VerdictError(f"empty queue: {source}")
        return cls(queue_path=queue_path, output_path=output_path,
                   identity=identity.strip(), rows=rows)

    # -- verdict handling -------------------------------------------------

    def apply_verdict(self, index: int, verdict: str, annotated_title: str,
                      notes: str = "") -> dict:
        if not 0 <= index < len(self.rows):
            raise VerdictError(f"row index out of range: {index}")
        if verdict not in VERDICTS:
            raise VerdictError(f"unknown verdict {verdict!r}; "
                               f"expected one of {VERDICTS}")
        annotated_title = (annotated_title or "").strip()
        if verdict == "annotated":
            entities = dict()
            for value, label in ENTITY_RE.findall(annotated_title):
                entities.setdefault(label, value.strip())
            if not entities:
                raise VerdictError(
                    "verdict 'annotated' needs at least one "
                    "[text](cpe_vendor|cpe_product|cpe_version) bracket")
            if "cpe_vendor" not in entities and "cpe_product" not in entities:
                raise VerdictError(
                    "verdict 'annotated' needs a vendor or a product bracket")
        else:
            annotated_title = ""  # never carry stale brackets on non-gold rows
        row = self.rows[index]
        row["annotated_title"] = annotated_title
        row["verdict"] = verdict
        row["annotator"] = self.identity
        row["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        row["notes"] = (notes or "").strip()
        self.save()
        return dict(row)

    # -- persistence ------------------------------------------------------

    def save(self) -> None:
        """Atomic full rewrite: temp file in the same directory + replace."""
        tmp = self.output_path.with_name(self.output_path.name + ".tmp")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
            writer.writeheader()
            for row in self.rows:
                writer.writerow(row)
        os.replace(tmp, self.output_path)

    # -- read model for the UI -------------------------------------------

    def progress(self) -> dict:
        counts = {v: 0 for v in VERDICTS}
        for row in self.rows:
            if row["verdict"] in counts:
                counts[row["verdict"]] += 1
        done = counts["annotated"] + counts["not_software"]
        return {"total": len(self.rows), "done": done, **counts}

    def as_payload(self) -> dict:
        return {
            "identity": self.identity,
            "queue": str(self.queue_path),
            "output": str(self.output_path),
            "progress": self.progress(),
            "rows": self.rows,
        }


# -- HTTP layer (thin: parse, delegate, serialize) -------------------------


def handle_state(state: ReviewState) -> dict:
    return state.as_payload()


def handle_verdict(state: ReviewState, payload: dict) -> dict:
    try:
        row = state.apply_verdict(
            index=int(payload.get("index", -1)),
            verdict=str(payload.get("verdict", "")),
            annotated_title=str(payload.get("annotated_title", "")),
            notes=str(payload.get("notes", "")),
        )
    except VerdictError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "row": row, "progress": state.progress()}


class _Handler(BaseHTTPRequestHandler):
    state: ReviewState  # set by serve()

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path in ("/", "/index.html"):
            self._send(200, UI_ASSET.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send_json(handle_state(self.state))
        else:
            self._send_json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/verdict":
            self._send_json({"ok": False, "error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "invalid JSON"}, 400)
            return
        result = handle_verdict(self.state, payload)
        self._send_json(result, 200 if result["ok"] else 422)

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        pass


def serve(queue_path: Path | str, identity: str, port: int = 8765,
          output_path: Path | str | None = None) -> None:
    """Blocking server loop; Ctrl+C stops it (all verdicts already saved)."""
    state = ReviewState.load(queue_path, identity=identity,
                             output_path=output_path)
    handler = type("BoundHandler", (_Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    p = state.progress()
    print(f"cpegen review — {state.queue_path}")
    print(f"  reviewer: {state.identity}")
    print(f"  progress: {p['done']}/{p['total']} done "
          f"({p['annotated']} annotated, {p['not_software']} not-software, "
          f"{p['skipped']} skipped)")
    print(f"  open:     http://127.0.0.1:{port}/   (Ctrl+C to stop; every "
          f"verdict is already on disk)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
