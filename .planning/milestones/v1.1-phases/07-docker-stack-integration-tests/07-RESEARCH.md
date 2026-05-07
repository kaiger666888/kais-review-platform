# Phase 07: Docker Stack Integration Tests - Research

**Researched:** 2026-05-07
**Domain:** Docker Compose black-box integration testing (HTTP + Docker CLI)
**Confidence:** HIGH

## Summary

Phase 07 tests the full Docker Compose deployment as a black-box system. Tests hit `http://localhost:8090` (Nginx external port) using `curl`/`jq` for HTTP assertions and `docker exec`/`docker stats`/`docker inspect` for container-level verification. This is fundamentally different from Phase 06 which used `httpx.AsyncClient` with ASGI transport -- these tests require a running Docker Compose stack.

The test script is a standalone bash script (not pytest) that orchestrates: (1) verify the stack is running, (2) run HTTP tests through Nginx, (3) run Redis-dependent tests via API, (4) test SSE streaming through Nginx proxy, (5) verify container memory and security constraints. Each requirement (DOCK-01 through DOCK-07) maps to a discrete test function with clear pass/fail output.

**Primary recommendation:** Write a single `tests/docker/run_docker_tests.sh` bash script using `curl` + `jq` + `docker` CLI. Each test is a bash function that returns 0/1 and prints PASS/FAIL. The script reports summary at end.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion -- this is a Docker black-box testing phase with well-defined requirements (DOCK-01 through DOCK-07).

Key guidelines:
- Tests are NOT pytest -- they are standalone scripts (bash or Python) that require Docker Compose to be running
- Tests hit http://localhost:8090 (or the configured external port) through Nginx
- Use docker stats for memory verification, docker exec for filesystem/user checks
- Tests should be runnable independently after `docker compose up -d`
- Test script should report pass/fail per requirement

### Claude's Discretion
All implementation choices are at Claude's discretion.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOCK-01 | API responds to /api/v1/health through Nginx reverse proxy | Health endpoint at `/health` proxied via Nginx `location /health` block. Use `curl -s http://localhost:8090/health` and verify 200 status code. Note: Nginx config proxies `/health` not `/api/v1/health`. |
| DOCK-02 | Health check returns 200 with all dependencies healthy, 503 with degraded status | Health endpoint checks Redis and SQLite, returns `{"status":"ok","redis":"ok","database":"ok"}` with 200, or `{"status":"degraded",...}` with 503. Test with `curl` + `jq` parsing. |
| DOCK-03 | Redis connectivity confirmed through API (state transitions, token operations) | Token generation at `POST /api/v1/reviews/{id}/token` requires Redis. Full flow: submit review, get auth token, generate review token, verify it's stored in Redis. Use `docker exec review-redis redis-cli GET review_token:{token}` to cross-verify. |
| DOCK-04 | SSE connections work through Nginx with long-lived connection support | Nginx config has dedicated `/events/stream` location with `proxy_buffering off; proxy_read_timeout 86400s`. Test by connecting with `curl -N -H "Authorization: Bearer {jwt}"` and verifying headers + event data. Must use cookie-auth `/events/stream` or Bearer auth `/api/v1/events/stream`. |
| DOCK-05 | Total container memory usage stays under 400MB limit | `docker stats --no-stream --format "{{.MemUsage}}"` for each running container. Parse MiB/GiB values, sum them, verify < 400MB. Limits: api=256M, nginx=32M, redis=64M. |
| DOCK-06 | API container filesystem is read_only (write attempts fail) | Two approaches: (1) `docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' review-api` returns `true`. (2) `docker exec review-api touch /test_write 2>&1` should fail with "Read-only file system". Note: `/tmp` is tmpfs so writes there succeed. |
| DOCK-07 | API process runs as non-root user | `docker exec review-api id` or `docker exec review-api whoami` should show `appuser` / uid 1000. Cross-check with `docker inspect --format '{{.Config.User}}' review-api` returning `appuser`. |
</phase_requirements>

## Standard Stack

