"""Whitelisted API surface for Theme Studio, the bench-wide theme editor."""

import frappe

from solvronix_desk import chart_config, theme_engine, theme_store
from theme_studio import chart_preview, chart_registry


# ── 1. AUTHORIZATION / COMPLETE EDITOR STATE ──────────────────────────────────
# Every Studio endpoint passes through the same gate: a System Manager on the
# bench's theme master site. Edits made anywhere else would never reach a site.
def manager_only():
    frappe.only_for("System Manager")
    master = theme_store.master_site()
    if master and not theme_store.is_master():
        frappe.throw(f"The theme for this bench is managed on {master}")


def validate_persisted_config(config, base=None):
    """Apply one strict chart contract to every persisted theme payload."""
    try:
        return theme_engine.sanitize_config(
            config,
            base,
            strict_charts=True,
        )
    except chart_config.ChartConfigError as error:
        frappe.throw(frappe.as_json({"chart_errors": error.errors}))


def studio_state(settings=None):
    """Assemble one consistent editor snapshot from normalized stored fields."""
    settings = settings or frappe.get_single("Theme Settings")
    published = theme_engine.published_config(settings)
    stored_draft = theme_engine.json_field(settings, "theme_studio_draft", {})
    draft = (
        theme_engine.sanitize_config(stored_draft, published, validate_contrast=False)
        if stored_draft
        else published
    )
    versions = theme_engine.json_field(settings, "theme_versions", [])[:theme_engine.MAX_VERSIONS]
    configured_chart_ids = set(published.get("chart_overrides", {}).keys())
    configured_chart_ids.update(draft.get("chart_overrides", {}).keys())
    return {
        "config": draft,
        "published": published,
        "defaults": theme_engine.sanitize_config(
            theme_engine.DEFAULT_CONFIG, validate_contrast=False
        ),
        "profiles": theme_engine.profiles(settings),
        "versions": versions,
        # One theme serves the whole bench: no user, role, company or scheduled rules.
        "flags": {
            "enabled": bool(getattr(settings, "theme_enabled", 1)),
            "active_profile": getattr(settings, "active_profile", "") or "",
        },
        "chart_schema": chart_config.load_schema(),
        "chart_registry": chart_registry.list_chart_sources(
            getattr(frappe.session, "user", None),
            configured_ids=sorted(configured_chart_ids),
        ),
        "wcag_failures": theme_engine.wcag_failures(draft),
    }


@frappe.whitelist()
def get_theme_studio_state():
    manager_only()
    return studio_state()


@frappe.whitelist()
def get_chart_preview(chart_id):
    """Return permission-checked ERPNext values for one supported preview source."""
    manager_only()
    return chart_preview.get_preview(chart_id)


# ── 2. LIVE PREVIEW / PRIVATE DRAFTS ──────────────────────────────────────────
# Preview never publishes. Drafts persist separately from the active site theme.
@frappe.whitelist()
def preview_theme_css(config):
    manager_only()
    clean = theme_engine.sanitize_config(config, validate_contrast=False)
    return {
        "config": clean,
        "css": theme_engine.render_css(clean),
        "wcag_failures": theme_engine.wcag_failures(clean),
    }


@frappe.whitelist()
def save_theme_draft(config):
    manager_only()
    settings = frappe.get_single("Theme Settings")
    clean = validate_persisted_config(config)
    frappe.db.set_single_value("Theme Settings", "theme_studio_draft", frappe.as_json(clean))
    return {"config": clean, "wcag_failures": theme_engine.wcag_failures(clean)}


def sync_legacy_fields(settings, config):
    """Keep pre-Studio settings coherent for older templates and integrations."""
    for field in (
        "brand_color", "accent_color", "sidebar_background", "navbar_background",
        "page_background", "card_background", "text_color", "corner_radius",
        "shadow_style", "sidebar_width", "chart_background", "chart_palette",
        # icon_rail_background/icon_rail_active_color are OPTIONAL_COLOR_FIELDS
        # (auto-if-empty, like sidebar_text_color) and are deliberately excluded
        # from this sync for the same reason those are — see icon_rail_width's
        # sibling sidebar_width above for the pattern this does follow.
        "sidebar_layout", "icon_rail_width",
    ):
        settings.set(field, config[field])
    settings.studio_layout = frappe.as_json(config["layout"])
    settings.default_theme_mode = config["preferred_mode"]
    settings.default_density = config["density"]
    settings.base_font_size = (
        "Small" if config["base_font_px"] <= 13
        else "Large" if config["base_font_px"] >= 16
        else "Default"
    )
    # Theme Studio is canonical, so empty values must also clear legacy fields.
    settings.logo = config["company_logo"]
    settings.favicon = config["favicon"]
    settings.company_name = config["app_title"]
    settings.tagline = config["tagline"]
    settings.enable_command_palette = int(config["enable_command_palette"])
    settings.enable_smart_home = int(config["enable_smart_home"])
    # Keep the deprecated field coherent for older clients that still read it.
    settings.dark_mode_default = int(config["preferred_mode"] == "Dark")


