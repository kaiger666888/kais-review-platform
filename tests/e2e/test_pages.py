"""E2E tests for core page rendering and navigation."""

import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8199"


def goto(page: Page, url: str):
    """Navigate with domcontentloaded + retry on timeout."""
    for attempt in range(3):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            if attempt == 2:
                raise
            page.wait_for_timeout(2000)


class TestLoginPage:
    """Login page rendering and authentication flow."""

    def test_login_page_renders(self, page: Page):
        goto(page, f"{BASE_URL}/login")
        expect(page.locator("h1")).to_contain_text("Login")
        expect(page.locator('button[type="submit"]')).to_contain_text("Enter Dashboard")

    def test_login_without_api_key(self, page: Page):
        goto(page, f"{BASE_URL}/login")
        page.click('button[type="submit"]')
        page.wait_for_url(re.compile(r"/$"), timeout=5000)
        expect(page.locator("h1")).to_contain_text("Kai's Review Platform")

    def test_login_sets_jwt_cookie(self, page: Page):
        goto(page, f"{BASE_URL}/login")
        page.click('button[type="submit"]')
        page.wait_for_url(re.compile(r"/$"), timeout=5000)

        cookies = page.context.cookies()
        token_cookie = [c for c in cookies if c["name"] == "access_token"]
        assert len(token_cookie) == 1, "Expected access_token cookie after login"
        assert token_cookie[0]["httpOnly"] is True


class TestDashboard:
    """Dashboard page with review list and tab navigation."""

    def _login(self, page: Page):
        goto(page, f"{BASE_URL}/login")
        page.click('button[type="submit"]')
        page.wait_for_url(re.compile(r"/"), timeout=5000)

    def test_dashboard_loads_after_login(self, page: Page):
        self._login(page)
        expect(page.locator("h1")).to_contain_text("Kai's Review Platform")

    def test_dashboard_has_bottom_tab_bar(self, page: Page):
        self._login(page)
        nav = page.locator("nav[role='tablist']")
        expect(nav).to_be_visible()
        expect(nav.get_by_role("tab", name="Pending")).to_be_visible()
        expect(nav.get_by_role("tab", name="Approved")).to_be_visible()
        expect(nav.get_by_role("tab", name="Rejected")).to_be_visible()
        expect(nav.get_by_role("tab", name="Analytics")).to_be_visible()

    def test_pending_tab_is_active_on_fresh_load(self, page: Page):
        goto(page, f"{BASE_URL}/?tab=pending")
        pending_tab = page.locator("a[href='/?tab=pending']")
        expect(pending_tab).to_have_attribute("aria-selected", "true")

    def test_approved_tab_navigation(self, page: Page):
        goto(page, f"{BASE_URL}/?tab=pending")
        page.click("a[href='/?tab=approved']")
        page.wait_for_url(re.compile(r"tab=approved"), timeout=5000)
        approved_tab = page.locator("a[href='/?tab=approved']")
        expect(approved_tab).to_have_attribute("aria-selected", "true")

    def test_rejected_tab_navigation(self, page: Page):
        goto(page, f"{BASE_URL}/?tab=pending")
        page.click("a[href='/?tab=rejected']")
        page.wait_for_url(re.compile(r"tab=rejected"), timeout=5000)
        rejected_tab = page.locator("a[href='/?tab=rejected']")
        expect(rejected_tab).to_have_attribute("aria-selected", "true")

    def test_dashboard_has_sse_container(self, page: Page):
        goto(page, f"{BASE_URL}/")
        sse_div = page.locator("[sse-connect]")
        expect(sse_div).to_be_visible()

    def test_dashboard_accessible_without_cookie(self, page: Page):
        """Auth is optional — get_template_user returns default user when no cookie."""
        goto(page, f"{BASE_URL}/")
        expect(page.locator("h1")).to_contain_text("Kai's Review Platform")


