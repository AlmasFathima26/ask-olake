import hashlib
import logging
import os
import re
import secrets
import sys
import threading
import time
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
import uvicorn

from config import (
    ALLOWED_ORIGINS,
    CACHE_TTL_SECONDS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    SIM_THRESHOLD,
)
from rag import retrieve, context_and_sources, build_index, load_index
from llm import generate
import database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s msg=%(message)s",
)
log = logging.getLogger("ask-olake")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    try:
        load_index()
    except Exception as e:
        log.error("index_load_failed error=%s", e)
    yield


app = FastAPI(title="Ask OLake", version="1.1.0", lifespan=lifespan)

origins = [o.strip() for o in (ALLOWED_ORIGINS or "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Source(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    url: str = Field(..., min_length=8, max_length=2048)
    excerpt: str | None = Field(default=None, max_length=500)
    score: float | None = Field(default=None, ge=0, le=1)
    chunk_id: int | None = Field(default=None, ge=0)

    @field_validator("url")
    @classmethod
    def http_source_only(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source URL must use HTTP or HTTPS")
        return value


class AskRequest(BaseModel):
    question: str = Field(..., max_length=4000)
    conversation_id: str | None = None
    mode: str = Field(default="normal", pattern="^(normal|troubleshoot)$")


class AskResponse(BaseModel):
    answer: str
    sources: list[str]
    source_details: list[Source] = Field(default_factory=list)
    conversation_id: str | None = None
    message_id: str | None = None


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if value is not None and not value.strip():
            raise ValueError("title cannot be blank")
        return value.strip() if value is not None else value


class ConversationUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("title cannot be blank")
        return value


class Conversation(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float


class Message(BaseModel):
    id: str
    role: str
    content: str
    sources: list[Source] | None = None
    mode: str = "normal"
    created_at: float


class SearchResult(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float


class SessionResponse(BaseModel):
    session_token: str


# Rate limiting: token bucket per client IP.
_rate_state = defaultdict(lambda: {"tokens": RATE_LIMIT_REQUESTS, "reset": time.time() + RATE_LIMIT_WINDOW})
_rate_lock = threading.Lock()


def _rate_limit_ok(client_ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        state = _rate_state[client_ip]
        if now > state["reset"]:
            state["tokens"] = RATE_LIMIT_REQUESTS
            state["reset"] = now + RATE_LIMIT_WINDOW
        if state["tokens"] <= 0:
            return False
        state["tokens"] -= 1
        return True


# Response cache: (question_hash, mode) -> (expiry, answer, sources, details)
_cache = {}
_cache_lock = threading.Lock()


def _cache_get(q: str, mode: str):
    if CACHE_TTL_SECONDS <= 0:
        return None
    h = (hashlib.sha256(q.encode("utf-8")).hexdigest(), mode)
    with _cache_lock:
        entry = _cache.get(h)
        if not entry:
            return None
        expiry, answer, sources, details = entry
        if time.time() > expiry:
            _cache.pop(h, None)
            return None
        return answer, sources, details


def _cache_set(q: str, mode: str, answer: str, sources: list, details: list):
    if CACHE_TTL_SECONDS <= 0:
        return
    h = (hashlib.sha256(q.encode("utf-8")).hexdigest(), mode)
    with _cache_lock:
        _cache[h] = (time.time() + CACHE_TTL_SECONDS, answer, sources, details)


def _session_owner(request: Request, required=True):
    token = request.headers.get("x-ask-olake-session", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,50}", token):
        if required:
            raise HTTPException(status_code=401, detail="valid browser session required")
        return None
    return token


def _save_exchange(conversation_id, owner_token, question, answer, details, mode):
    if owner_token is None:
        return conversation_id, None
    if conversation_id is None:
        conversation_id = database.create_conversation(owner_token, title=question[:60])
    ids = database.add_exchange(
        conversation_id, owner_token, question, answer, details, mode,
    )
    if ids is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    database.update_conversation_title(
        conversation_id, owner_token, question[:60]
    )
    return conversation_id, ids[1]


def _verified_source_details(items):
    verified = []
    for item in items:
        try:
            verified.append(Source(**item).model_dump())
        except (TypeError, ValueError) as exc:
            log.warning("invalid_retrieved_source error=%s", exc)
    return verified


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = hashlib.sha256(f"{time.time()}-{id(request)}".encode()).hexdigest()[:8]
    start = time.time()
    try:
        response = await call_next(request)
    except Exception as e:
        log.error("request_failed request_id=%s path=%s error=%s", request_id, request.url.path, e)
        raise
    latency_ms = int((time.time() - start) * 1000)
    client = request.client
    client_host = client.host if client else "unknown"
    log.info(
        "request request_id=%s method=%s path=%s status=%s latency_ms=%s client=%s",
        request_id, request.method, request.url.path, response.status_code, latency_ms, client_host,
    )
    return response


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question required")

    client = request.client
    client_ip = client.host if client else "unknown"
    if not _rate_limit_ok(client_ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    owner_token = _session_owner(request, required=False)
    conversation_id = req.conversation_id
    if conversation_id:
        if owner_token is None:
            raise HTTPException(status_code=401, detail="browser session required for conversation")
        if not database.get_conversation(conversation_id, owner_token):
            raise HTTPException(status_code=404, detail="conversation not found")

    question_hash = hashlib.sha256(q.encode("utf-8")).hexdigest()[:8]
    cached = _cache_get(q, req.mode)
    if cached is not None:
        answer, sources, details = cached
        conversation_id, message_id = _save_exchange(
            conversation_id, owner_token, q, answer, details, req.mode
        )
        log.info("ask request_id=%s question_hash=%s cached=true", question_hash, question_hash)
        return AskResponse(
            answer=answer, sources=sources, source_details=details,
            conversation_id=conversation_id, message_id=message_id,
        )

    try:
        results = retrieve(q)
        context, details, max_score, low = context_and_sources(results)
    except Exception as exc:
        log.exception("retrieval_failed question_hash=%s", question_hash)
        raise HTTPException(status_code=503, detail="documentation retrieval is temporarily unavailable") from exc
    details = _verified_source_details(details)
    if max_score < SIM_THRESHOLD or not results:
        answer = ("I don't know based on the available OLake documentation. "
                  "Try rephrasing, or check https://olake.io/docs.")
        conversation_id, message_id = _save_exchange(
            conversation_id, owner_token, q, answer, [], req.mode
        )
        _cache_set(q, req.mode, answer, [], [])
        log.info("ask request_id=%s question_hash=%s dont_know=true", question_hash, question_hash)
        return AskResponse(
            answer=answer, sources=[], source_details=[],
            conversation_id=conversation_id, message_id=message_id,
        )

    answer = generate(q, context, mode=req.mode)
    sources = list(dict.fromkeys(
        source["url"] for source in details
        if isinstance(source, dict) and isinstance(source.get("url"), str)
    ))
    conversation_id, message_id = _save_exchange(
        conversation_id, owner_token, q, answer, details, req.mode
    )
    _cache_set(q, req.mode, answer, sources, details)
    log.info("ask request_id=%s question_hash=%s max_score=%.3f low=%s", question_hash, question_hash, max_score, low)
    return AskResponse(
        answer=answer, sources=sources, source_details=details,
        conversation_id=conversation_id, message_id=message_id,
    )


@app.get("/health")
def health():
    idx = load_index()
    return {"status": "ok", "chunks": len(idx["chunks"])}


@app.get("/widget", response_class=HTMLResponse)
def widget():
    p = os.path.join(os.path.dirname(__file__), "..", "frontend", "widget.html")
    with open(p, encoding="utf-8") as f:
        return f.read()


@app.get("/")
def root():
    return {"service": "Ask OLake", "endpoint": "POST /ask"}


# --- Conversation endpoints ---

@app.post("/session", response_model=SessionResponse)
def create_session(request: Request):
    client = request.client
    if not _rate_limit_ok(client.host if client else "unknown"):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    return SessionResponse(session_token=database.new_session_token())


@app.post("/conversations", response_model=Conversation, status_code=201)
def create_conversation_endpoint(
    request: Request,
    payload: ConversationCreate | None = None,
):
    owner_token = _session_owner(request)
    title = payload.title if payload and payload.title else "New conversation"
    cid = database.create_conversation(owner_token, title=title)
    row = database.get_conversation(cid, owner_token)
    return Conversation(**row)


@app.get("/conversations", response_model=list[Conversation])
def list_conversations_endpoint(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
):
    owner_token = _session_owner(request)
    rows = database.list_conversations(
        owner_token, limit=limit, search=search
    )
    return [Conversation(**r) for r in rows]


@app.get("/conversations/search", response_model=list[SearchResult])
def search_conversations_endpoint(
    request: Request,
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
):
    owner_token = _session_owner(request)
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="search query required")
    rows = database.search_conversations(owner_token, query=query, limit=limit)
    return [SearchResult(**r) for r in rows]


@app.get("/conversations/{cid}", response_model=Conversation)
def get_conversation_endpoint(
    request: Request,
    cid: str = Path(..., min_length=20, max_length=64),
):
    owner_token = _session_owner(request)
    row = database.get_conversation(cid, owner_token)
    if row is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return Conversation(**row)


@app.patch("/conversations/{cid}", response_model=Conversation)
def update_conversation_endpoint(
    request: Request,
    cid: str = Path(..., min_length=20, max_length=64),
    payload: ConversationUpdate = ...,
):
    owner_token = _session_owner(request)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    if not database.update_conversation_title(cid, owner_token, title):
        raise HTTPException(status_code=404, detail="conversation not found")
    row = database.get_conversation(cid, owner_token)
    return Conversation(**row)


@app.delete("/conversations/{cid}", status_code=204)
def delete_conversation_endpoint(
    request: Request,
    cid: str = Path(..., min_length=20, max_length=64),
):
    owner_token = _session_owner(request)
    if not database.delete_conversation(cid, owner_token):
        raise HTTPException(status_code=404, detail="conversation not found")


@app.get("/conversations/{cid}/messages", response_model=list[Message])
def get_messages_endpoint(
    request: Request,
    cid: str = Path(..., min_length=20, max_length=64),
):
    owner_token = _session_owner(request)
    if not database.get_conversation(cid, owner_token):
        raise HTTPException(status_code=404, detail="conversation not found")
    rows = database.get_messages(cid, owner_token)
    messages = []
    for r in rows:
        source_items = []
        for source in r.get("sources") or []:
            try:
                source_items.append(Source(**source))
            except (TypeError, ValueError):
                log.warning("invalid_persisted_source conversation_id=%s", cid)
        messages.append(Message(
            id=r["id"],
            role=r["role"],
            content=r["content"],
            sources=source_items,
            mode=r.get("mode", "normal"),
            created_at=r["created_at"],
        ))
    return messages


if __name__ == "__main__":
    # build index if missing
    build_index()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
