"""Per-format text extraction: PDF, DOCX, EML, CSV -> plain text."""
from __future__ import annotations
import csv, email, io
from email import policy
from pathlib import Path

def read_pdf(p: Path) -> str:
    from pypdf import PdfReader
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)

def read_docx(p: Path) -> str:
    import docx
    d = docx.Document(str(p))
    parts = [para.text for para in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)

def read_eml(p: Path) -> str:
    msg = email.message_from_bytes(p.read_bytes(), policy=policy.default)
    hdr = "\n".join(f"{k}: {msg[k]}" for k in ("From", "To", "Date", "Subject") if msg[k])
    body = msg.get_body(preferencelist=("plain", "html"))
    out = [hdr, "", body.get_content() if body else ""]
    for att in msg.iter_attachments():
        out.append(f"\n[ATTACHMENT {att.get_filename()} {att.get_content_type()}]")
        if att.get_content_type() == "application/pdf":
            out.append(read_pdf_bytes(att.get_content()))
        elif att.get_content_type().startswith("text/"):
            out.append(att.get_content())
    return "\n".join(out)

def read_pdf_bytes(b: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(b)).pages)

def read_csv_rows(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def read_any(p: Path) -> str:
    s = p.suffix.lower()
    if s == ".pdf": return read_pdf(p)
    if s == ".docx": return read_docx(p)
    if s == ".eml": return read_eml(p)
    raise ValueError(f"unsupported {p}")