# ── 3. ATOMIC PUBLISH ──────────────────────────────────────────────────────────
# Back up the previous version before replacing the published configuration.
# Saving Theme Settings on the master site republishes the bench-wide theme.
@frappe.whitelist()
def publish_theme_config(config, label=None, profile_id=None):
    manager_only()
    settings = frappe.get_single("Theme Settings")
    clean = validate_persisted_config(config)
    clean = theme_engine.protect_identity_on_profile_switch(settings, clean, profile_id)
    versions = theme_engine.json_field(settings, "theme_versions", [])
    versions.insert(
        0,
        theme_engine.version_entry(
            theme_engine.published_config(settings),
            label or "Before publish",
        ),
    )
    settings.theme_versions = frappe.as_json(versions[:theme_engine.MAX_VERSIONS])
    settings.theme_studio_config = frappe.as_json(clean)
    settings.theme_studio_draft = ""
    settings.theme_enabled = 1
    settings.active_profile = str(profile_id or "")[:80]
    sync_legacy_fields(settings, clean)
    settings.save()
    return {
        "config": clean,
        "css": theme_engine.render_css(clean),
        "state": studio_state(settings),
    }


# ── 4. PROFILE CRUD ────────────────────────────────────────────────────────────
# Built-in profiles come from the engine; only custom JSON profiles are mutable.
@frappe.whitelist()
def manage_theme_profile(action, profile_id=None, name=None, config=None, description=None):
    manager_only()
    settings = frappe.get_single("Theme Settings")
    custom = theme_engine.json_field(settings, "theme_profiles", [])
    action = str(action or "").lower()
    source = theme_engine.profile_by_id(settings, profile_id) if profile_id else None

    if action in {"create", "duplicate"}:
        if len(custom) >= theme_engine.MAX_PROFILES:
            frappe.throw("Maximum number of custom theme profiles reached")
        source_config = config if action == "create" else (source or {}).get("config")
        if not source_config:
            frappe.throw("Theme profile source not found")
        now = theme_engine.now_string()
        custom.append(
            {
                "id": theme_engine.new_id("theme"),
                "name": str(name or ((source or {}).get("name", "Custom") + " Copy"))[:100],
                "description": str(description or (source or {}).get("description", ""))[:300],
                "created": now,
                "modified": now,
                "config": validate_persisted_config(source_config),
            }
        )
    elif action == "update":
        target = next((item for item in custom if item.get("id") == profile_id), None)
        if not target:
            frappe.throw("Only custom profiles can be updated")
        target["name"] = str(name or target.get("name") or "Custom")[:100]
        target["description"] = str(
            description if description is not None else target.get("description", "")
        )[:300]
        target["config"] = validate_persisted_config(config or target.get("config"))
        target["modified"] = theme_engine.now_string()
    elif action == "rename":
        target = next((item for item in custom if item.get("id") == profile_id), None)
        if not target:
            frappe.throw("Only custom profiles can be renamed")
        target["name"] = str(name or "")[:100]
        if not target["name"]:
            frappe.throw("Profile name is required")
        target["modified"] = theme_engine.now_string()
    elif action == "delete":
        original_length = len(custom)
        custom = [item for item in custom if item.get("id") != profile_id]
        if len(custom) == original_length:
            frappe.throw("Only custom profiles can be deleted")
        assigned = theme_engine.assignments(settings)
        if assigned["default"] == profile_id:
            assigned["default"] = ""
        for scope in ("users", "roles", "companies"):
            assigned[scope] = {
                key: value
                for key, value in assigned[scope].items()
                if value != profile_id
            }
        settings.theme_assignments = frappe.as_json(assigned)
        scheduled = theme_engine.schedule(settings)
        if scheduled["profile_id"] == profile_id:
            scheduled.update({"enabled": False, "profile_id": ""})
            settings.theme_schedule = frappe.as_json(scheduled)
        if getattr(settings, "active_profile", "") == profile_id:
            settings.active_profile = ""
        if frappe.db.exists("DocType", "Theme Preference"):
            frappe.db.delete("Theme Preference", {"theme_profile": profile_id})
    else:
        frappe.throw("Unsupported profile action")

    settings.theme_profiles = frappe.as_json(custom)
    settings.save()
    return studio_state(settings)


# ── 5. VERSION RESTORE / PORTABLE IMPORT ───────────────────────────────────────
# Restores land in the draft slot, giving administrators a review step.
@frappe.whitelist()
def restore_theme_version(version_id):
    manager_only()
    settings = frappe.get_single("Theme Settings")
    versions = theme_engine.json_field(settings, "theme_versions", [])
    version = next((item for item in versions if item.get("id") == version_id), None)
    if not version:
        frappe.throw("Theme version not found")
    clean = validate_persisted_config(version.get("config"))
    frappe.db.set_single_value("Theme Settings", "theme_studio_draft", frappe.as_json(clean))
    return {"config": clean, "wcag_failures": theme_engine.wcag_failures(clean)}


@frappe.whitelist()
def import_theme_profile(payload, name=None):
    manager_only()
    data = theme_engine.parse_json(payload, {})
    config = data.get("config", data)
    return manage_theme_profile(
        "create",
        name=name or data.get("name") or "Imported Theme",
        config=config,
        description=data.get("description") or "Imported Theme Studio profile",
    )


# ── 6. SITE POLICY ─────────────────────────────────────────────────────────────
# One theme serves the whole bench, so the only policy left is switching it on/off.
@frappe.whitelist()
def set_theme_enabled(enabled):
    manager_only()
    settings = frappe.get_single("Theme Settings")
    settings.theme_enabled = int(theme_engine.bool_value(enabled))
    settings.save()
    return studio_state(settings)


# ── 7. CACHE CONTROL ───────────────────────────────────────────────────────────
@frappe.whitelist()
def clear_theme_cache(reload_desk=0):
    manager_only()
    frappe.clear_cache()
    return {"ok": True, "reload": bool(int(reload_desk or 0))}
