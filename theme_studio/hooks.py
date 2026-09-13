# ── APP METADATA ───────────────────────────────────────────────────────────────
app_name = "theme_studio"
app_title = "Theme Studio"
app_publisher = "Habeebe"
app_description = "Visual editor for the bench-wide Solvronix Desk theme"
app_email = "dosnet2200@gmail.com"
app_license = "mit"

# The editor stores Theme Settings and renders previews with solvronix_desk's engine.
required_apps = ["solvronix_desk"]

# ── AUTHENTICATED DESK ASSETS ──────────────────────────────────────────────────
# Query versions are bumped whenever an asset changes to invalidate browser cache.
app_include_css = ["/assets/theme_studio/css/theme_studio.css?v=21"]

# ── INSTALL HOOKS ──────────────────────────────────────────────────────────────
after_install = "theme_studio.setup.after_install"