class TestWorkstation:
    """Desktop workstation 3-column layout for shot card review."""

    def test_workstation_loads(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        expect(page).to_have_title(re.compile(r"Desktop Workstation"))
        expect(page.locator("h1")).to_contain_text("Desktop Workstation")

    def test_workstation_has_3_column_layout(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        grid = page.locator(".grid-cols-\\[25fr_45fr_30fr\\]")
        expect(grid).to_be_visible()

    def test_workstation_has_shot_queue(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        shot_queue = page.locator("#shot-queue-list")
        expect(shot_queue).to_be_visible()

    def test_workstation_has_decision_panel(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        decision_panel = page.locator("#decision-panel")
        expect(decision_panel).to_be_visible()

    def test_workstation_has_media_preview(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        media_preview = page.locator("#media-preview")
        expect(media_preview).to_be_visible()

    def test_workstation_has_dark_header(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        header = page.locator("header.bg-gray-800")
        expect(header).to_be_visible()

    def test_workstation_accessible_without_auth(self, page: Page):
        """Auth is optional — get_template_user returns default user."""
        goto(page, f"{BASE_URL}/workstation")
        expect(page.locator("h1")).to_contain_text("Desktop Workstation")


class TestMobilePWA:
    """Mobile PWA card-swipe interface."""

    def test_mobile_page_loads(self, page: Page):
        goto(page, f"{BASE_URL}/mobile")
        expect(page).to_have_title(re.compile(r"Review"))

    def test_mobile_has_manifest(self, page: Page):
        goto(page, f"{BASE_URL}/mobile")
        manifest_link = page.locator('link[rel="manifest"]')
        expect(manifest_link).to_have_attribute("href", "/static/manifest.json")

    def test_mobile_has_service_worker_script(self, page: Page):
        goto(page, f"{BASE_URL}/mobile")
        content = page.content()
        assert "serviceWorker" in content

    def test_mobile_dark_background(self, page: Page):
        goto(page, f"{BASE_URL}/mobile")
        body = page.locator("body.bg-gray-900")
        expect(body).to_be_visible()

    def test_mobile_empty_state(self, page: Page):
        goto(page, f"{BASE_URL}/mobile")
        page.wait_for_timeout(2000)
        empty_msg = page.locator("text=No cards to review")
        expect(empty_msg).to_be_visible()

    def test_mobile_accessible_without_auth(self, page: Page):
        """Auth is optional — get_template_user returns default user."""
        goto(page, f"{BASE_URL}/mobile")
        expect(page).to_have_title(re.compile(r"Review"))


class TestAnalyticsDashboard:
    """Analytics dashboard with metrics, routing, and scores."""

    def test_analytics_loads(self, page: Page):
        goto(page, f"{BASE_URL}/analytics")
        expect(page).to_have_title(re.compile(r"Analytics"))
        expect(page.locator("h1")).to_contain_text("Analytics Dashboard")

    def test_analytics_has_date_picker(self, page: Page):
        goto(page, f"{BASE_URL}/analytics")
        date_inputs = page.locator('input[type="date"]')
        expect(date_inputs.nth(0)).to_be_visible()
        expect(date_inputs.nth(1)).to_be_visible()

    def test_analytics_has_refresh_button(self, page: Page):
        goto(page, f"{BASE_URL}/analytics")
        refresh_btn = page.locator("button", has_text="Refresh")
        expect(refresh_btn).to_be_visible()

    def test_analytics_has_quick_select_buttons(self, page: Page):
        goto(page, f"{BASE_URL}/analytics")
        expect(page.locator("button", has_text="Today")).to_be_visible()
        expect(page.locator("button", has_text="7d")).to_be_visible()
        expect(page.locator("button", has_text="30d")).to_be_visible()
        expect(page.locator("button", has_text="All")).to_be_visible()

    def test_analytics_has_three_sections(self, page: Page):
        goto(page, f"{BASE_URL}/analytics")
        expect(page.locator("#analytics-metrics")).to_be_visible()
        expect(page.locator("#analytics-routing")).to_be_visible()
        expect(page.locator("#analytics-scores")).to_be_visible()

    def test_analytics_accessible_without_auth(self, page: Page):
        """Auth is optional — get_template_user returns default user."""
        goto(page, f"{BASE_URL}/analytics")
        expect(page.locator("h1")).to_contain_text("Analytics Dashboard")


class TestAuditCockpit:
    """Audit cockpit with timeline, stats, and policy diff."""

    def test_audit_cockpit_loads(self, page: Page):
        goto(page, f"{BASE_URL}/audit-cockpit")
        expect(page).to_have_title(re.compile(r"Audit"))

    def test_audit_cockpit_accessible_without_auth(self, page: Page):
        """Auth is optional — get_template_user returns default user."""
        goto(page, f"{BASE_URL}/audit-cockpit")
        expect(page).to_have_title(re.compile(r"Audit"))


class TestHealthEndpoint:
    """Health check API endpoint — uses direct HTTP, not page.request."""

    def test_health_returns_ok(self, page: Page):
        resp = page.request.get(f"{BASE_URL}/health", timeout=10000)
        assert resp.status in (200, 503)
        body = resp.json()
        assert "version" in body


class TestNavigation:
    """Cross-page navigation flows."""

    def test_navigate_dashboard_to_workstation(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        expect(page.locator("h1")).to_contain_text("Desktop Workstation")

    def test_navigate_dashboard_to_mobile(self, page: Page):
        goto(page, f"{BASE_URL}/mobile")
        expect(page).to_have_title(re.compile(r"Review"))

    def test_navigate_dashboard_to_analytics_via_tab(self, page: Page):
        goto(page, f"{BASE_URL}/")
        page.click("a[href='/analytics']")
        page.wait_for_url(re.compile(r"/analytics"), timeout=5000)
        expect(page.locator("h1")).to_contain_text("Analytics Dashboard")

    def test_navigate_between_all_pages(self, page: Page):
        goto(page, f"{BASE_URL}/workstation")
        expect(page.locator("h1")).to_contain_text("Desktop Workstation")

        goto(page, f"{BASE_URL}/mobile")
        expect(page).to_have_title(re.compile(r"Review"))

        goto(page, f"{BASE_URL}/analytics")
        expect(page.locator("h1")).to_contain_text("Analytics Dashboard")

        goto(page, f"{BASE_URL}/")
        expect(page.locator("h1")).to_contain_text("Kai's Review Platform")
