# Ask OLake

A RAG-powered chat assistant for the [OLake](https://olake.io) documentation.
Built for the Hacktoberfest Hack Day Bengaluru x OLake challenge.

## Challenge

Build a chat assistant for the OLake docs that answers user questions about setup,
source configuration, sync modes, catalogs, table maintenance, deployment and
troubleshooting. Every answer must cite its sources and say clearly when it doesn't
know. Runs on a public website, built as if for production.

## Deliverables

- Publicly reachable endpoint: `POST /ask` with `{"question": "..."}` returning
  `{"answer": "...", "sources": ["<url>", ...]}`
- Embeddable chat UI (`frontend/widget.html`) for a docs site
- Repo with this README explaining architecture and design choices

## Architecture

```
[User] -> embeddable widget (frontend/widget.html)
        -> POST /ask {question}
        -> FastAPI (backend/main.py)
            -> sentence-transformers embeddings (all-MiniLM-L6-v2)
            -> numpy cosine-similarity retrieval over chunked OLake docs
            -> LLM generation (OpenAI-compatible or Ollama) with citations
            -> {answer, sources}
```

- **Ingestion**: markdown docs in `backend/corpus/` are chunked (paragraph-aware,
  ~700 chars, 120 overlap) and embedded once into `backend/index.npz`.
- **Retrieval**: cosine similarity with a lexical-overlap rerank; low-confidence
  chunks are dropped and the answer context is limited to closely ranked evidence.
- **Honesty**: if no chunk clears the threshold, returns "I don't know" with
  empty sources.
- **Evaluation**: `tests/rag_eval_cases.json` contains supported and unsupported
  OLake questions. Run `pytest tests/test_rag_evaluation.py -q` to verify
  expected corpus evidence and retrieval results.
- **Citations**: each chunk carries its source URL; sources are deduplicated.
- **Source details**: `/ask` retains its URL-only `sources` array and adds
  `source_details` entries with the matched document title, URL, excerpt, score,
  and chunk ID.
- **LLM**: configurable via env vars (OpenAI-compatible or Ollama); falls back
  to extractive passages when no LLM is configured.
- **Conversation history**: SQLite stores messages and source references;
  owner-scoped history APIs support search, rename, reopen, and delete.
- **Troubleshooting mode**: opt-in answer structure for problems, causes,
  checks, solutions, and verification, grounded in retrieved context.

## Run locally

```powershell
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Set-Location backend
python main.py
```

On first run, the app builds the documentation index and serves on port 8000.
Open `http://localhost:8000/widget` for the chat UI. Before starting, edit
`.env` and set your OpenRouter key locally; never paste it into chat or commit it.

Test:
```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/ask' -Method Post `
  -ContentType 'application/json' -Body '{"question":"What sync modes does OLake support?"}'
```

## Run with Docker

```powershell
if (-not (Test-Path backend\.env)) { Copy-Item .env.example backend\.env }
docker compose up --build
```

`docker-compose.yml` loads `backend/.env`. Copy `.env.example` to `backend/.env`
and set your LLM credentials before starting.
Conversation history persists in the `ask-olake-data` Docker volume. For local
runs, SQLite defaults to `backend/data/ask_olake.db`; override it with
`ASK_OLAKE_DB`.

## Deploy to a public host

The service is a single container exposing `:8000`. Deploy the `Dockerfile` to any
public host (Railway, Render, Fly.io, Koyeb, etc.) and set the env vars from
`.env.example`. The endpoint `POST /ask` must be publicly reachable for
submission.

### Deploy to Vercel

The root `pyproject.toml` configures Vercel to load the FastAPI application from
`backend.main:app`. Import the repository into Vercel with the repository root as
the project root, then set the required environment variables in the Vercel
project settings and redeploy. Do not upload `.env`; add secrets such as
`OPENROUTER_API_KEY` as encrypted Vercel environment variables.

Vercel's function filesystem is not persistent. Conversation history uses
SQLite by default, so it will not persist reliably on Vercel; configure a
persistent database before relying on history endpoints. Also verify the
embedding model can download and initialize within Vercel's function size and
execution limits. For persistent SQLite and unrestricted model startup, deploy
the existing Docker application to a container host instead.

## Configure LLM

For OpenRouter, set `OPENROUTER_API_KEY` in `.env`; the example file uses
`https://openrouter.ai/api/v1` and `z-ai/glm-4.7-flash`. The older
`OPENAI_API_KEY` variable remains supported for OpenAI-compatible providers.
Alternatively, set `LLM_PROVIDER=ollama` and configure `OLLAMA_MODEL` to use
Ollama.

## Embed the widget

The documentation assistant is a standalone responsive page served at `/widget`.
It includes suggested questions, saved recent conversations, Markdown answers,
code highlighting, and clickable source links. It uses Markdown, sanitization,
and syntax-highlighting libraries from public CDNs; no separate frontend build
or `npm run dev` step is required.

For local development, start the FastAPI backend and open
`http://localhost:8000/widget`. The widget sends the existing
`POST /ask` request to the same origin by default.

To embed the hosted widget in another site, point it to the deployed API:

```html
<script>window.ASK_OLAKE_API = "https://your-host/ask";</script>
<iframe src="https://your-host/widget" ...></iframe>
```

## API

- `POST /ask` keeps accepting `{"question": "..."}` and returns `answer` and
  the URL-string `sources` list. Optional `conversation_id` and `mode` fields
  add persistent history and troubleshooting mode. Responses also include
  additive `source_details`, `conversation_id`, and `message_id` fields.
- `POST /session` creates a random browser capability token.
- `POST /conversations`, `GET /conversations`, `GET /conversations/search`,
  `GET/PATCH/DELETE /conversations/{id}`, and
  `GET /conversations/{id}/messages` provide history operations.
- History endpoints require the `X-Ask-Olake-Session` header returned by
  `/session`. The widget stores this opaque token in browser local storage and
  sends it as a bearer capability; SQLite stores only its SHA-256 hash.

There is no user login or account system. A browser profile shares its history,
and anyone who obtains its session token can access that browser's history.
Use HTTPS for hosted deployments. For multi-user or shared-device deployments,
add real authentication and authorization before exposing conversation history
to users.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto \| openai \| ollama \| none` |
| `OPENROUTER_API_KEY` | `` | OpenRouter API key (preferred for OpenRouter) |
| `OPENAI_API_KEY` | `` | Legacy OpenAI-compatible API key fallback |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible base URL |
| `OPENAI_MODEL` | `z-ai/glm-4.7-flash` | Model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama base URL |
| `OLLAMA_MODEL` | `gemma2:2b` | Ollama model |
| `EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `CORPUS_DIR` | `corpus` | Docs directory |
| `INDEX_PATH` | `index.npz` | Index file path |
| `TOP_K` | `5` | Top chunks retrieved |
| `SIM_THRESHOLD` | `0.35` | Cosine-similarity cutoff |
| `MAX_CONTEXT_CHARS` | `6000` | Context char budget |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `RATE_LIMIT_REQUESTS` | `60` | Requests per window per IP |
| `RATE_LIMIT_WINDOW` | `60` | Rate-limit window in seconds |
| `CACHE_TTL_SECONDS` | `0` | Response cache TTL (0 = disabled) |
| `ASK_OLAKE_DB` | `backend/data/ask_olake.db` | SQLite conversation-history database |

## Testing

```bash
pip install -r requirements.txt
pytest
```

## Design choices

- **Local embeddings**: `sentence-transformers/all-MiniLM-L6-v2` runs locally, so
  embedding cost is zero and no external embedding API is needed.
- **Small, persistent index**: `index.npz` is rebuilt on startup when missing or
  when corpus files are newer (index freshness). Small enough to ship in a container.
- **Honesty first**: thresholded retrieval + explicit "I don't know" with empty
  sources; the LLM is instructed to answer only from context.
- **Citations**: every chunk carries its source URL; sources are deduplicated in
  the URL-compatible response field, with separate structured source metadata.
- **Persistent history**: per-browser random tokens scope all conversation
  operations; token hashes are stored in SQLite, and messages plus their source
  excerpts are committed as an atomic exchange.
- **Extractive fallback**: when no LLM is configured, returns the most relevant
  passages instead of fabricating an answer.
- **Production readiness**: structured logging, IP-based rate limiting, env-driven
  CORS, optional response cache, Dockerfile, tests, CI.

## Security

- `.env` files are gitignored and must not contain real keys in the repo.
- `.env.example` documents all config variables with placeholders.
- Real API keys were removed from the repository.

## Scoring alignment

- Answer accuracy: RAG over curated OLake docs.
- Citations & honesty: thresholded retrieval + explicit "don't know".
- Production readiness: CORS, health endpoint, configurable, Docker-ready.
- UX & embedding: standalone widget + /widget route.
- Engineering: local embeddings (no API cost), small index, low latency, caching.