### Core (Test Infrastructure)

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| bash | 5.x | Test script runtime | Available on all Linux, process control, curl pipe support |
| curl | 8.5.0 | HTTP requests against Nginx | Installed, supports `-N` (no-buffer) for SSE streaming |
| jq | 1.7 | JSON response parsing | Installed, handles API health/submit responses |
| docker CLI | 29.4.1 | Container inspection, stats, exec | Installed, all container-level verification |
| docker compose | 5.1.3 | Stack lifecycle management | Installed, compose file parsing |

### Supporting (Available in Environment)

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| python3 | 3.12.3 | Alternative test runner (if bash proves insufficient) | Fallback for complex SSE or async flows |
| httpx | 0.28.1 | Python HTTP client | Python-based test approach |
| nc | netcat | Port connectivity checks | Quick pre-flight port check |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| bash + curl | Python + httpx script | Python has better SSE/streaming support but adds dependency; bash is universally available and simpler for sequential HTTP assertions |
| Single bash script | Multiple test files | Single script is simpler to run, matches CONTEXT.md guidance of standalone script |
| curl -N for SSE | Python asyncio + httpx stream | Python has proper async SSE parsing but bash `curl -N --max-time` is sufficient for connection + first-event verification |

**Installation:**
```bash
# No installation needed - all tools verified present in environment
# curl 8.5.0, jq 1.7, docker 29.4.1, docker compose 5.1.3, bash
```

## Architecture Patterns

### Recommended Test Structure

```
tests/
└── docker/
    ├── run_docker_tests.sh    # Main test runner (entry point)
    └── lib/                   # Optional: sourced helper functions
        ├── http_helpers.sh    # curl wrappers, JWT generation
        └── docker_helpers.sh  # stats parsing, inspect helpers
```

### Pattern 1: Bash Test Function with Pass/Fail

**What:** Each requirement is a bash function that returns 0 (pass) or 1 (fail) and prints labeled output.

**When to use:** Every DOCK-XX test.

**Example:**
```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8090"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; ((PASS++)); }
fail() { echo "  FAIL: $1"; ((FAIL++)); }

test_dock01_health_through_nginx() {
    echo "DOCK-01: API responds to /health through Nginx"
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
    if [[ "$status" == "200" ]]; then
        pass "Health endpoint returns 200"
    else
        fail "Expected 200, got $status"
    fi
}
```

### Pattern 2: Authenticated API Call Sequence

**What:** Get JWT token first, then use it for subsequent API calls.

**When to use:** DOCK-02 (full health check), DOCK-03 (Redis-dependent), DOCK-04 (SSE).

**Example:**
```bash
# Step 1: Get JWT token
get_auth_token() {
    local response
    response=$(curl -s -X POST "$BASE_URL/api/v1/auth/token" \
        -H "Content-Type: application/json" \
        -d "{\"api_key\": \"$API_KEY\", \"client_id\": \"docker-test\"}")
    echo "$response" | jq -r '.data.access_token'
}
```

### Pattern 3: Docker Stats Memory Parsing

**What:** Parse `docker stats --no-stream` output to extract memory in MiB.

**When to use:** DOCK-05.

**Example:**
```bash
get_container_memory_mib() {
    local container="$1"
    local mem_usage
    mem_usage=$(docker stats --no-stream --format "{{.MemUsage}}" "$container")
    # Parse "XX.XXMiB / 256MiB" format
    local mem_value
    mem_value=$(echo "$mem_usage" | awk '{print $1}')
    # Handle MiB and GiB suffixes
    if echo "$mem_value" | grep -q "GiB"; then
        echo "$mem_value" | sed 's/GiB//' | awk '{printf "%.0f", $1 * 1024}'
    else
        echo "$mem_value" | sed 's/MiB//' | awk '{printf "%.0f", $1}'
    fi
}
```

### Pattern 4: SSE Connection Test via curl

**What:** Use `curl -N` (no-buffer) with `--max-time` to connect to SSE endpoint and read events.

**When to use:** DOCK-04.

