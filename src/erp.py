"""Thin client for the (read-only) mock ERP + local schema validation.

Delivery failures are reported, never raised or swallowed: _post returns (status, body) where
status 0 means the ERP could not be reached after retries (network error, timeout, repeated 5xx).
Any 4xx is returned as-is so callers can react (422 -> repair loop, 400 -> delivery failure).
"""
from __future__ import annotations
import json, time
from pathlib import Path
import urllib.request, urllib.error
from jsonschema import Draft7Validator

BASE = "http://localhost:8000"
RETRIES = 3                 # attempts per call
BACKOFF = (1, 3)            # seconds to wait between attempts
SCHEMA = json.loads((Path(__file__).parent.parent / "schema" / "contract.schema.json").read_text())
VALIDATOR = Draft7Validator(SCHEMA, format_checker=Draft7Validator.FORMAT_CHECKER)


def local_errors(record: dict) -> list[dict]:
    return [{"field": "/".join(map(str, e.path)) or "(root)", "error": e.message}
            for e in sorted(VALIDATOR.iter_errors(record), key=lambda e: list(e.path))]


def _json(raw: bytes) -> dict:
    try:
        return json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"raw": raw[:200].decode("utf-8", "replace")}


def _post(path: str, body: dict):
    last = ""
    for attempt in range(RETRIES):
        req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:      # must precede URLError (it is a subclass)
            payload = _json(e.read())
            if e.code < 500:
                return e.code, payload
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError) as e:   # connection refused, DNS, timeout, reset
            last = f"{type(e).__name__}: {e}"
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    return 0, {"error": f"ERP unreachable after {RETRIES} attempts ({last})"}


def post_contract(record: dict):
    return _post("/contracts", record)


def post_escalation(source_document: str, kind: str, reason: str, record: dict | None = None, **extra):
    body = {"source_document": source_document, "kind": kind, "reason": reason, "record": record}
    return _post("/escalate", body)


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def healthy() -> bool:
    """One quick check so a run does not spend model calls against a dead ERP."""
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False
