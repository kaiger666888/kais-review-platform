# Technology Stack

**Project:** kais-review-platform (AI Production Pipeline Review/Governance Platform)
**Researched:** 2026-05-05
**Overall confidence:** HIGH

---

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12+ | Runtime | Performance improvements over 3.11 (faster comprehensions, exception groups), matches kais-* ecosystem, asyncio mature | HIGH |
| FastAPI | 0.136 | Web framework | Native async, built-in SSE via `StreamingResponse`, auto OpenAPI docs, Pydantic v2 integration, Jinja2 template support | HIGH |
| Pydantic | 2.13.3 | Data validation | FastAPI's validation layer, v2 is 5-50x faster than v1, strict mode for audit log integrity | HIGH |
| pydantic-settings | 2.14.0 | Configuration management | Environment variable loading, `.env` file support, validated config with type safety | HIGH |
| Uvicorn | 0.46.0 | ASGI server | Lightweight, production-ready, `--workers` for multi-process, HTTP/1.1 keep-alive for SSE | HIGH |

### Database Layer

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| SQLite | (system) | Primary database | Append-heavy audit log workload, single-writer matches review platform pattern, WAL mode for concurrent reads, zero ops overhead | HIGH |
| SQLAlchemy | 2.0.49 | ORM + query builder | Production-stable 2.0 release, async engine support via `create_async_engine`, explicit typing, declarative models | HIGH |
| aiosqlite | 0.21.0 | Async SQLite driver | Required for SQLAlchemy async engine with SQLite, wraps stdlib sqlite3 in async interface | HIGH |

### Cache & Queue

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Redis | 7.x (alpine) | State machine store, KV cache, SSE connection registry | In-memory speed for state transitions, TTL for one-time tokens, pub/sub for SSE fan-out, alpine image < 30MB | HIGH |
| redis-py | 7.4.0 | Redis client (async) | `redis.asyncio` module replaces deprecated aioredis, connection pooling, pipeline support | HIGH |
| arq | 0.28.0 | Task queue | Pure async, Redis-based, shares FastAPI event loop (no separate worker process), 10x lighter than Celery, cron support for policy sync | HIGH |

### Authentication & Security

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyJWT | 2.12.1 | JWT token generation/validation | Lightweight, no external deps, short-lived tokens (15min) + one-time review tokens, >=2.11.0 fixes CVE-2025-45768 | HIGH |
| python-multipart | 0.0.20 | Form data parsing | Required by FastAPI for file uploads (review material images/thumbnails) | HIGH |
| passlib | 1.7.4 | Password hashing | bcrypt wrapper for admin credentials, well-established | MEDIUM |

### Real-time Communication

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx | 0.28.1 | Async HTTP client (webhooks) | Async-native, HTTP/2 support, timeout control, webhook delivery to kais-movie-agent and kais-gold-team | HIGH |
| FastAPI SSE | (built-in) | Server-Sent Events | `StreamingResponse` with `text/event-stream` content type, no extra library, Nginx proxy support verified | HIGH |

### Frontend (Zero-Build)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| HTMX | 2.0.9 | Dynamic HTML over AJAX | 14KB gzipped, server-rendered HTML fragments replace SPA complexity, perfect for review CRUD flows, `hx-sse` for real-time status | HIGH |
| Alpine.js | 3.15.12 | Client-side interactivity | 15KB, lightweight state management for UI toggles, modal controls, token input forms -- complements HTMX where server round-trip is wasteful | HIGH |
| Tailwind CSS | 4.2.3 | Utility-first CSS | v4 is engine rewrite (Rust-based, faster), zero-build via CDN play script, mobile-first review UI | MEDIUM |
| Jinja2 | 3.1.6 | Server-side templates | FastAPI built-in support, partial rendering via jinja2-fragments for HTMX responses | HIGH |
| jinja2-fragments | 1.8.0 | Partial template rendering | Render named blocks instead of full pages for HTMX responses, avoids duplicate templates | HIGH |

