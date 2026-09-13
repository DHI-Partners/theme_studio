import os

import frappe
from frappe.installer import update_site_config

from solvronix_desk import theme_store


# ── INSTALL: CLAIM THE BENCH THEME ─────────────────────────────────────────────
def after_install():
    """Make this site the bench's theme master, unless another site already is."""
    site = frappe.local.site
    master = theme_store.master_site()
    if master and master != site:
        print(f"\n⚠️  Theme Studio: {master} already manages the bench theme; "
              f"the studio on {site} will refuse edits.\n")
        return
    if not master:
        common_config = os.path.join(frappe.local.sites_path, "common_site_config.json")
        update_site_config(theme_store.MASTER_KEY, site, site_config_path=common_config)
        # This process keeps its loaded config; export() below must already see the key.
        frappe.local.conf[theme_store.MASTER_KEY] = site
    theme_store.export()
    print(f"\n✅ Theme Studio: {site} manages the theme for every site on this bench.\n")
