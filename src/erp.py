"""Thin client for the (read-only) mock ERP + local schema validation."""
from __future__ import annotations
import json
from pathlib import Path
import urllib.request, urllib.error
from jsonschema import Draft7Validator

BASE = "http://localhost:8000"
SCHEMA = json.loads((Path(__file__).parent.parent / "schema" / "contract.schema.json").read_text())
VALIDATOR = Draft7Validator(SCHEMA, format_checker=Draft7Validator.FORMAT_CHECKER)


def local_errors(record: dict) -> list[dict]:
    return [{"field": "/".join(map(str, e.path)) or "(root)", "error": e.message}
            for e in sorted(VALIDATOR.iter_errors(record), key=lambda e: list(e.path))]


def _post(path: str, body: dict):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def post_contract(record: dict):
    return _post("/contracts", record)


def post_escalation(source_document: str, kind: str, reason: str, record: dict | None = None, **extra):
    body = {"source_document": source_document, "kind": kind, "reason": reason, "record": record}
    return _post("/escalate", body)


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())
