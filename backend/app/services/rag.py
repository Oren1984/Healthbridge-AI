"""Chunking, indexing and authorization-filtered hybrid retrieval.

Security invariant: callers pass the set of document IDs the requesting user is authorized to
read (from AccessPolicy). The SQL query restricts candidates to that set *before* ranking, so
vector similarity can never surface unauthorized content.
"""
import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, literal, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.observability import log_event, metrics
from app.services.embeddings import get_embedder

log = logging.getLogger(__name__)

CHUNK_CHARS = 700
CHUNK_OVERLAP = 120
MIN_SCORE = 0.18

# Instruction-like text inside documents (prompt-injection indicators).
INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts)|disregard (?:the|all|your) "
    r"(?:instructions|rules)|you are now|system prompt|act as (?:an?|the) |reveal (?:all|the|your)|"
    r"new instructions|developer mode|override (?:your|the) (?:rules|policy)|התעלם מ(?:כל )?ההוראות)"
)


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "did", "do", "does", "for", "from", "has", "have", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "say", "said", "the", "this", "to", "was", "were", "what",
    "when", "where", "which", "who", "why", "with", "you", "your", "about", "any", "there",
    "של", "את", "על", "מה", "אני", "זה", "עם", "או", "גם", "כי", "לי", "יש", "האם",
}
_TOKEN = re.compile(r"[\w֐-׿]+", re.UNICODE)


def keyword_query(query: str) -> str | None:
    """OR-query of meaningful tokens (tokens are word characters only, so safe for to_tsquery)."""
    tokens = [t.lower() for t in _TOKEN.findall(query) if len(t) > 1 and t.lower() not in _STOPWORDS]
    return " | ".join(dict.fromkeys(tokens)) or None


def chunk_text(text: str) -> list[tuple[int, int, str]]:
    """Paragraph-aware chunks of ~CHUNK_CHARS with overlap. Returns (start, end, text)."""
    chunks: list[tuple[int, int, str]] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(n, start + CHUNK_CHARS)
        if end < n:
            cut = max(text.rfind("\n\n", start + 200, end), text.rfind(". ", start + 200, end))
            if cut > start:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            lead = len(text[start:end]) - len(text[start:end].lstrip())
            chunks.append((start + lead, start + lead + len(piece), piece))
        if end >= n:
            break
        nxt = max(end - CHUNK_OVERLAP, start + 1)
        # Start the overlap at a word boundary so quoted excerpts never begin mid-word.
        space = text.find(" ", nxt, end)
        nl = text.find("\n", nxt, end)
        cands = [p for p in (space, nl) if p != -1]
        start = min(cands) + 1 if cands else nxt
    return chunks


def index_document(db: Session, doc: Document) -> int:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    if not doc.extracted_text:
        return 0
    pieces = chunk_text(doc.extracted_text)
    embedder = get_embedder()
    vectors = embedder.embed([p[2] for p in pieces])
    for i, ((s, e, t), v) in enumerate(zip(pieces, vectors)):
        db.add(DocumentChunk(document_id=doc.id, patient_id=doc.patient_id, ordinal=i, text=t, char_start=s,
                             char_end=e, embedding=v, embedding_provider=embedder.name,
                             suspicious=bool(INJECTION_PATTERNS.search(t))))
    return len(pieces)


@dataclass
class RetrievedChunk:
    document_id: uuid.UUID
    document_title: str
    document_date: str | None
    chunk_id: int
    text: str
    char_start: int
    char_end: int
    score: float
    vector_score: float
    keyword_score: float
    suspicious: bool


def retrieve(db: Session, patient_id: uuid.UUID, allowed_document_ids: set[uuid.UUID], query: str,
             k: int = 5) -> list[RetrievedChunk]:
    """Hybrid (vector + full-text) retrieval restricted to `allowed_document_ids`."""
    if not allowed_document_ids or not query.strip():
        return []
    embedder = get_embedder()
    qvec = embedder.embed([query])[0]
    kq = keyword_query(query)
    vscore = (1 - DocumentChunk.embedding.cosine_distance(qvec)).label("vscore")
    kscore = (func.ts_rank_cd(DocumentChunk.tsv, func.to_tsquery("simple", kq), 32) if kq else literal(0.0)).label("kscore")
    stmt = (
        select(DocumentChunk, Document.title, Document.document_date, vscore, kscore)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.patient_id == patient_id,                    # patient isolation
            DocumentChunk.document_id.in_(list(allowed_document_ids)),  # consent filter (pre-ranking)
            DocumentChunk.embedding_provider == embedder.name,
            Document.deleted_at.is_(None),
            Document.is_latest.is_(True),
        )
        .order_by(vscore.desc())
        .limit(40)
    )
    rows = db.execute(stmt).all()
    results = []
    for chunk, title, ddate, vs, ks in rows:
        ks_norm = min(1.0, float(ks or 0) * 4)
        score = 0.65 * float(vs or 0) + 0.35 * ks_norm
        results.append(RetrievedChunk(chunk.document_id, title, ddate.isoformat() if ddate else None, chunk.id,
                                      chunk.text, chunk.char_start, chunk.char_end, round(score, 4),
                                      round(float(vs or 0), 4), round(ks_norm, 4), chunk.suspicious))
    results.sort(key=lambda r: r.score, reverse=True)
    top = [r for r in results if r.score >= MIN_SCORE][:k]
    metrics.incr("rag.queries")
    if not top:
        metrics.incr("rag.insufficient_evidence")
    # Diagnostics without content: counts and scores only.
    log_event(log, "rag.retrieve", candidates=len(rows), returned=len(top),
              allowed_docs=len(allowed_document_ids), top_score=top[0].score if top else None,
              provider=embedder.name)
    return top