### Observability & DevOps

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| structlog | 24.5.0 | Structured logging | JSON logs for Docker ingestion, context binding (request_id, review_id), better than stdlib logging for audit trail | HIGH |
| Dozzle | latest | Container log viewer | Read-only Docker log web UI, < 10MB RAM, development/debugging only | HIGH |
| Docker Compose | v2 | Container orchestration | 4-container deployment (API + Nginx + Redis + Dozzle), resource limits, health checks, restart policies | HIGH |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Web framework | FastAPI | Flask | No native async, no built-in OpenAPI, no SSE without extensions |
| Web framework | FastAPI | Django | Too heavy (ORM/admin/auth baked in), async support bolted on, overkill for API-first service |
| Web framework | FastAPI | Litestar | Smaller ecosystem, less community support, no clear advantage for this use case |
| ORM | SQLAlchemy 2.0 | SQLModel | Still pre-1.0 (v0.0.38), API surface unstable, not production-ready for audit log integrity requirements |
| ORM | SQLAlchemy 2.0 | Tortoise ORM | Async-native but less mature, smaller community, weaker migration tooling |
| Database | SQLite WAL | PostgreSQL | Single-machine deployment, append-heavy workload, < 400MB total RAM constraint, no distributed need |
| Task queue | arq | Celery | Celery requires broker + result backend + separate worker process, 10x heavier, not async-native |
| Task queue | arq | Dramatiq | Better than Celery but still needs RabbitMQ/Redis broker, more ceremony than arq |
| Real-time | SSE | WebSocket | Unidirectional push sufficient (status updates to reviewers), no browser API complexity, simpler infra |
| Real-time | SSE | Socket.IO | Requires socketio server library, protocol overhead, bidirectional not needed |
| Auth | PyJWT | python-jose | python-jose maintenance questionable, PyJWT is reference implementation, lighter |
| Frontend | HTMX | React/Vue | SPA overkill for review CRUD, requires build toolchain, larger bundle, slower first paint on mobile |
| Frontend | HTMX | Svelte | Requires build step, SPA pattern not needed for server-driven review flows |
| CSS | Tailwind CDN | Tailwind CLI build | v4 play CDN sufficient for review platform scope, avoids Node.js build dependency |
| Policy engine | YAML (custom) | OPA/Rego | OPA adds binary dependency + learning curve, YAML sufficient for v1 risk-tier routing rules |
| Policy engine | YAML (custom) | Cedar (AWS) | AWS-specific, not self-contained enough for embedded policy in Docker < 400MB |
| Redis client | redis-py 7.x | aioredis | aioredis deprecated since redis-py 4.2.0, merged into `redis.asyncio` module |
| Logging | structlog | loguru | structlog better for structured JSON output in Docker, loguru more suited to CLI/debugging |

---

## Key Architecture Decisions Embedded in Stack

### 1. Why async everywhere (FastAPI + arq + aiosqlite + redis.asyncio)
The review platform has three async-heavy workloads:
- SSE connections holding open for mobile reviewers (many idle connections)
- Webhook delivery to kais-movie-agent/kais-gold-team (outbound HTTP)
- arq background tasks (policy sync, timeout escalation)

A single async event loop handles all three without thread pool exhaustion. arq shares the FastAPI loop, avoiding the Celery pattern of a separate worker process.

### 2. Why SQLite WAL over PostgreSQL
- Single-machine deployment on 192.168.71.140 (8-16GB RAM)
- Audit log is append-only (write-once, read-many) -- SQLite's strength
- Total database will stay under 100MB for foreseeable future
- Zero ops: no separate DB process, no connection pooling config, no replication setup
- WAL mode enables concurrent reads while writing, which is the actual contention pattern (reviewers reading status while new submissions write)

