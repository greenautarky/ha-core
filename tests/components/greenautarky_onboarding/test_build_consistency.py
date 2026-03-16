"""Integration consistency tests for greenautarky onboarding.

Verifies that the build pipeline, frontend serving, and cross-repo wiring
are correctly configured. These tests catch issues like the old page.html
being served instead of the built Lit panel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Core repo root
CORE_ROOT = Path(__file__).resolve().parents[3]
# Frontend repo is a sibling directory
FRONTEND_ROOT = CORE_ROOT.parent / "homeassistant_frontend"
GA_COMPONENT = CORE_ROOT / "homeassistant" / "components" / "greenautarky_onboarding"
FRONTEND_COMPONENT = CORE_ROOT / "homeassistant" / "components" / "frontend"


class TestFrontendServing:
    """Verify the built frontend HTML is correctly served."""

    def test_greenautarky_html_registered_as_static_path(self) -> None:
        """frontend/__init__.py must serve greenautarky-setup.html as static."""
        init_py = FRONTEND_COMPONENT / "__init__.py"
        content = init_py.read_text()
        assert '"greenautarky-setup.html"' in content, (
            "greenautarky-setup.html not registered as static path in frontend/__init__.py"
        )

    def test_redirect_points_to_html_file(self) -> None:
        """The GA onboarding redirect must go to .html, not the old /greenautarky-setup."""
        init_py = FRONTEND_COMPONENT / "__init__.py"
        content = init_py.read_text()
        # Find the GA redirect line
        assert "/greenautarky-setup.html" in content, (
            "Redirect should point to /greenautarky-setup.html"
        )

    def test_old_page_html_removed(self) -> None:
        """The legacy page.html must not exist (replaced by built Lit panel)."""
        assert not (GA_COMPONENT / "page.html").exists(), (
            "Legacy page.html still exists — should be deleted"
        )

    def test_page_view_redirects_not_serves(self) -> None:
        """GAOnboardingPageView must redirect to .html, not serve inline HTML."""
        http_py = GA_COMPONENT / "http.py"
        content = http_py.read_text()
        # Must not have _PAGE_HTML reference
        assert "_PAGE_HTML" not in content, (
            "http.py still references _PAGE_HTML — should redirect to built HTML"
        )
        assert "greenautarky-setup.html" in content, (
            "http.py should redirect to greenautarky-setup.html"
        )


class TestEndpointConsistency:
    """Verify API endpoints match between frontend and backend."""

    def test_create_user_endpoint_exists(self) -> None:
        """Backend must have create_user view (not create_tenant)."""
        http_py = GA_COMPONENT / "http.py"
        content = http_py.read_text()
        assert "create_user" in content
        assert "create_tenant" not in content, (
            "Old create_tenant endpoint found — must use create_user"
        )

    def test_no_tenant_mode_references(self) -> None:
        """No tenant_mode logic should remain in the backend."""
        for py_file in GA_COMPONENT.glob("*.py"):
            content = py_file.read_text()
            assert "tenant_mode" not in content, (
                f"tenant_mode reference found in {py_file.name} — remove legacy code"
            )
            assert "tenant" not in content.lower() or "create_tenant" not in content, (
                f"create_tenant reference found in {py_file.name}"
            )

    def test_all_onboarding_endpoints_unauthenticated(self) -> None:
        """Onboarding endpoints must be unauthenticated (user has no account yet).

        Exception: GAOnboardingResetView requires admin auth — it is a QA/admin
        utility, not part of the customer-facing wizard flow.
        """
        http_py = GA_COMPONENT / "http.py"
        content = http_py.read_text()
        # Find all GA onboarding view classes (not consent views)
        onboarding_views = re.findall(
            r"class (GAOnboarding\w+)\(HomeAssistantView\)",
            content,
        )
        assert len(onboarding_views) >= 4, (
            f"Expected at least 4 onboarding views, found {len(onboarding_views)}"
        )
        # Authenticated-by-design views (admin/bearer token required)
        authenticated_by_design = {"GAOnboardingResetView"}
        # Each onboarding wizard view must have requires_auth = False
        for view in onboarding_views:
            if view in authenticated_by_design:
                continue
            # Find the class block
            pattern = rf"class {view}\(HomeAssistantView\).*?requires_auth\s*=\s*(\w+)"
            match = re.search(pattern, content, re.DOTALL)
            assert match, f"{view} missing requires_auth"
            assert match.group(1) == "False", (
                f"{view} must have requires_auth = False for unauthenticated onboarding"
            )


class TestIframePanelConsistency:
    """Verify the sidebar iframe panel is correctly configured."""

    def test_iframe_points_to_html(self) -> None:
        """The iframe entrypoint must load /greenautarky-setup.html."""
        entrypoint = GA_COMPONENT / "panel" / "dist" / "entrypoint.js"
        if not entrypoint.exists():
            pytest.skip("Panel entrypoint not found")
        content = entrypoint.read_text()
        assert "greenautarky-setup.html" in content, (
            "Iframe must point to /greenautarky-setup.html (not /greenautarky-setup)"
        )

    def test_panel_registration_exists(self) -> None:
        """The sidebar panel must be registered in __init__.py."""
        init_py = GA_COMPONENT / "__init__.py"
        content = init_py.read_text()
        assert "async_register_panel" in content
        assert "greenautarky-setup-panel" in content


class TestFrontendBuildPipeline:
    """Verify the frontend repo build pipeline is correctly configured."""

    @pytest.fixture(autouse=True)
    def _check_frontend(self) -> None:
        if not FRONTEND_ROOT.exists():
            pytest.skip("Frontend repo not found")

    def test_webpack_entrypoint_exists(self) -> None:
        """The greenautarky-setup webpack entrypoint must exist."""
        assert (FRONTEND_ROOT / "src" / "entrypoints" / "greenautarky-setup.ts").exists()

    def test_html_template_exists(self) -> None:
        """The greenautarky-setup HTML template must exist."""
        assert (FRONTEND_ROOT / "src" / "html" / "greenautarky-setup.html.template").exists()

    def test_html_template_loads_lit_panel(self) -> None:
        """The HTML template must load the Lit panel (not inline JS)."""
        template = (
            FRONTEND_ROOT / "src" / "html" / "greenautarky-setup.html.template"
        ).read_text()
        assert "<ha-panel-greenautarky-setup>" in template
        assert "<script>" not in template or "renderTemplate" in template, (
            "Template should use Lit panel, not inline JavaScript"
        )

    def test_entry_html_includes_greenautarky(self) -> None:
        """entry-html.js APP_PAGE_ENTRIES must include greenautarky-setup.html."""
        entry_html = (
            FRONTEND_ROOT / "build-scripts" / "gulp" / "entry-html.js"
        ).read_text()
        assert '"greenautarky-setup.html"' in entry_html, (
            "greenautarky-setup.html not in APP_PAGE_ENTRIES — build won't produce HTML"
        )

    def test_bundle_has_entrypoint(self) -> None:
        """bundle.cjs must register the greenautarky-setup entrypoint."""
        bundle = (FRONTEND_ROOT / "build-scripts" / "bundle.cjs").read_text()
        assert '"greenautarky-setup"' in bundle

    def test_compress_includes_greenautarky(self) -> None:
        """compress.js must include greenautarky-setup in compression."""
        compress = (
            FRONTEND_ROOT / "build-scripts" / "gulp" / "compress.js"
        ).read_text()
        assert "greenautarky-setup" in compress

    def test_panel_has_user_creation_step(self) -> None:
        """The Lit panel must include the user creation step."""
        panel = (
            FRONTEND_ROOT
            / "src"
            / "panels"
            / "greenautarky-setup"
            / "ha-panel-greenautarky-setup.ts"
        ).read_text()
        assert '"user"' in panel, "Panel must include 'user' step"
        assert "ga-setup-create-user" in panel

    def test_api_uses_create_user(self) -> None:
        """Frontend API layer must use create_user (not create_tenant)."""
        api = (
            FRONTEND_ROOT / "src" / "data" / "greenautarky_setup.ts"
        ).read_text()
        assert "create_user" in api
        assert "create_tenant" not in api
