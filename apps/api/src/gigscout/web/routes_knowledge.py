"""The knowledge base: the company's own case studies, proposals, portfolio and rates, which pitches are written
from and checked against."""

import io
import logging
from datetime import UTC, datetime
from pathlib import PurePath

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select

from gigscout.outreach import claims_out, evidence_out
from gigscout.platform.tables import KnowledgeDoc
from gigscout.store.knowledge import DOC_KINDS
from gigscout.web.deps import SessionDep, WriterDep, Ws, WsDep, audit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

MAX_TEXT = 200_000  # characters per document
MAX_UPLOAD = 10 * 1024 * 1024  # bytes
MAX_PDF_PAGES = 200
MAX_DOCS = 500  # per workspace
TEXT_TYPES = {".txt", ".md", ".markdown", ".csv"}


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="other", pattern=f"^({'|'.join(DOC_KINDS)})$")
    text: str = Field(min_length=20, max_length=MAX_TEXT)


class CheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.get("")
def list_docs(session: SessionDep, ws: WsDep) -> dict:
    rows = session.scalars(select(KnowledgeDoc).where(KnowledgeDoc.workspace_id == ws.id)
                           .order_by(KnowledgeDoc.created_at.desc()))
    docs = [_out(r) for r in rows]
    return {"docs": docs, "kinds": list(DOC_KINDS), "chunks": sum(d["chunks"] for d in docs)}


@router.post("", status_code=status.HTTP_201_CREATED)
def add_doc(body: KnowledgeIn, session: SessionDep, ws: WriterDep) -> dict:
    return _store(session, ws, body.title.strip(), body.kind, body.text)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_doc(request: Request, session: SessionDep, ws: WriterDep,
                     filename: str = Query(min_length=1, max_length=200),
                     kind: str = Query(default="other", pattern=f"^({'|'.join(DOC_KINDS)})$")) -> dict:
    """The file's bytes as the request body (PDF, text or Markdown); the name says which."""
    data = bytearray()
    async for part in request.stream():  # read with a cap, so a huge body never fills memory
        data.extend(part)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Files up to 10 MB")
    suffix = PurePath(filename).suffix.lower()
    text = _pdf_text(bytes(data)) if suffix == ".pdf" else _plain_text(bytes(data), suffix)
    if len(text.strip()) < 20:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "No readable text in that file (scanned PDFs need OCR first)")
    title = PurePath(filename).stem.replace("_", " ").replace("-", " ").strip()[:200] or "Untitled"
    return _store(session, ws, title, kind, text[:MAX_TEXT])


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(doc_id: int, session: SessionDep, ws: WriterDep) -> None:
    row = session.get(KnowledgeDoc, doc_id)
    if row is None or row.workspace_id != ws.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    ws.index.knowledge().remove(doc_id)
    audit(session, ws, "knowledge.delete", str(doc_id), title=row.title)
    session.delete(row)
    session.commit()


@router.get("/search")
def search(ws: WsDep, q: str = Query(min_length=2, max_length=500), k: int = Query(default=5, ge=1, le=10)) -> dict:
    """What the pitch writer would cite for a lead like this."""
    return {"results": evidence_out(ws.index.knowledge().search(q, k=k))}


@router.post("/check")
def check(body: CheckIn, ws: WsDep) -> dict:
    """Which claims in a text the documents back, and which they do not."""
    knowledge = ws.index.knowledge()
    if knowledge.count() == 0:
        return {"claims": [], "empty": True}
    return {"claims": claims_out(knowledge.check_claims(body.text, ())), "empty": False}


def _store(session, ws: Ws, title: str, kind: str, text: str) -> dict:
    count = len(session.scalars(select(KnowledgeDoc.id).where(KnowledgeDoc.workspace_id == ws.id)).all())
    if count >= MAX_DOCS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"At most {MAX_DOCS} documents per workspace")
    row = KnowledgeDoc(workspace_id=ws.id, title=title, kind=kind, text=text, created_by=ws.email)
    session.add(row)
    session.flush()
    row.chunks = ws.index.knowledge().add(row.id, title, kind, text)
    audit(session, ws, "knowledge.add", str(row.id), title=title, kind=kind, chunks=row.chunks)
    session.commit()
    return _out(row)


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That PDF is password-protected")
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        log.info("Unreadable PDF upload: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That PDF could not be read") from None


def _plain_text(data: bytes, suffix: str) -> str:
    if suffix not in TEXT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a PDF, .txt or .md file")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _out(row: KnowledgeDoc) -> dict:
    return {"id": row.id, "title": row.title, "kind": row.kind, "chars": len(row.text), "chunks": row.chunks,
            "preview": " ".join(row.text.split())[:240], "created_by": row.created_by,
            "created_at": _aware(row.created_at).isoformat()}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)  # SQLite hands back naive UTC
