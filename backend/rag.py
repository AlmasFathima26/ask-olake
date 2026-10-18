import os
import glob
import json
import re
from urllib.parse import urlsplit
import numpy as np
from sentence_transformers import SentenceTransformer

from config import (
    CORPUS_DIR, INDEX_PATH, EMBED_MODEL, TOP_K, SIM_THRESHOLD, MAX_CONTEXT_CHARS,
)

_model = None
_index = None  # dict: chunks(list of dict), embeddings(np.ndarray)
_STOPWORDS = {
    "a", "an", "and", "are", "can", "does", "for", "from", "how", "i", "in",
    "is", "it", "of", "on", "or", "the", "to", "what", "when", "where",
    "which", "with", "you", "your",
}


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _query_terms(text):
    return {
        term for term in re.findall(r"[a-z0-9]+", text.lower())
        if len(term) > 1 and term not in _STOPWORDS
    }


def _extract_title(text):
    """Extract the first H1 heading as the document title, else fall back."""
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return None


def _chunk_text(text, source, title=None, chunk_size=700, overlap=120):
    chunks = []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    buf = ""
    section = None
    buffer_section = None

    def flush():
        nonlocal buf, buffer_section
        if buf:
            chunks.append({"text": buf, "section": buffer_section})
            buf = ""
            buffer_section = None

    for p in paras:
        heading = re.match(r"^(#{1,3})\s+(.+)", p)
        if heading:
            flush()
            section = heading.group(2).strip() if len(heading.group(1)) > 1 else None
        if not buf:
            buffer_section = section
        if len(buf) + len(p) + 2 <= chunk_size:
            buf = (buf + "\n\n" + p).strip() if buf else p
        else:
            flush()
            buf = p
            buffer_section = section
            while len(buf) > chunk_size:
                chunks.append({
                    "text": buf[:chunk_size],
                    "section": buffer_section,
                })
                buf = buf[chunk_size - overlap:]
    flush()
    out = []
    for i, c in enumerate(chunks):
        out.append({
            "text": c["text"],
            "source": source,
            "title": title,
            "section": c["section"],
            "chunk_id": i,
        })
    return out


def build_index():
    global _index
    model = get_model()
    all_chunks = []
    base = os.path.join(os.path.dirname(__file__), CORPUS_DIR)
    for path in sorted(glob.glob(os.path.join(base, "**", "*.*"), recursive=True)):
        if not path.endswith((".md", ".txt", ".html")):
            continue
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        # derive source url from front matter if present
        source = path
        # try parse first line "source: url"
        first = text.splitlines()[0] if text.splitlines() else ""
        if first.lower().startswith("source:"):
            source = first.split(":", 1)[1].strip()
            text = "\n".join(text.splitlines()[1:]).lstrip()
        rel = os.path.relpath(path, base)
        if source == path:
            source = f"olake-docs://{rel}"
        title = _extract_title(text)
        all_chunks.extend(_chunk_text(text, source, title=title))
    if not all_chunks:
        _index = {"chunks": [], "embeddings": np.zeros((0, 384), dtype=np.float32)}
        return _index
    texts = [c["text"] for c in all_chunks]
    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    emb = np.asarray(emb, dtype=np.float32)
    _index = {"chunks": all_chunks, "embeddings": emb}
    # persist
    idx_path = os.path.join(os.path.dirname(__file__), INDEX_PATH)
    np.savez_compressed(idx_path, embeddings=emb, chunks=json.dumps(all_chunks))
    return _index


def _newest_corpus_mtime():
    base = os.path.join(os.path.dirname(__file__), CORPUS_DIR)
    newest = 0.0
    for path in glob.glob(os.path.join(base, "**", "*.*"), recursive=True):
        if not path.endswith((".md", ".txt", ".html")):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime > newest:
            newest = mtime
    return newest


def load_index():
    global _index
    if _index is not None:
        return _index
    idx_path = os.path.join(os.path.dirname(__file__), INDEX_PATH)
    newest_corpus = _newest_corpus_mtime()
    if os.path.exists(idx_path):
        index_mtime = os.path.getmtime(idx_path)
        if newest_corpus <= index_mtime:
            data = np.load(idx_path, allow_pickle=True)
            chunks = json.loads(str(data["chunks"]))
            emb = data["embeddings"]
            _index = {"chunks": chunks, "embeddings": emb}
            return _index
    return build_index()


def retrieve(question, k=TOP_K):
    idx = load_index()
    chunks = idx["chunks"]
    emb = idx["embeddings"]
    if len(chunks) == 0:
        return []
    model = get_model()
    q = model.encode([question], normalize_embeddings=True, show_progress_bar=False)
    q = np.asarray(q, dtype=np.float32)[0]
    scores = emb @ q
    query_terms = _query_terms(question)
    order = np.argsort(scores)[::-1][:k]
    results = []
    for i in order:
        chunk = chunks[i]
        semantic_score = float(scores[i])
        chunk_terms = _query_terms(chunk["text"])
        lexical_score = (
            len(query_terms.intersection(chunk_terms)) / len(query_terms)
            if query_terms else 0.0
        )
        rank_score = 0.82 * semantic_score + 0.18 * lexical_score
        results.append({
            "chunk": chunk,
            "score": semantic_score,
            "rank_score": rank_score,
        })
    return sorted(results, key=lambda result: result["rank_score"], reverse=True)


def context_and_sources(results):
    """Build context and structured source metadata from retrieval results.

    Returns (context, sources, max_score, low_confidence).
    sources is a list of dicts: {title, url, excerpt}
    """
    chosen = [r for r in results if r["score"] >= SIM_THRESHOLD]
    if chosen:
        best_rank = max(r.get("rank_score", r["score"]) for r in chosen)
        chosen = [
            r for r in chosen
            if r.get("rank_score", r["score"]) >= best_rank - 0.15
        ]
    if not chosen:
        chosen = results[:1] if results else []
        low = True
    else:
        low = False
    # build context up to MAX_CONTEXT_CHARS
    ctx_parts = []
    used_sources = []
    source_positions = {}
    total = 0
    for r in chosen:
        c = r["chunk"]
        source = c.get("source")
        label = c.get("title") or source or "OLake documentation"
        if c.get("section") and c.get("section") != label:
            label = f"{label} — {c['section']}"
        piece = f"[Source: {label}]\n{c['text']}"
        if total + len(piece) > MAX_CONTEXT_CHARS:
            break
        ctx_parts.append(piece)
        total += len(piece)
        if isinstance(source, str):
            parsed = urlsplit(source)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            excerpt = c["text"][:220].replace("\n", " ").strip()
            title = label
            if source in source_positions:
                existing = used_sources[source_positions[source]]
                if title not in existing["title"].split("; "):
                    existing["title"] = f"{existing['title']}; {title}"
                if excerpt and excerpt not in existing["excerpt"]:
                    existing["excerpt"] = f"{existing['excerpt']} ... {excerpt}"[:440]
                existing["score"] = max(existing["score"], r["score"])
            else:
                source_positions[source] = len(used_sources)
                used_sources.append({
                    "title": title,
                    "url": source,
                    "excerpt": excerpt,
                    "score": r["score"],
                    "chunk_id": c.get("chunk_id"),
                })
    context = "\n\n---\n\n".join(ctx_parts)
    # confidence: max score
    max_score = max((r["score"] for r in results), default=0.0)
    return context, used_sources, max_score, low