**Example:**
```bash
test_sse_through_nginx() {
    echo "DOCK-04: SSE connections work through Nginx"
    local token
    token=$(get_auth_token)

    # Connect to SSE stream with timeout, capture headers + first event
    local output
    output=$(curl -s -N --max-time 10 \
        -H "Authorization: Bearer $token" \
        -H "Accept: text/event-stream" \
        -w "\nHTTP_STATUS:%{http_code}" \
        "$BASE_URL/api/v1/events/stream" 2>&1) || true

    local http_status
    http_status=$(echo "$output" | grep "HTTP_STATUS:" | sed 's/HTTP_STATUS://')

    if [[ "$http_status" == "200" ]]; then
        # Verify content-type header
        local content_type
        content_type=$(curl -s -I -N --max-time 5 \
            -H "Authorization: Bearer $token" \
            "$BASE_URL/api/v1/events/stream" 2>&1 | grep -i "content-type" || true)
        if echo "$content_type" | grep -q "text/event-stream"; then
            pass "SSE endpoint returns text/event-stream through Nginx"
        else
            fail "Expected text/event-stream content type"
        fi
    else
        fail "SSE endpoint returned $http_status, expected 200"
    fi
}
```

### Anti-Patterns to Avoid

- **Using pytest with subprocess:** This phase explicitly calls for standalone scripts, not pytest wrapping Docker commands. The tests operate at a different level (running infrastructure, not in-process code).
- **Hardcoding localhost:8090:** Use `BASE_URL` variable with fallback from environment: `BASE_URL="${BASE_URL:-http://localhost:8090}"`.
- **Assuming Docker stack is running:** Test script should check stack health first and fail fast with a clear message if containers are not up.
- **Testing `/tmp` writes for read-only check:** The docker-compose.yml mounts tmpfs at `/tmp`, so writes to `/tmp` will succeed even in a `read_only: true` container. Test writes to non-tmpfs paths like `/test_write` or `/app/test`.
- **Ignoring Nginx routing:** The Nginx config routes `/health` (not `/api/v1/health`) directly. Tests must use the Nginx-mapped paths, not the direct API paths.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON parsing | Custom string matching | `jq` | jq handles nested JSON, arrays, null values correctly. String matching is fragile. |
| Memory unit conversion | Custom MiB/GiB parser | `awk` with conditional logic | Docker stats output varies (MiB vs GiB), awk handles both reliably. |
| SSE stream reading | Custom TCP socket code | `curl -N --max-time` | curl handles HTTP chunked encoding, connection keep-alive, and SSE protocol. |
| Container state queries | Parsing docker ps text output | `docker inspect --format` | Go template format is stable and documented, text output may change. |

**Key insight:** All the tools needed (curl, jq, docker) are already installed in the environment. No dependencies to install.

## Common Pitfalls

### Pitfall 1: Health Endpoint Path Mismatch

**What goes wrong:** Testing `/api/v1/health` through Nginx but Nginx only proxies `/health`.
**Why it happens:** The FastAPI app defines `@app.get("/health")` (not under `/api/v1/` prefix). The Nginx config has `location /health { proxy_pass http://api; }`.
**How to avoid:** Always use `http://localhost:8090/health` (Nginx path), not `http://localhost:8090/api/v1/health`.
**Warning signs:** 404 response when testing health through Nginx.

### Pitfall 2: SSE Requires Auth, But EventSource Uses Cookies

**What goes wrong:** Trying to connect to `/events/stream` with Bearer auth header, but the cookie-auth SSE endpoint at `/events/stream` requires a cookie, not a header.
**Why it happens:** There are TWO SSE endpoints: `/api/v1/events/stream` (Bearer JWT) and `/events/stream` (cookie JWT). The `/events/stream` endpoint reads `access_token` from cookies.
**How to avoid:** For Docker testing, use the Bearer auth endpoint `/api/v1/events/stream` with `Authorization: Bearer {jwt}` header. The Nginx config has a dedicated location for `/events/stream` (cookie-based) but `/api/v1/events/stream` goes through the general `/api/` location which also works for SSE.
**Warning signs:** 401 response when connecting to SSE with correct JWT.

