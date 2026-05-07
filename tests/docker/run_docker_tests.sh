#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Docker Stack Integration Tests -- DOCK-01 through DOCK-07
#
# Standalone bash test script that verifies the full Docker Compose stack
# as a black-box system through Nginx.
#
# Dependencies: bash, curl, jq, docker
# Usage: ./tests/docker/run_docker_tests.sh
# =============================================================================

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL="${BASE_URL:-http://localhost:8090}"
API_KEY="${API_KEY:-CHANGE-ME-USE-openssl-rand-hex-32}"
API_CONTAINER="review-api"
NGINX_CONTAINER="review-nginx"
REDIS_CONTAINER="review-redis"

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
pass() {
    PASS=$((PASS + 1))
    echo "  PASS: $1"
}

fail() {
    FAIL=$((FAIL + 1))
    echo "  FAIL: $1"
}

get_auth_token() {
    local response
    response=$(curl -s -f -X POST \
        -H "Content-Type: application/json" \
        -d "{\"api_key\":\"${API_KEY}\",\"client_id\":\"docker-test\"}" \
        "${BASE_URL}/api/v1/auth/token" 2>/dev/null)

    if [[ -z "$response" ]]; then
        echo "ERROR: Auth token request failed (empty response)" >&2
        exit 1
    fi

    local token
    token=$(echo "$response" | jq -r '.data.access_token // empty')

    if [[ -z "$token" ]]; then
        echo "ERROR: Failed to extract auth token from response: $response" >&2
        exit 1
    fi

    echo "$token"
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight_check() {
    echo ""
    echo "=== Pre-flight checks ==="

    # Verify Docker daemon is running
    if ! docker info > /dev/null 2>&1; then
        echo "ERROR: Docker daemon is not running" >&2
        exit 1
    fi
    echo "  Docker daemon is running"

    # Verify all required containers are running
    local running
    running=$(docker ps --format '{{.Names}}')

    for container in "$API_CONTAINER" "$NGINX_CONTAINER" "$REDIS_CONTAINER"; do
        if ! echo "$running" | grep -q "^${container}$"; then
            echo "ERROR: Container '$container' is not running" >&2
            exit 1
        fi
        echo "  Container '$container' is running"
    done

    # Wait for API health
    echo "  Waiting for API health endpoint..."
    local attempt=0
    local max_attempts=30
    while [[ $attempt -lt $max_attempts ]]; do
        if curl -s -f -o /dev/null "${BASE_URL}/health" 2>/dev/null; then
            echo "  Stack is healthy"
            echo "  Pre-flight checks passed"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    echo "ERROR: API health check timed out after $((max_attempts * 2)) seconds" >&2
    exit 1
}

# ---------------------------------------------------------------------------
# DOCK-01: API responds through Nginx at /health with 200
# ---------------------------------------------------------------------------
test_dock01() {
    echo ""
    echo "--- DOCK-01: Health endpoint returns HTTP 200 through Nginx ---"

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")

    if [[ "$http_code" == "200" ]]; then
        pass "DOCK-01: /health returned HTTP 200"
    else
        fail "DOCK-01: /health returned HTTP $http_code (expected 200)"
    fi
}

# ---------------------------------------------------------------------------
# DOCK-02: Health response contains status=ok, redis=ok, database=ok
# ---------------------------------------------------------------------------
test_dock02() {
    echo ""
    echo "--- DOCK-02: Health response has all dependency status ok ---"

    local response
    response=$(curl -s "${BASE_URL}/health")

    local status_val redis_val db_val
    status_val=$(echo "$response" | jq -r '.status // empty')
    redis_val=$(echo "$response" | jq -r '.redis // empty')
    db_val=$(echo "$response" | jq -r '.database // empty')

    # Verify all keys present
    local keys_ok=true
    if [[ "$status_val" == "" ]]; then
        fail "DOCK-02: Response missing 'status' key"
        keys_ok=false
    fi
    if [[ "$redis_val" == "" ]]; then
        fail "DOCK-02: Response missing 'redis' key"
        keys_ok=false
    fi
    if [[ "$db_val" == "" ]]; then
        fail "DOCK-02: Response missing 'database' key"
        keys_ok=false
    fi

    if [[ "$keys_ok" == "true" ]]; then
        # Verify all values are "ok"
        if [[ "$status_val" == "ok" && "$redis_val" == "ok" && "$db_val" == "ok" ]]; then
            pass "DOCK-02: All dependencies ok (status=$status_val, redis=$redis_val, database=$db_val)"
        else
            fail "DOCK-02: Degraded status (status=$status_val, redis=$redis_val, database=$db_val)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# DOCK-03: Redis-dependent features work (token generation + cross-verify)
# ---------------------------------------------------------------------------
test_dock03() {
    echo ""
    echo "--- DOCK-03: Redis-dependent features work end-to-end ---"

    # Step 1: Get auth token
    local token
    token=$(get_auth_token)

    # Step 2: Submit a review
    local submit_response
    submit_response=$(curl -s -f -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d '{"type":"video","content_ref":"docker-test://test-content","source_system":"docker-test","priority":"normal","risk_score":0.3}' \
        "${BASE_URL}/api/v1/reviews/")

    local review_id
    review_id=$(echo "$submit_response" | jq -r '.data.review_id // empty')
    if [[ -z "$review_id" ]]; then
        fail "DOCK-03: Failed to submit review (response: $submit_response)"
        return
    fi
    echo "  Submitted review_id=$review_id"

    # Step 3: Generate review token (requires Redis)
    local token_response
    token_response=$(curl -s -f -X POST \
        -H "Authorization: Bearer ${token}" \
        "${BASE_URL}/api/v1/reviews/${review_id}/token")

    local review_token
    review_token=$(echo "$token_response" | jq -r '.data.token // empty')
    if [[ -z "$review_token" ]]; then
        fail "DOCK-03: Failed to generate review token (response: $token_response)"
        return
    fi
    echo "  Generated review token: $review_token"

    # Step 4: Cross-verify in Redis via docker exec
    local redis_val
    redis_val=$(docker exec "$REDIS_CONTAINER" redis-cli GET "review_token:${review_token}")

    if [[ "$redis_val" == "$review_id" ]]; then
        pass "DOCK-03: Token stored in Redis correctly (review_token:$review_token -> $redis_val)"
    else
        fail "DOCK-03: Redis value mismatch (expected=$review_id, got=$redis_val)"
    fi
}

# ---------------------------------------------------------------------------
# DOCK-04: SSE connections work through Nginx with correct content-type
# ---------------------------------------------------------------------------
test_dock04() {
    echo ""
    echo "--- DOCK-04: SSE connections establish through Nginx ---"

    local token
    token=$(get_auth_token)

    # Check 1: SSE endpoint returns HTTP 200
    local sse_output
    sse_output=$(timeout 8 curl -s -N --max-time 10 \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: text/event-stream" \
        -w "\nHTTP_CODE:%{http_code}" \
        "${BASE_URL}/api/v1/events/stream" 2>&1 || true)

    local http_code
    http_code=$(echo "$sse_output" | grep "HTTP_CODE:" | sed 's/HTTP_CODE://')

    if [[ "$http_code" == "200" ]]; then
        pass "DOCK-04: SSE stream returned HTTP 200"
    else
        fail "DOCK-04: SSE stream returned HTTP $http_code (expected 200)"
    fi

    # Check 2: Content-Type is text/event-stream
    local content_type
    content_type=$(curl -s -I --max-time 5 \
        -H "Authorization: Bearer ${token}" \
        "${BASE_URL}/api/v1/events/stream" 2>/dev/null | grep -i "content-type" || true)

    if echo "$content_type" | grep -qi "text/event-stream"; then
        pass "DOCK-04: SSE Content-Type is text/event-stream"
    else
        fail "DOCK-04: SSE Content-Type is not text/event-stream (got: $content_type)"
    fi
}

# ---------------------------------------------------------------------------
# DOCK-05: Total container memory under 400MB
# ---------------------------------------------------------------------------
test_dock05() {
    echo ""
    echo "--- DOCK-05: Total container memory under 400MB ---"

    local total_mib=0

    for container in "$API_CONTAINER" "$NGINX_CONTAINER" "$REDIS_CONTAINER"; do
        local mem_usage
        mem_usage=$(docker stats --no-stream --format "{{.MemUsage}}" "$container" 2>/dev/null)

        local mem_val
        mem_val=$(echo "$mem_usage" | awk '{print $1}')

        local mem_num unit
        mem_num=$(echo "$mem_val" | sed 's/[^0-9.]//g')
        unit=$(echo "$mem_val" | sed 's/[0-9.]//g')

        local mem_mib=0
        if [[ "$unit" == "GiB" || "$unit" == "GB" ]]; then
            mem_mib=$(echo "$mem_num * 1024" | bc)
        elif [[ "$unit" == "MiB" || "$unit" == "MB" ]]; then
            mem_mib="$mem_num"
        elif [[ "$unit" == "KiB" || "$unit" == "kB" ]]; then
            mem_mib=$(echo "$mem_num / 1024" | bc -l)
        elif [[ "$unit" == "B" ]]; then
            mem_mib=$(echo "$mem_num / 1024 / 1024" | bc -l)
        fi

        # Use awk for floating-point addition
        total_mib=$(echo "$total_mib + $mem_mib" | bc -l)
        echo "  $container: $mem_val"
    done

    local total_int
    total_int=$(printf "%.1f" "$total_mib")

    if (( $(echo "$total_mib < 400" | bc -l) )); then
        pass "DOCK-05: Total memory ${total_int}MiB < 400MiB limit"
    else
        fail "DOCK-05: Total memory ${total_int}MiB >= 400MiB limit"
    fi
}

# ---------------------------------------------------------------------------
# DOCK-06: API container filesystem is read-only
# ---------------------------------------------------------------------------
test_dock06() {
    echo ""
    echo "--- DOCK-06: API container filesystem is read-only ---"

    local all_pass=true

    # Check 1: docker inspect shows ReadonlyRootfs=true
    local readonly_flag
    readonly_flag=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$API_CONTAINER" 2>/dev/null)

    if [[ "$readonly_flag" == "true" ]]; then
        pass "DOCK-06: ReadonlyRootfs is true"
    else
        fail "DOCK-06: ReadonlyRootfs is '$readonly_flag' (expected true)"
        all_pass=false
    fi

    # Check 2: Attempt to write to root filesystem should fail
    local write_result
    write_result=$(docker exec "$API_CONTAINER" touch /test_write 2>&1 || true)

    if echo "$write_result" | grep -qi "read-only"; then
        pass "DOCK-06: Write to /test_write correctly blocked (read-only filesystem)"
    else
        fail "DOCK-06: Write to /test_write was not blocked (output: $write_result)"
        all_pass=false
    fi
}

# ---------------------------------------------------------------------------
# DOCK-07: API process runs as non-root (appuser)
# ---------------------------------------------------------------------------
test_dock07() {
    echo ""
    echo "--- DOCK-07: API process runs as non-root user ---"

    local all_pass=true

    # Check 1: docker exec whoami returns appuser
    local whoami_result
    whoami_result=$(docker exec "$API_CONTAINER" whoami 2>/dev/null || echo "")

    if [[ "$whoami_result" == "appuser" ]]; then
        pass "DOCK-07: Running user is 'appuser' (whoami)"
    else
        fail "DOCK-07: Running user is '$whoami_result' (expected appuser)"
        all_pass=false
    fi

    # Check 2: docker inspect Config.User returns appuser
    local config_user
    config_user=$(docker inspect --format '{{.Config.User}}' "$API_CONTAINER" 2>/dev/null)

    if [[ "$config_user" == "appuser" ]]; then
        pass "DOCK-07: Container configured user is 'appuser' (Config.User)"
    else
        fail "DOCK-07: Container configured user is '$config_user' (expected appuser)"
        all_pass=false
    fi
}

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
echo "============================================"
echo "Docker Stack Integration Tests"
echo "Base URL: $BASE_URL"
echo "============================================"

preflight_check
test_dock01
test_dock02
test_dock03
test_dock04
test_dock05
test_dock06
test_dock07

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS + FAIL))
echo ""
echo "============================================"
echo "Results: $PASS passed, $FAIL failed, $TOTAL total"
echo "============================================"

if [[ $FAIL -eq 0 ]]; then
    exit 0
else
    exit 1
fi
