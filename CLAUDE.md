<!-- GSD:project-start source:PROJECT.md -->
## Project

**Kai's Review Platform V2**

AI 短剧管线治理平台（OpenClaw 治理层），为 kais-movie-agent、kais-gold-team 等 AI 系统提供 Shot Card 驱动的审核治理。通过 GitOps 版本控制、策略引擎路由、桌面三栏工作台 + 移动 PWA 卡片流双端审核、AI 审计预留窗口，为短剧管线提供可审计、可回溯、可渐进自动化的质量闸门。

**Core Value:** Shot Card 是审核原子 — 将 OpenClaw 节点拓扑折叠为叙事分镜单元，捆绑首帧/尾帧/视频/音频/提示词，实现"时空-视听"一体化审核，确保每个分镜在进入高成本下游执行前通过质量闸门。

### Constraints

- **资源限制**: 目标机器 8-16GB RAM，Docker 容器总内存 < 1GB
- **技术栈**: FastAPI (Python 3.12+) + PostgreSQL (TimescaleDB) + Redis 7 + HTMX/Alpine.js/Tailwind CSS + MinIO
- **网络**: 局域网部署，无公网，API 地址 http://192.168.71.140:8090
- **数据库**: PostgreSQL + TimescaleDB，热温冷分层存储
- **任务队列**: arq（纯 async，Redis-based）
- **前端**: 桌面三栏工作台（HTMX SSR），移动 PWA（卡片流），零构建步骤
- **安全**: Docker read_only + cap_drop ALL + non-root 用户
- **GitOps**: 所有决策逻辑入 Git，运行时读取 commit SHA
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

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
### NEW: Telegram Bot (v1.2)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| python-telegram-bot | 22.x | Telegram Bot API client | Fully async (v22), polling mode for LAN deployment (no public IP), InlineKeyboard for approve/reject, shares FastAPI event loop | HIGH |
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
| Telegram bot | python-telegram-bot | aiogram | aiogram is popular but python-telegram-bot is the reference implementation, better docs, larger community |
| Telegram bot | python-telegram-bot | telethon | Telethon is MTProto client (userbot), not Bot API. Wrong abstraction for bot use case |
| Bot deployment | Same process | Separate container | Separate container adds 150MB+ RAM, exceeds 400MB Docker budget, requires IPC |
| Bot mode | Polling | Webhook | Webhook requires public HTTPS URL, not available on LAN (192.168.71.140) |
## Key Architecture Decisions Embedded in Stack
### 1. Why async everywhere (FastAPI + arq + aiosqlite + redis.asyncio)
- SSE connections holding open for mobile reviewers (many idle connections)
- Webhook delivery to kais-movie-agent/kais-gold-team (outbound HTTP)
- arq background tasks (policy sync, timeout escalation)
### 2. Why SQLite WAL over PostgreSQL
- Single-machine deployment on 192.168.71.140 (8-16GB RAM)
- Audit log is append-only (write-once, read-many) -- SQLite's strength
- Total database will stay under 100MB for foreseeable future
- Zero ops: no separate DB process, no connection pooling config, no replication setup
- WAL mode enables concurrent reads while writing, which is the actual contention pattern (reviewers reading status while new submissions write)
### 3. Why HTMX + Jinja Fragments over SPA
### 4. Why Tailwind v4 CDN over build pipeline
### 5. Why python-telegram-bot in same process (v1.2)
- The review platform runs on 192.168.71.140 with no public internet access
- Telegram webhook mode requires a publicly accessible HTTPS URL -- not available
- Polling mode works via outbound connections only, compatible with LAN deployment
- python-telegram-bot v22 is fully async, shares FastAPI's event loop natively
- Same-process deployment avoids IPC overhead, keeps memory under 400MB total
- Direct function calls to state machine (no HTTP-to-localhost overhead)
- Bot lifecycle managed via FastAPI lifespan context manager
## Critical Version Constraints
| Constraint | Details |
|------------|---------|
| PyJWT >= 2.11.0 | CVE-2025-45768 in v2.10.1 -- invalid ECDSA signatures accepted as valid. MUST use 2.11.0+ |
| redis-py >= 5.0.0 | aioredis merged into `redis.asyncio` module. Do NOT install aioredis separately |
| SQLAlchemy >= 2.0.0 | 1.4.x async API was transitional. 2.0 is the stable async API |
| FastAPI >= 0.100.0 | Pydantic v2 support requires FastAPI >= 0.100 |
| Python >= 3.12 | Required for performance characteristics and exception group support |
| python-telegram-bot >= 22.0 | v22 is the fully-async rewrite. Do NOT use v20 or earlier (different async model) |
## Installation
# Core application
# Database
# Cache & Queue
# Authentication
# Real-time
# Templates & Frontend
# Observability
# NEW: Telegram Bot (v1.2)
# Development
# Frontend (no npm -- CDN loaded in HTML)
# HTMX 2.0.9: <script src="https://unpkg.com/htmx.org@2.0.9"></script>
# Alpine.js 3.15.12: <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.15.12/dist/cdn.min.js"></script>
# Tailwind v4: <script src="https://cdn.tailwindcss.com"></script>
# Docker images
# API: python:3.12-slim (not alpine -- compiled dependencies need glibc)
# Nginx: nginx:alpine
# Redis: redis:7-alpine
# Dozzle: amir20/dozzle:latest (optional)
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
| python-telegram-bot v22 PyPI | PyPI direct | HIGH |
| python-telegram-bot v22 official docs | Official documentation | HIGH |
| PTB GitHub issues #3687, #4107 (event loop integration) | GitHub issues | HIGH |
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