### Pitfall 3: Timing -- Stack Not Ready

**What goes wrong:** Tests run immediately after `docker compose up -d` but API container hasn't finished startup.
**Why it happens:** The API container depends on Redis health check, then runs its own health check (30s interval, 10s start period). Startup can take 15-30 seconds.
**How to avoid:** Implement a wait-for-healthy loop that polls `http://localhost:8090/health` with retries before running tests.
**Warning signs:** Connection refused or 502 Bad Gateway on first test.

### Pitfall 4: Memory Stats Timing

**What goes wrong:** Checking memory immediately after stack starts, getting artificially low readings.
**Why it happens:** Docker memory stats include page cache and can be misleading during warm-up.
**How to avoid:** Run a few API requests first (health check, submit review) to warm up the application, THEN capture memory stats. This gives more realistic numbers.
**Warning signs:** Memory shows ~5MB total which is unrealistic for a running Python app.

### Pitfall 5: /tmp is tmpfs in read_only Container

**What goes wrong:** Testing `docker exec review-api touch /tmp/testfile` to verify read_only, but it succeeds because `/tmp` is mounted as tmpfs.
**Why it happens:** The docker-compose.yml has `tmpfs: - /tmp` which creates a writable tmpfs mount inside the read_only container. This is intentional for temporary files.
**How to avoid:** Test writes to a non-tmpfs path like `/app/test_write` or `/test_write`. Or use `docker inspect --format '{{.HostConfig.ReadonlyRootfs}}'` to verify the flag is set.
**Warning signs:** Read-only test passes even though container is read_only.

### Pitfall 6: Container Names Must Match docker-compose.yml

**What goes wrong:** Using wrong container names in `docker exec` or `docker stats` commands.
**Why it happens:** Container names are set by `container_name` in docker-compose.yml: `review-api`, `review-nginx`, `review-redis`.
**How to avoid:** Use exact names from docker-compose.yml. Define them as variables at top of script: `API_CONTAINER="review-api"`, `REDIS_CONTAINER="review-redis"`, `NGINX_CONTAINER="review-nginx"`.
**Warning signs:** "No such container" errors.

## Code Examples

### Complete Authenticated API Call Sequence

```bash
# Source: Derived from app/api/v1/auth.py and app/core/auth.py

API_KEY="${API_KEY:-$(grep API_KEY .env.production | cut -d= -f2)}"

# Get JWT token via API key exchange
TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/auth/token" \
    -H "Content-Type: application/json" \
    -d "{\"api_key\": \"$API_KEY\", \"client_id\": \"docker-test\"}" \
    | jq -r '.data.access_token')

# Use token for authenticated requests
SUBMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/reviews/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "type": "video",
        "content_ref": "docker-test://test-content",
        "source_system": "docker-test",
        "priority": "normal",
        "risk_score": 0.3
    }')

REVIEW_ID=$(echo "$SUBMIT_RESPONSE" | jq -r '.data.review_id')
```

### Redis Token Cross-Verification (DOCK-03)

```bash
# Source: Derived from app/core/auth.py create_review_token

# Generate a review token via API
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/reviews/$REVIEW_ID/token" \
    -H "Authorization: Bearer $TOKEN")
REVIEW_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.data.token')

# Cross-verify in Redis container
REDIS_VALUE=$(docker exec review-redis redis-cli GET "review_token:$REVIEW_TOKEN")
if [[ "$REDIS_VALUE" == "$REVIEW_ID" ]]; then
    pass "Token stored in Redis correctly"
else
    fail "Token not found in Redis (expected=$REVIEW_ID, got=$REDIS_VALUE)"
fi
```

### Container Security Verification (DOCK-06, DOCK-07)

