"""Playwright E2E test fixtures — starts FastAPI app with Docker PostgreSQL."""

import os
import re
import subprocess
import sys
import time

import pytest
from playwright.sync_api import Page, Route


PORT = 8199
POSTGRES_IP = "172.19.0.4"
POSTGRES_URL = f"postgresql+asyncpg://review:review2026@{POSTGRES_IP}:5432/reviewdb"
REDIS_URL = "redis://172.19.0.3:6379/0"


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1440, "height": 900},
    }


@pytest.fixture(scope="session")
def _server_process():
    """Start FastAPI app as subprocess for E2E testing."""
    venv_python = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "bin", "python")
    )
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )

    proc = subprocess.Popen(
        [
            venv_python, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--workers", "4",
            "--log-level", "warning",
            "--timeout-keep-alive", "5",
        ],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "API_KEY": "",
            "JWT_SECRET": "test-jwt-secret-for-e2e-testing-min-32-chars-long",
            "POSTGRES_URL": POSTGRES_URL,
            "REDIS_URL": REDIS_URL,
            "DATABASE_URL": "sqlite+aiosqlite:///./test_e2e.db",
            "LOG_LEVEL": "WARNING",
        },
    )

    import urllib.request
    import urllib.error

    base = f"http://localhost:{PORT}"
    for _ in range(30):
        try:
            resp = urllib.request.urlopen(f"{base}/health", timeout=2)
            if resp.status in (200, 503):
                break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(1)
    else:
        proc.terminate()
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        raise RuntimeError(f"Server failed to start on port {PORT}:\n{stderr}")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(autouse=True)
def _ensure_server(_server_process):
    pass


@pytest.fixture(autouse=True)
def block_long_lived_connections(page: Page):
    """Block SSE streams and mobile card API calls that hang the server."""
    page.route("**/events/stream", lambda r: r.fulfill(
        status=200, content_type="text/event-stream", body=""))
    page.route(re.compile(r".*/api/v1/mobile/cards.*"), lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"status":"ok","data":{"items":[],"has_more":false}}'))
    yield
