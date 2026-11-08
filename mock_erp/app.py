"""
Atlas Industrial — Mock ERP API for the FDE Labs Challenge.

Validates every POST /contracts payload against schema/contract.schema.json and
REJECTS (HTTP 422) anything non-conformant. Structured-output discipline is
enforced here, not just in the rubric.

Run:
    pip install -r requirements.txt
    python app.py            # http://localhost:8000

Endpoints:
    GET  /health             -> {"status": "ok"}
    POST /contracts          -> load a record (422 if it fails schema validation)
    POST /escalate           -> route a record to human review (needs "reason")
    GET  /loaded             -> list successfully loaded records
    GET  /escalations        -> list escalations/quarantines
    POST /reset              -> clear in-memory state (handy while developing)

No database; state is in-memory and resets when the process restarts.
"""
import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from jsonschema import Draft7Validator

# The canonical schema shipped to participants (schema/contract.schema.json) —
# the fixed, checksum-verified contract every submission is judged against.
# CONTRACT_SCHEMA_PATH can point the API at an alternate schema for local
# testing, but the default is the one that counts.
SCHEMA_PATH = os.environ.get(
    "CONTRACT_SCHEMA_PATH",
    os.path.join(os.path.dirname(__file__), "..", "schema", "contract.schema.json"),
)
with open(os.path.abspath(SCHEMA_PATH)) as fh:
    CONTRACT_SCHEMA = json.load(fh)

# format_checker enforces "format": "date" — without it, jsonschema ignores
# `format` entirely and would accept "03/01/2024" or "March 1, 2024" as a date.
# The challenge promises ISO-8601 dates; this makes the API actually enforce it.
VALIDATOR = Draft7Validator(
    CONTRACT_SCHEMA, format_checker=Draft7Validator.FORMAT_CHECKER
)

app = FastAPI(title="Atlas Industrial Mock ERP", version="1.0.0")

# In-memory stores
LOADED: list[dict] = []
ESCALATIONS: list[dict] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health():
    return {"status": "ok", "loaded": len(LOADED), "escalations": len(ESCALATIONS)}


@app.post("/contracts")
def load_contract(record: dict):
    """Load a contract record. Rejects (422) if it doesn't match the schema."""
    errors = sorted(VALIDATOR.iter_errors(record), key=lambda e: list(e.path))
    if errors:
        detail = [
            {
                "field": "/".join(str(p) for p in err.path) or "(root)",
                "error": err.message,
            }
            for err in errors
        ]
        # 422 with a precise list of what's wrong -> build a repair loop around this.
        return JSONResponse(status_code=422, content={"accepted": False, "errors": detail})

    stored = {**record, "_loaded_at": _now(), "_id": len(LOADED) + 1}
    LOADED.append(stored)
    return {"accepted": True, "id": stored["_id"], "source_document": record.get("source_document")}


class Escalation(BaseModel):
    source_document: str
    reason: str
    record: dict | None = None
    kind: str = "escalate"  # or "quarantine"


@app.post("/escalate")
def escalate(item: Escalation):
    """Route a document to human review. Does not require a schema-perfect record."""
    if not item.reason or not item.reason.strip():
        raise HTTPException(status_code=400, detail="A non-empty 'reason' is required.")
    stored = item.model_dump()
    stored["_at"] = _now()
    stored["_id"] = len(ESCALATIONS) + 1
    ESCALATIONS.append(stored)
    return {"accepted": True, "id": stored["_id"], "kind": item.kind}


@app.get("/loaded")
def loaded():
    return {"count": len(LOADED), "records": LOADED}


@app.get("/escalations")
def escalations():
    return {"count": len(ESCALATIONS), "records": ESCALATIONS}


@app.post("/reset")
def reset():
    LOADED.clear()
    ESCALATIONS.clear()
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
