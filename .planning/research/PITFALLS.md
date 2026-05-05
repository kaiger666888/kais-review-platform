# Pitfalls Research

**Domain:** AI Production Pipeline Review/Governance Platform (FastAPI + SQLite WAL + HTMX + Docker)
**Researched:** 2026-05-05
**Confidence:** HIGH (SQLite/SSE/HTMX/Docker pitfalls verified against community reports and official docs; state machine/policy engine pitfalls verified against domain patterns)

## Critical Pitfalls

### Pitfall 1: SQLite "database is locked" Under Concurrent Writes

**What goes wrong:**
Two or more FastAPI async handlers attempt to write to SQLite simultaneously. One succeeds, the other crashes with `sqlite3.OperationalError: database is locked`. The audit log loses entries, or an approval action silently fails. This is the single most common production failure in FastAPI+SQLite apps.

**Why it happens:**
SQLite allows only one writer at a time, even in WAL mode. When using synchronous SQLAlchemy with FastAPI `async def` routes, synchronous `db.commit()` calls block the event loop. This means the write lock is held across `await` boundaries -- session A starts a transaction, hits `await asyncio.sleep()` (or any await), and the event loop gives control to session B which also tries to write. Session B either blocks or gets "database is locked." The root cause is mixing synchronous DB drivers with async routes. With `aiosqlite`, the event loop properly yields during I/O waits, but the fundamental single-writer constraint remains.

**How to avoid:**
1. Use `aiosqlite` (SQLAlchemy async engine with `sqlite+aiosqlite://`) -- this ensures DB operations yield to the event loop properly instead of blocking it.
2. Enable WAL mode on every connection: `PRAGMA journal_mode=WAL;`
3. Set `PRAGMA busy_timeout=5000;` (5 seconds) so that write contention waits instead of immediately failing.
4. Keep transactions as short as possible -- do all computation before opening the transaction, then write and commit immediately.
5. Run a single uvicorn worker. Multiple workers means multiple processes, each with independent connections, and SQLite's single-writer lock becomes a severe bottleneck. Single worker + async is the correct architecture.
6. Consider a write serialization queue: all mutations go through a single async queue, ensuring exactly one write at a time, with reads proceeding freely via WAL readers.

**Warning signs:**
- Intermittent 500 errors on write endpoints under load
- `OperationalError: database is locked` in logs
- Slow write endpoints that get slower with more concurrent users
- Database file growing rapidly (WAL file not checkpointing)

**Phase to address:**
Phase 1 (project skeleton) -- the database layer and connection pooling strategy must be correct from day one. Retrofitting async DB access after writing synchronous CRUD is extremely painful.

---

### Pitfall 2: SSE Zombie Connections and Memory Leaks

**What goes wrong:**
SSE connections accumulate on the server without being cleaned up. Mobile browsers are especially bad -- they open connections, switch tabs, lose network, and the server never knows the client is gone. Over hours/days, the server runs out of memory or hits file descriptor limits. The FastAPI process becomes sluggish, then unresponsive.

**Why it happens:**
The server cannot detect a client disconnect until it actually tries to send data. If no review status changes happen for a client, their zombie connection lingers indefinitely. Browser `EventSource` auto-reconnects on connection loss, but the old server-side handler may not have been cleaned up yet, creating duplicate connections. Storing client references in a dict/list without periodic cleanup is the direct cause.

**How to avoid:**
1. Use `sse-starlette` library instead of raw `StreamingResponse` -- it handles connection lifecycle events properly, including client disconnect detection.
2. Implement a heartbeat: send a keep-alive comment (`: heartbeat\n\n`) every 30 seconds. This serves two purposes: (a) keeps the connection alive through proxies/load balancers, and (b) detects dead connections because the send will fail.
3. Store active connections in a structured manager (not a bare dict). Include a timestamp. Periodically sweep connections older than a threshold (e.g., 2 hours).
4. Set `proxy_read_timeout` in Nginx SSE location to match your maximum expected connection lifetime (e.g., `86400s` for 24h).
5. Set `proxy_buffering off` and `proxy_cache off` in Nginx for the SSE endpoint -- buffered SSE is broken SSE.
6. Set `chunked_transfer_encoding off` in Nginx SSE config -- SSE uses its own framing.
7. Limit max concurrent SSE connections per server instance. With 400MB RAM budget, a practical limit is ~200 concurrent SSE connections.

