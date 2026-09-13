"""Integration-contract coverage for the Theme Studio editor and its API."""

from pathlib import Path
import ast
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "theme_studio" / "api.py"
HOOKS = ROOT / "theme_studio" / "hooks.py"
SETUP = ROOT / "theme_studio" / "setup.py"
MODULES = ROOT / "theme_studio" / "modules.txt"
PAGE = ROOT / "theme_studio" / "theme_studio" / "page" / "theme_studio" / "theme_studio.js"
PAGE_JSON = PAGE.with_name("theme_studio.json")
CSS = ROOT / "theme_studio" / "public" / "css" / "theme_studio.css"


def api_functions():
    source = API.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return source, {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


class StudioAppTest(unittest.TestCase):
    def test_app_depends_on_the_theme_and_ships_its_own_assets(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        self.assertIn('required_apps = ["solvronix_desk"]', hooks)
        self.assertIn("/assets/theme_studio/css/theme_studio.css?v=20", hooks)
        self.assertIn('after_install = "theme_studio.setup.after_install"', hooks)

    def test_install_claims_the_bench_theme_only_when_unclaimed(self):
        setup = SETUP.read_text(encoding="utf-8")
        self.assertIn("if master and master != site:", setup)
        self.assertIn("update_site_config(theme_store.MASTER_KEY, site", setup)
        self.assertIn("theme_store.export()", setup)

    def test_page_is_owned_by_this_app_and_restricted_to_system_managers(self):
        page = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(page["name"], "theme-studio")
        self.assertEqual(page["module"], "Theme Studio")
        self.assertEqual(page["roles"], [{"role": "System Manager"}])
        self.assertEqual(MODULES.read_text(encoding="utf-8").strip(), "Theme Studio")

    def test_editor_calls_this_apps_api(self):
        js = PAGE.read_text(encoding="utf-8")
        self.assertIn("theme_studio.api.publish_theme_config", js)
        self.assertIn("theme_studio.api.get_theme_studio_state", js)
        self.assertNotIn("solvronix_desk.theme_api", js)

    def test_every_endpoint_is_gated_to_managers_on_the_master_site(self):
        source, functions = api_functions()
        gate = ast.get_source_segment(source, functions["manager_only"]) or ""
        self.assertIn('frappe.only_for("System Manager")', gate)
        self.assertIn("theme_store.is_master()", gate)

        whitelisted = [
            node for node in functions.values()
            if any("whitelist" in ast.unparse(decorator) for decorator in node.decorator_list)
        ]
        self.assertGreaterEqual(len(whitelisted), 11)
        for node in whitelisted:
            first = node.body[1] if isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) else node.body[0]
            self.assertEqual(ast.unparse(first), "manager_only()", node.name)

    def test_studio_state_exposes_canonical_chart_schema_and_safe_registry(self):
        source = API.read_text(encoding="utf-8")

        self.assertIn("from solvronix_desk import chart_config, theme_engine, theme_store", source)
        self.assertIn("from theme_studio import chart_preview, chart_registry", source)
        self.assertIn('"chart_schema": chart_config.load_schema()', source)
        self.assertIn('"chart_registry": chart_registry.list_chart_sources(', source)
        self.assertIn('published.get("chart_overrides", {}).keys()', source)

    def test_every_chart_config_persistence_path_uses_strict_validation(self):
        source, nodes = api_functions()
        functions = {name: ast.get_source_segment(source, node) or "" for name, node in nodes.items()}

        self.assertIn("strict_charts=True", functions["validate_persisted_config"])
        for name in (
            "save_theme_draft",
            "publish_theme_config",
            "manage_theme_profile",
            "restore_theme_version",
        ):
            self.assertIn("validate_persisted_config", functions[name], name)
        self.assertIn("validate_referenced_profiles", functions["save_theme_assignments"])
        self.assertIn("validate_referenced_profiles", functions["save_theme_schedule"])

    def test_legacy_sync_projects_canonical_chart_colors(self):
        source, functions = api_functions()
        segment = ast.get_source_segment(source, functions["sync_legacy_fields"]) or ""

        self.assertIn('"chart_background"', segment)
        self.assertIn('"chart_palette"', segment)

    def test_api_validates_and_persists_studio_configuration(self):
        api = API.read_text(encoding="utf-8")
        self.assertIn("def publish_theme_config(", api)
        self.assertIn("def save_theme_draft(", api)
        self.assertIn("def manage_theme_profile(", api)
        self.assertIn("settings.theme_studio_config", api)
        self.assertIn("settings.theme_enabled = 1", api)

    def test_editor_has_drag_history_and_responsive_preview(self):
        js = PAGE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        self.assertIn('draggable="true"', js)
        self.assertIn('addEventListener("dragover"', js)
        self.assertIn("undo()", js)
        self.assertIn("redo()", js)
        self.assertIn('[data-device="mobile"]', css)
        self.assertIn("sts-preview-collapse", js)
        self.assertIn("sts-toolbar-left", js)
        self.assertIn("st-studio-draft", js)
        self.assertIn("on_page_hide", js)
        self.assertIn("_resolved_visual_config", js)
        self.assertIn("_is_dark_palette", js)
        self.assertIn("_mix_hex", js)
        self.assertIn("this._apply_draft_to_desk(visual)", js)

    def test_editor_typography_stays_readable(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("READABLE TYPOGRAPHY SCALE", css)
        self.assertIn(".sts-field > label { font-size: 13px; }", css)
        self.assertIn(".sts-field textarea { font-size: 13px;", css)
        self.assertIn(".sts-table-row { font-size: 11px; }", css)

    def test_login_preview_matches_public_login_structure(self):
        js = PAGE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        for token in (
            "sts-login-card-head", "sts-login-card-body", "sts-login-company-logo",
            "sts-login-app-logo", "sts-login-input", "sts-login-forgot",
            "data-login-powered", "data-login-footer",
        ):
            self.assertIn(token, js + css)
        self.assertIn("var loginSettings = loginConfig || c;", js)
        self.assertIn('"--studio-login-background": loginBackground', js)
        self.assertIn("background-image: var(--studio-login-background)", css)
        self.assertNotIn("Powered by Solvronix", js)

    def test_preview_elements_expose_contextual_property_inspector(self):
        js = PAGE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        for inspector in (
            "dashboard.heading", "dashboard.metrics", "dashboard.chart",
            "form.heading", "form.card", "form.fields", "form.actions",
            "table.heading", "table.grid", "table.status",
            "login.background", "login.branding", "login.card",
            "login.fields", "login.button", "login.footer",
        ):
            self.assertIn(f'"{inspector}"', js)
        self.assertIn("_inspector_catalog()", js)
        self.assertIn("_render_inspector()", js)
        self.assertIn("_position_inspector(element)", js)
        self.assertIn("_sync_setting_inputs(key, this)", js)
        self.assertIn("data-open-control-section", js)
        self.assertIn(".sts-context-inspector", css)
        self.assertIn('.sts-context-inspector[data-side="right"]', css)
        self.assertIn('.sts-context-inspector[data-side="left"]', css)
        self.assertIn(".is-inspected", css)

    def test_complete_studio_feature_surfaces_exist(self):
        js = PAGE.read_text(encoding="utf-8")
        api = API.read_text(encoding="utf-8")
        for token in (
            "Main colours", "Navbar & sidebar", "Buttons & fields", "Typography",
            "Cards, lists & tables", "Workspace & dashboard", "Login & branding",
            "Layout", "Smart Home & features", "Accessibility", "Developer options", "Profiles & deployment",
        ):
            self.assertIn(token, js)
        for endpoint in (
            "save_theme_draft", "publish_theme_config", "manage_theme_profile",
            "restore_theme_version", "import_theme_profile",
            "save_theme_assignments", "save_theme_schedule", "clear_theme_cache",
        ):
            self.assertIn(f"def {endpoint}", api)
        self.assertIn('"preferred_mode", "Theme mode"', js)
        self.assertIn("_sync_profile_actions()", js)
        self.assertIn('__("Current Theme Copy")', js)
        self.assertIn('data-profile-action="apply"', js)

    def test_hybrid_charts_preview_scene_is_declared_after_workspace(self):
        source = PAGE.read_text(encoding="utf-8")

        workspace = source.index('data-preview-scene="workspace"')
        charts = source.index('data-preview-scene="charts"')
        self.assertGreater(charts, workspace)
        self.assertIn("_charts_scene_html()", source)
        for kind in ("line", "bar", "donut", "sparkline"):
            self.assertIn(f'card("{kind}"', source)

    def test_hybrid_charts_preview_is_responsive_theme_driven_and_motion_safe(self):
        css = CSS.read_text(encoding="utf-8")

        for token in (
            ".sts-charts-gallery",
            ".sts-chart-preview-card.is-inspected",
            "--sts-chart-surface",
            "--sts-chart-series-1",
            "--sts-chart-line-width",
            "--sts-chart-bar-radius",
            ".sts-chart-donut",
            "@media (prefers-reduced-motion: reduce)",
        ):
            self.assertIn(token, css)
        self.assertRegex(css, r'\[data-device="(?:tablet|mobile)"\][^{]*\.sts-charts-gallery')

    def test_theme_settings_are_unified_into_studio(self):
        js = PAGE.read_text(encoding="utf-8")
        api = API.read_text(encoding="utf-8")

        for key in ("tagline", "enable_command_palette", "enable_smart_home"):
            self.assertIn(f'"{key}"', js)
            self.assertIn(f'config["{key}"]', api)
        self.assertIn('"attach-image"', js)
        self.assertIn("st_allow_raw_theme_settings", js)

    def test_theme_studio_exposes_sidebar_layout_control(self):
        studio = PAGE.read_text(encoding="utf-8")

        self.assertIn('"sidebar_layout", "Sidebar layout", "select", ["Tree", "Icon Rail"]', studio)
        self.assertIn("icon_rail_width", studio)
        self.assertIn("_apply_draft_to_desk", studio)
        self.assertIn("--st-rail-width:", studio)

    def test_loading_a_profile_preserves_site_identity_in_the_editor(self):
        """Regression test: loading ANY profile (built-in or custom) directly
        replaces this.config with the profile's own stored config, which
        always carries blank company_logo/app_title/favicon/tagline unless
        the profile explicitly set them — confirmed live on
        erp.solvronix.com, where loading a built-in profile then publishing
        silently erased the real company logo/name. The editor must restore
        these from what was there before loading, mirroring
        theme_engine.resolve_profile_config()'s server-side fix."""
        js = PAGE.read_text(encoding="utf-8")

        self.assertIn("var previousIdentity = {", js)
        self.assertIn("if (!self.config[field]) self.config[field] = previousIdentity[field];", js)


if __name__ == "__main__":
    unittest.main()