### 3. Why HTMX + Jinja Fragments over SPA
The review workflow is fundamentally server-driven:
1. Reviewer opens review link (server renders page)
2. Reviewer sees content + approves/rejects (server processes, re-renders)
3. Status updates pushed via SSE (server sends HTML fragment)

There is zero need for client-side routing, client-side state management, or client-side data fetching. HTMX replaces all of this with `hx-post` + `hx-swap`. Jinja fragments (`render_block`) let us return just the status badge HTML instead of re-rendering the entire page.

### 4. Why Tailwind v4 CDN over build pipeline
Tailwind v4's "play CDN" script loads zero-build Tailwind in the browser. For a review platform with < 20 unique UI components, this is sufficient and avoids introducing Node.js into the build chain. The entire frontend stays Python-only.

---

## Critical Version Constraints

| Constraint | Details |
|------------|---------|
| PyJWT >= 2.11.0 | CVE-2025-45768 in v2.10.1 -- invalid ECDSA signatures accepted as valid. MUST use 2.11.0+ |
| redis-py >= 5.0.0 | aioredis merged into `redis.asyncio` module. Do NOT install aioredis separately |
| SQLAlchemy >= 2.0.0 | 1.4.x async API was transitional. 2.0 is the stable async API |
| FastAPI >= 0.100.0 | Pydantic v2 support requires FastAPI >= 0.100 |
| Python >= 3.12 | Required for performance characteristics and exception group support |

---

## Installation

```bash
# Core application
pip install fastapi==0.136 uvicorn[standard]==0.46.0 pydantic==2.13.3 pydantic-settings==2.14.0

# Database
pip install sqlalchemy[asyncio]==2.0.49 aiosqlite==0.21.0

# Cache & Queue
pip install redis==7.4.0 arq==0.28.0

# Authentication
pip install PyJWT==2.12.1 passlib[bcrypt]==1.7.4 python-multipart==0.0.20

# Real-time
pip install httpx==0.28.1

# Templates & Frontend
pip install jinja2==3.1.6 jinja2-fragments==1.8.0

# Observability
pip install structlog==24.5.0

# Development
pip install pytest pytest-asyncio httpx  # httpx already included, reused for test client
```

```bash
# Frontend (no npm -- CDN loaded in HTML)
# HTMX 2.0.9: <script src="https://unpkg.com/htmx.org@2.0.9"></script>
# Alpine.js 3.15.12: <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.12/dist/cdn.min.js"></script>
# Tailwind v4: <script src="https://cdn.tailwindcss.com"></script>
```

```bash
# Docker images
# API: python:3.12-slim (not alpine -- compiled dependencies need glibc)
# Nginx: nginx:alpine
# Redis: redis:7-alpine
# Dozzle: amir20/dozzle:latest (optional)
```

---

## Sources

| Source | Type | Confidence |
|--------|------|------------|
| PyPI verified versions (FastAPI, Pydantic, SQLAlchemy, redis-py, arq, PyJWT, httpx, Jinja2, uvicorn, structlog) | PyPI direct | HIGH |
| HTMX 2.0.9 release from htmx.org | Official release page | HIGH |
| Alpine.js 3.15.12 from CDN/alpinejs.dev | Official CDN | HIGH |
| Tailwind v4 from tailwindcss.com | Official docs | HIGH |
| CVE-2025-45768 PyJWT vulnerability | GitHub advisory | HIGH |
| redis-py changelog (aioredis merge) | GitHub releases | HIGH |
| jinja2-fragments documentation | GitHub README | MEDIUM |
| Docker Hub image sizes | Docker Hub | HIGH |
| PROJECT.md constraints (authoritative) | Project definition | HIGH |
| RESEARCH-REPORT.md competitor analysis | Existing research | MEDIUM |
| DEPLOYMENT-FEASIBILITY.md deployment specs | Existing research (note: contains Node.js references that conflict with PROJECT.md -- PROJECT.md is authoritative) | MEDIUM |