**Warning signs:**
- Memory usage climbing steadily over hours
- Growing number of entries in connection tracking dict
- File descriptor exhaustion (`Too many open files`)
- Heartbeat sends failing silently

**Phase to address:**
Phase 2 (real-time events + SSE) -- connection lifecycle management must be built into the SSE implementation from the start, not bolted on after.

---

### Pitfall 3: State Machine Race Conditions in Concurrent Approvals

**What goes wrong:**
Two approvers open the same review simultaneously. Both click "approve" within milliseconds of each other. Without optimistic locking, both requests read the state as "PENDING", both transition to "APPROVED", and the review is approved twice. Or worse: one approves and the other rejects, and the final state depends on which request commits last. The audit trail becomes inconsistent.

**Why it happens:**
Classic TOCTOU (time-of-check-time-of-use) bug. The state is read, validated, modified, and written back in separate steps without any concurrency control. SQLite's transaction isolation helps, but in async code the gap between read and write can span await points, allowing interleaving. Even with SQLite's file-level locking, the application logic can read-then-write in two separate transactions.

**How to avoid:**
1. Add a `version` integer column to the review table. On every state transition, use optimistic locking: `UPDATE reviews SET state='APPROVED', version=version+1 WHERE id=? AND version=? AND state='PENDING'`. If `affected_rows == 0`, the state was already changed by another request -- return a conflict error (409).
2. Perform the state read-check-write in a single SQL transaction (not separate queries). Use `BEGIN IMMEDIATE` to acquire a write lock at the start of the transaction.
3. Make transitions idempotent: if a request tries to approve an already-approved review, return success (not an error). This handles retry scenarios gracefully.
4. Log every transition attempt (successful or not) to the audit trail, including the actor, timestamp, previous state, intended new state, and outcome.
5. Define all invalid transitions explicitly in the state machine. Reject anything not in the allowed transition map. Never allow "soft" transitions that skip states.

**Warning signs:**
- Duplicate approval/rejection notifications for the same review
- Audit log shows two transitions from the same source state
- Reviews stuck in impossible states (e.g., "APPROVED" then "REJECTED" with no resubmission)
- Complaints from users that their action "didn't take effect"

**Phase to address:**
Phase 1 (state machine + checkpoint design) -- the optimistic locking strategy must be part of the initial schema and state machine implementation. Adding version columns and transaction guards later requires a migration and can miss edge cases.

---

### Pitfall 4: HTMX SSE Extension Error Handling Gaps