```bash
# Source: Docker Compose v2 and Docker CLI documentation

# DOCK-06: Verify read_only filesystem
READONLY=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' review-api)
if [[ "$READONLY" == "true" ]]; then
    pass "API container has read-only root filesystem"
else
    fail "API container root filesystem is NOT read-only"
fi

# Functional test: write to non-tmpfs path should fail
WRITE_OUTPUT=$(docker exec review-api touch /test_write 2>&1) || true
if echo "$WRITE_OUTPUT" | grep -qi "read-only"; then
    pass "Write attempt correctly rejected on read-only filesystem"
else
    fail "Write attempt did not fail as expected: $WRITE_OUTPUT"
fi

# DOCK-07: Verify non-root user
CONTAINER_USER=$(docker exec review-api whoami)
if [[ "$CONTAINER_USER" == "appuser" ]]; then
    pass "API process runs as non-root user (appuser)"
else
    fail "API process runs as: $CONTAINER_USER (expected: appuser)"
fi
```

### SSE Connection Verification (DOCK-04)

```bash
# Source: nginx/nginx.conf proxy_read_timeout 86400s + app/api/v1/events.py

# SSE through Bearer-auth endpoint (/api/v1/events/stream)
# -N disables curl buffering (essential for SSE)
# --max-time limits how long we listen
SSE_OUTPUT=$(timeout 8 curl -s -N \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: text/event-stream" \
    -w "\nHTTP_CODE:%{http_code}" \
    "$BASE_URL/api/v1/events/stream" 2>&1) || true

SSE_HTTP=$(echo "$SSE_OUTPUT" | grep "HTTP_CODE:" | sed 's/HTTP_CODE://')
if [[ "$SSE_HTTP" == "200" ]]; then
    pass "SSE connection accepted through Nginx (200 OK)"
else
    fail "SSE connection failed with HTTP $SSE_HTTP"
fi

# Verify it's actually event-stream content (not buffered/errored)
# The SSE stream should send heartbeat comments within 30 seconds
# With --max-time 8 and 30s heartbeat interval, we might not get a heartbeat
# but we should at least verify the connection stays open (no immediate close)
```

### Memory Summation (DOCK-05)

```bash
# Source: Docker CLI stats command documentation

TOTAL_MIB=0
for container in review-api review-nginx review-redis; do
    MEM_USAGE=$(docker stats --no-stream --format "{{.MemUsage}}" "$container")
    MEM_VALUE=$(echo "$MEM_USAGE" | awk '{print $1}')

    if echo "$MEM_VALUE" | grep -q "GiB"; then
        MIB=$(echo "$MEM_VALUE" | sed 's/GiB//' | awk '{printf "%.0f", $1 * 1024}')
    elif echo "$MEM_VALUE" | grep -q "MiB"; then
        MIB=$(echo "$MEM_VALUE" | sed 's/MiB//' | awk '{printf "%.0f", $1}')
    else
        MIB=0
    fi
    TOTAL_MIB=$((TOTAL_MIB + MIB))
done

if [[ $TOTAL_MIB -lt 400 ]]; then
    pass "Total memory usage: ${TOTAL_MIB}MiB < 400MiB limit"
else
    fail "Total memory usage: ${TOTAL_MIB}MiB exceeds 400MiB limit"
fi
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| docker-compose v1 (python) | docker compose v2 (Go plugin) | 2020-2023 | Use `docker compose` not `docker-compose` |
| Parsing docker ps output | `docker inspect --format` (Go templates) | Stable | Go template format is the reliable way to extract container config |
| aioredis package | redis.asyncio (merged into redis-py) | redis-py 4.2+ | DOCK-03 verifies the merged package works end-to-end |

**Deprecated/outdated:**
- `docker-compose` (hyphenated): Use `docker compose` (space, v2 plugin). The environment has v5.1.3.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | All DOCK tests | Yes | 29.4.1 | -- |
| Docker Compose v2 | Stack management | Yes | 5.1.3 | -- |
| curl | HTTP requests | Yes | 8.5.0 | -- |
| jq | JSON parsing | Yes | 1.7 | -- |
| bash | Test script runtime | Yes | 5.x | -- |
| python3 | Alternative test runner | Yes | 3.12.3 | Use bash primarily |
| httpx CLI | Alternative HTTP client | Yes | 0.28.1 | Use curl primarily |
| nc (netcat) | Port pre-check | Yes | -- | Use curl instead |

**Missing dependencies with no fallback:**
- None. All required tools are present.

**Missing dependencies with fallback:**
- None needed. The bash + curl + jq + docker CLI stack is complete.

## Pre-Flight Checks

The test script needs to verify the Docker stack is running before executing tests. Key checks:

```bash
# Check Docker daemon
docker info > /dev/null 2>&1 || { echo "ERROR: Docker daemon not running"; exit 1; }