**What goes wrong:**
The HTMX SSE extension (`ext/sse.js`) has known issues with error handling (GitHub Issue #134). When the SSE stream returns a non-200 status code (even 204 No Content), the extension throws errors instead of gracefully handling the response. During server restarts or network interruptions, the extension's auto-reconnect behavior can flood the server with reconnection attempts from all connected clients simultaneously (thundering herd). The UI shows broken states or error popups that confuse reviewers.

**Why it happens:**
The HTMX SSE extension intercepts `EventSource` behavior but does not properly handle all HTTP status codes. Unlike core HTMX (which respects status codes and can show error indicators), the SSE extension tries to process every response. The auto-reconnect logic has no exponential backoff or jitter, so all clients reconnect at the same interval after a server restart.

**How to avoid:**
1. Always send valid SSE data from the endpoint. Never return 204 or error status codes from an SSE endpoint. If nothing to send, use SSE comments (`: nothing\n\n`) as keep-alive.
2. Implement server-side reconnection throttling: track recent SSE connection attempts by IP and rate-limit them.
3. On the client side, consider using a custom `EventSource` wrapper with exponential backoff (the HTMX SSE extension supports custom EventSource via `htmx.config.sseEventSource` in some versions).
4. Handle `htmx:responseError` and `htmx:sendError` events globally to show user-friendly "reconnecting..." messages instead of raw errors.
5. Test the SSE disconnect/reconnect flow explicitly: kill the server, restart it, and verify the mobile browser reconnects and shows correct state.
6. Use a single SSE connection per page (not multiple streams) to avoid hitting the browser's 6-connection-per-domain limit (HTTP/1.1).

**Warning signs:**
- Console errors about SSE processing failures on mobile devices
- All review dashboards going blank simultaneously after a server restart
- Server logs showing burst of SSE connection requests after restart
- Users reporting "stuck" review pages that don't update

**Phase to address:**
Phase 2 (SSE implementation) -- error handling and reconnection strategy must be designed alongside the SSE endpoint, not as an afterthought.

---

### Pitfall 5: YAML Policy Engine Silent Failures and Complexity Creep

**What goes wrong:**
YAML policy rules silently produce wrong routing decisions. A typo in a risk level name ("hight" instead of "high") causes the rule to never match, defaulting to a less restrictive route. Policies grow in complexity without anyone noticing -- 20 rules become 200, evaluation takes 500ms per request, and no one remembers what half the rules do. Conflicting rules produce unpredictable results (which rule wins when two match?).

**Why it happens:**
YAML is deceptively simple to write but has no type checking, no validation at load time, and no compilation step to catch errors. The policy engine has no dry-run mode, so the only way to test a rule is to submit a real review. Rule evaluation order is ambiguous when multiple rules could match. No one builds a rule tester because "YAML is simple enough."

**How to avoid:**
1. Define a JSON Schema for policy YAML files and validate every policy at load time. Reject policies that don't conform. This catches typos, missing fields, invalid enum values immediately.
2. Build a policy dry-run endpoint: `POST /api/v1/policy/dry-run` that accepts a mock review payload and returns which rules would match and what routing decision would be made, without actually creating a review.
3. Implement deterministic rule precedence: rules are evaluated in explicit priority order (first match wins, or highest priority wins). Document the resolution strategy.
4. Add a policy evaluation performance budget: if evaluation takes >50ms, log a warning. If it takes >200ms, reject it. This prevents complexity creep.
5. Log every policy evaluation decision: which rules matched, which didn't, and the final routing decision. This is essential for debugging wrong routing.
6. Implement conflict detection: when a new policy is loaded, check if it conflicts with existing policies (same conditions, different outcomes) and warn.
7. Limit v1 policy complexity: cap at 50 rules maximum. If you need more, the policy structure needs redesigning, not more rules.

**Warning signs:**
- Reviews being routed to wrong queues (AUTO when they should be HUMAN)
- Policy files growing past 200 lines
- "I don't understand why this review went to human approval" comments
- Policy evaluation logging shows rules matching that shouldn't

**Phase to address:**
Phase 1 (policy engine design) -- the validation schema, evaluation order, and dry-run capability must be part of the initial policy engine design. Adding validation later means a period of unvalidated policies in production.

---

### Pitfall 6: Docker read_only + SQLite WAL File Mismatch

**What goes wrong:**
The Docker Compose config sets `read_only: true` on the API container for security, but SQLite WAL mode creates `-wal` and `-shm` files in the same directory as the database. If the volume mount only covers the `.db` file (not its parent directory), WAL file creation fails. SQLite falls back to journal mode, and concurrent write performance degrades. Or worse: the WAL files are created on a tmpfs that gets wiped on container restart, corrupting the database.

**Why it happens:**
SQLite WAL mode requires write access to the directory containing the database file, not just the file itself. The `-wal` and `-shm` files are created alongside the `.db` file. Docker `read_only: true` makes the entire container filesystem read-only, with only explicitly mounted volumes writable. If the volume mount is misconfigured (mounting a single file instead of a directory, or mounting a tmpfs at the wrong path), WAL files can't be created or are lost on restart.

**How to avoid:**
1. Mount the entire data directory, not just the database file: `./data:/app/data` (not `./data/review.db:/app/data/review.db`). This allows SQLite to create `-wal` and `-shm` files in the same directory.
2. Use a bind mount (not tmpfs) for the SQLite data directory. tmpfs loses data on container restart, which corrupts the WAL state.
3. Verify WAL mode is actually active after deployment: `sqlite3 /path/to/data/review.db "PRAGMA journal_mode;"` should return `wal`, not `delete`.
4. Add tmpfs mounts only for directories that genuinely need temporary writes: `/tmp`, `/var/run`, etc. Never for the SQLite data directory.
5. Test the deployment from scratch: `docker compose down -v && docker compose up -d` and verify the database initializes correctly with WAL mode.

**Warning signs:**
- `PRAGMA journal_mode` returns `delete` instead of `wal` in production
- SQLite performance degrades unexpectedly
- `OperationalError: attempt to write a readonly database` errors
- Database corruption after container restart

**Phase to address:**
Phase 3 (Docker deployment) -- but the schema must be designed with WAL in mind from Phase 1. The Docker Compose config must be tested with `read_only: true` from the first deployment.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Synchronous SQLite with async routes | Faster initial development | "database is locked" errors under any real load; requires full rewrite of DB layer | Never -- use aiosqlite from the start |
| No version column on state transitions | Simpler schema | Race conditions in concurrent approvals; impossible to detect conflicts | Never -- add version column in initial migration |
| Raw StreamingResponse for SSE | No extra dependency | Zombie connections, no disconnect detection, memory leaks | Only for prototypes, never production |
| Storing SSE connections in a plain dict | Simple implementation | Unbounded growth, no cleanup, memory leak | Acceptable for MVP demo if cleanup timer is added immediately after |
| No YAML policy validation | Ship faster | Silent wrong routing decisions, debugging nightmares | Never -- add JSON Schema validation in first policy engine implementation |
| Single Docker compose file with no resource limits | Works in development | OOM kills on production machine, one container starving others | Development only -- add limits before any real deployment |
| Skipping audit log on failed transitions | Fewer log entries | Impossible to debug race conditions or understand what happened | Never -- log all attempts, successful or not |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| kais-movie-agent Webhook | Not handling callback failures (target down, timeout) | Use arq task queue with retry policy: 3 retries with exponential backoff. Log all callback attempts. |
| kais-gold-team Webhook | Synchronous webhook send blocks the review API response | Send webhooks asynchronously via arq background tasks. Return 202 to the caller immediately. |
| Redis (arq task queue) | Not setting task TTL -- failed tasks stay in queue forever | Set `max_tries=3`, `timeout=300`, and `expires_in=3600` on all arq tasks. |
| Nginx SSE proxy | Default proxy_buffering on -- SSE events buffered and sent in batches | Set `proxy_buffering off`, `proxy_cache off`, `proxy_http_version 1.1`, `proxy_set_header Connection ''` |
| HTMX frontend | Returning JSON from API endpoints | HTMX expects HTML fragments. Return HTML partials, not JSON. Use HTMX OOB swaps for multi-element updates. |
| SQLite backup | Running `sqlite3 backup` while container holds write lock | Use SQLite's Online Backup API (`sqlite3 ... ".backup 'path'"`) which handles concurrent access. Or use `PRAGMA wal_checkpoint(TRUNCATE)` before copy. |
| Browser SSE reconnection | Not handling the `Last-Event-ID` header on reconnect | Track event IDs server-side. On reconnect, replay missed events since `Last-Event-ID`. Without this, clients miss events that happened during disconnection. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unindexed queries on audit log table | Slow audit log queries, increasing response times | Add indexes on `review_id`, `created_at`, `actor_id`, `action` from the start. Use composite index on `(review_id, created_at)` | ~10K audit log rows |
| Policy evaluation on every request with no caching | P99 latency increasing proportionally to policy count | Cache policy evaluation results in Redis with TTL. Invalidate on policy change. | ~20+ active policies |
| SSE connections per browser tab (HTTP/1.1 limit of 6) | New SSE connections fail silently, updates stop | Use a single SSE multiplexed connection per page. Route events to correct DOM elements by event name/type. | Opening 2+ tabs with SSE |
| SQLite WAL file growing unbounded | Disk usage grows, slow reads | Run periodic WAL checkpoint: `PRAGMA wal_checkpoint(TRUNCATE)` via cron or background task | Long-running server with many writes, no restart |
| Loading full review with all relations for list view | Slow review list page, increasing memory per request | Use projection queries for list views. Load full relations only for detail view. | ~1000+ reviews |
| No pagination on audit log endpoint | Timeout on audit log query, memory spike | Paginate all list endpoints with cursor-based pagination (not offset-based, which degrades on large tables) | ~10K audit log entries |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| JWT secret in docker-compose.yml committed to git | Anyone with repo access can forge tokens | Use `.env` file (gitignored) for secrets. Validate `.env.example` is the only committed env file. |
| One-time review tokens with no expiry | Stale tokens usable indefinitely if found | Set 72-hour expiry on review tokens. Delete expired tokens via arq periodic task. |
| No rate limiting on approval endpoints | Brute-force token guessing or DoS | Add Nginx rate limiting: `limit_req_zone` on `/api/v1/approval/` paths. |
| SSE endpoint with no authentication | Anyone can connect to SSE stream and see review data | Validate JWT or review token on SSE endpoint before streaming. Close connection immediately on auth failure. |
| Audit log stored in same SQLite as operational data | SQL injection could delete audit trail | Use separate SQLite database file for audit log (append-only, no delete/update permissions in application code). |
| CORS allowing all origins | CSRF attacks from malicious pages | Set specific allowed origins (kais-movie-agent, kais-gold-team URLs). Use HTMX's built-in CSRF protection. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No feedback during SSE reconnection | Reviewers see stale status, make decisions on outdated info | Show a "reconnecting..." banner when SSE disconnects. Disable approval buttons during reconnection. |
| HTMX swap without visual indicator | User clicks approve, nothing visible happens for 1-2 seconds, clicks again (double-approve) | Use HTMX `hx-indicator` to show loading spinner on every mutation request. Disable button during request. |
| Mobile viewport not tested | Approval buttons off-screen on phones, horizontal scrolling | Test with Chrome DevTools mobile simulation from Phase 2. Use Tailwind responsive breakpoints (`sm:`, `md:`). |
| No confirmation for destructive actions | Accidental rejection of important review | Show confirmation modal (Alpine.js `x-data` + `x-show`) for reject/block actions. One-click approve is OK; reject should require confirmation + reason. |
| Review status shown as text only | Status changes not noticeable on a busy review list | Use color-coded badges (Tailwind `bg-green-500`, `bg-yellow-500`, `bg-red-500`). Animate status changes with HTMX `htmx-added` class. |
| HTMX 400/500 responses not handled in v2 | User sees nothing when server returns error | Configure `htmx.config.responseHandling` or use HTMX 4.x which swaps error responses by default. Show error toast via Alpine.js. |

## "Looks Done But Isn't" Checklist

- [ ] **SQLite WAL mode:** Often enabled in code but not actually active because volume mount is misconfigured -- verify with `PRAGMA journal_mode` in the running container
- [ ] **SSE disconnect detection:** Often "implemented" by assuming the library handles it -- verify by killing a client and checking server-side connection list shrinks
- [ ] **Optimistic locking on state transitions:** Often "implemented" with a version column but the UPDATE doesn't check `affected_rows` -- verify the code handles 0 affected rows (conflict) correctly
- [ ] **Docker resource limits:** Often set in compose file but never tested under load -- verify with `docker stats` during load test that limits are enforced
- [ ] **Policy dry-run:** Often "working" but testing with a subset of conditions -- verify dry-run matches actual routing decisions for at least 10 test cases
- [ ] **Audit log immutability:** Often "append-only" in intent but the ORM allows updates/deletes -- verify no UPDATE/DELETE SQL is ever generated against the audit table
- [ ] **HTMX CSRF protection:** Often "added" via `hx-headers` on body element but breaks with `hx-boost` -- verify CSRF token is sent on boosted links and form submissions
- [ ] **Backup script:** Often "tested" by running once manually -- verify it runs via cron for 48 hours without issues, and restored backup actually works
- [ ] **Nginx SSE proxy:** Often "configured" but with default proxy_buffering still active -- verify with `curl -N` that events arrive individually, not in batches

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| "database is locked" errors in production | MEDIUM | 1. Add `busy_timeout` pragma immediately. 2. Shorten transactions. 3. If using sync driver, migrate to aiosqlite (requires rewriting all DB code). |
| SSE zombie connections causing OOM | LOW | 1. Deploy connection cleanup timer. 2. Restart API container to clear accumulated connections. 3. Add connection limit. |
| Concurrent approval race condition | HIGH | Requires data migration to add version column + deploy new code. Any approvals that happened during the race must be manually audited. |
| Wrong policy routing in production | MEDIUM | 1. Add dry-run endpoint and validation. 2. Manually audit incorrectly routed reviews. 3. Re-process affected reviews with corrected policies. |
| WAL files lost on container restart (tmpfs) | HIGH | Database may be corrupted. Restore from latest backup. Any writes between backup and crash are lost. |
| HTMX SSE extension errors in production | LOW | 1. Ensure SSE endpoint always returns valid data (never 204/error). 2. Add client-side error handler. 3. Consider custom EventSource wrapper. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| SQLite concurrent writes | Phase 1: Database layer | Load test with 20 concurrent write requests, verify 0 "database is locked" errors |
| SSE zombie connections | Phase 2: Real-time events | Open 50 SSE connections, close clients, verify server connection list drops to 0 within 60 seconds |
| State machine race conditions | Phase 1: State machine + schema | Two concurrent approve requests on same review, verify one returns 409 Conflict |
| HTMX SSE error handling | Phase 2: SSE + HTMX integration | Kill server mid-SSE stream, restart, verify client reconnects and shows correct state |
| YAML policy silent failures | Phase 1: Policy engine | Submit policy with typo in risk level, verify load-time rejection with clear error message |
| Docker read_only + WAL | Phase 3: Docker deployment | `docker compose down -v && docker compose up -d`, then verify `PRAGMA journal_mode` returns `wal` inside container |
| Audit log immutability | Phase 1: Schema + models | Attempt UPDATE on audit table via API, verify it's rejected at ORM level |
| Webhook callback failures | Phase 2: Event bus + webhooks | Turn off target service, trigger review completion, verify retry queue and eventual delivery |
| Nginx SSE buffering | Phase 3: Nginx config | `curl -N http://192.168.71.140:8090/api/v1/stream`, verify events arrive individually with <100ms delay |
| Backup reliability | Phase 3: Deployment | Run backup script, restore to fresh location, verify all data intact |

## Sources

- [Stack Overflow: Concurrent writes in SQLite with FastAPI + SQLAlchemy](https://stackoverflow.com/questions/79707043/how-to-make-concurrent-writes-in-sqlite-with-fastapi-sqlalchemy-without-datab) -- Verified solution: aiosqlite + WAL mode
- [SQLite WAL documentation](https://www.sqlite.org/wal.html) -- Official WAL mode behavior and limitations
- [FastAPI Issue #1624: Memory usage piles up over time](https://github.com/fastapi/fastapi/issues/1624) -- Known FastAPI memory behavior under sustained load
- [sse-starlette library](https://github.com/sysid/sse-starlette) -- Production SSE implementation for FastAPI
- [HTMX SSE Extension Issue #134: Error handling gaps](https://github.com/bigskysoftware/htmx-extensions/issues/134) -- Known bug with SSE extension error handling
- [HTMX SSE Extension Issue #143: Connection limits](https://github.com/bigskysoftware/htmx-extensions/issues/143) -- HTTP/1.1 SSE connection limit discussion
- [Closing SSE Connections: Browser Compatibility](https://blog.apartment304.com/sse-close-connection/) -- Browser-specific SSE cleanup behavior
- [Beekeeper Studio: SQLite "database is locked" guide](https://www.beekeeperstudio.io/blog/how-to-solve-sqlite-database-is-locked-error) -- Comprehensive concurrency troubleshooting
- [django-fsm-2: Optimistic locking for state transitions](https://github.com/django-commons/django-fsm-2) -- Reference implementation of concurrent transition protection
- [FastAPI Discussion #13009: Gunicorn worker memory limits](https://github.com/fastapi/discussions/13009) -- Worker recycling strategies for memory management
- [CNCF: OPA Best Practices for Secure Deployment](https://www.cncf.io/blog/2025/03/18/open-policy-agent-best-practices-for-a-secure-deployment/) -- Policy engine production pitfalls
- [YAML: The Silent Killer of DevOps Pipelines](https://automatic.co/blog/yaml-the-silent-killer-of-devops-pipelines) -- YAML validation and testing strategies
- [Stack Overflow: Docker read-only filesystem + tmpfs](https://stackoverflow.com/questions/68933848/how-to-allow-container-with-read-only-root-filesystem-writing-to-tmpfs-volume) -- Read-only container volume patterns
- [HTMX CSRF Issue #3379](https://github.com/bigskysoftware/htmx/issues/3379) -- CSRF token + hx-boost interaction bug

---
*Pitfalls research for: AI Production Pipeline Review/Governance Platform*
*Researched: 2026-05-05*