# Check stack containers exist and are running
for container in review-api review-nginx review-redis; do
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "ERROR: Container $container is not running. Run: docker compose up -d"
        exit 1
    fi
done

# Wait for API health (Nginx might return 502 while API starts)
echo "Waiting for stack to be healthy..."
for i in $(seq 1 30); do
    if curl -sf "$BASE_URL/health" > /dev/null 2>&1; then
        echo "Stack is healthy."
        break
    fi
    sleep 2
done
```

## Open Questions

1. **API_KEY value for testing**
   - What we know: `.env.production` has `API_KEY=CHANGE-ME-USE-openssl-rand-hex-32`. The actual production value is a secret.
   - What's unclear: What value is actually deployed when running `docker compose up -d`.
   - Recommendation: Test script should read from `.env.production` or accept `API_KEY` env var. The placeholder value should work for testing since it matches what the container reads. If the user has customized it, env var override handles that.

2. **SSE heartbeat timing in tests**
   - What we know: SSE sends heartbeat every 30 seconds (asyncio.wait_for timeout). Nginx proxy_read_timeout is 86400s.
   - What's unclear: Whether we can rely on receiving a heartbeat within a reasonable test timeout (10-15 seconds) for DOCK-04.
   - Recommendation: For DOCK-04, verify the SSE connection opens successfully (200 + text/event-stream content-type) rather than waiting for a heartbeat. The test focuses on Nginx proxy support for long-lived connections, not on heartbeat delivery timing.

## Sources

### Primary (HIGH confidence)
- docker-compose.yml -- verified service definitions, container names, memory limits, read_only, tmpfs
- nginx/nginx.conf -- verified proxy routing: /health, /events/stream, /api/, /
- Dockerfile -- verified appuser (UID 1000), non-root USER directive
- app/main.py -- verified health endpoint at GET /health with Redis + SQLite checks
- app/api/v1/auth.py -- verified token exchange endpoint POST /api/v1/auth/token
- app/api/v1/events.py -- verified SSE endpoint at GET /api/v1/events/stream with Bearer auth
- app/web/sse.py -- verified cookie-auth SSE endpoint at GET /events/stream
- app/core/auth.py -- verified token create/consume functions with Redis Lua script
- Environment verification: docker 29.4.1, docker compose 5.1.3, curl 8.5.0, jq 1.7 all present

### Secondary (MEDIUM confidence)
- [Docker Best Practices: Read-Only Containers](https://blog.ploetzli.ch/2025/docker-best-practices-read-only-containers/) -- read_only verification patterns
- [How to Run Read-Only Docker Containers - OneUptime](https://oneuptime.com/blog/post/2026-01-16-docker-read-only-containers/view) -- tmpfs + read_only interaction
- [cURL SSE validation - Stack Overflow](https://stackoverflow.com/questions/31238626/curl-structuring-request-to-validate-server-sent-events) -- curl SSE testing patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools verified present in environment via direct checks
- Architecture: HIGH -- all API endpoints, Nginx routes, and Docker config verified from source code
- Pitfalls: HIGH -- derived from actual codebase analysis (Nginx routing, tmpfs, SSE auth)
- Environment: HIGH -- Docker daemon running, all CLI tools verified

**Research date:** 2026-05-07
**Valid until:** 2026-06-07 (stable -- Docker CLI patterns don't change frequently)
