# Theme Studio

Visual editor for the Solvronix Desk theme ([custom_theme](https://github.com/DHI-Partners/custom_theme)).
It lives in its own app so it is installed only on the site that manages the theme;
every other site just wears the theme.

## How it works

- Install it on one site. That site becomes `theme_master_site` in
  `common_site_config.json`, unless another site already holds the key.
- Publishing in the studio saves Theme Settings. `solvronix_desk` then writes the
  theme to `sites/solvronix_theme.json`, and every site on the bench renders it.
- On any site other than the master, the studio API refuses to read or write.

## Installation

```bash
bench get-app https://github.com/DHI-Partners/custom_theme
bench get-app https://github.com/DHI-Partners/theme_studio
bench --site habibi.localhost install-app theme_studio
```

`solvronix_desk` (from `custom_theme`) is required and is installed first.
The editor itself is described in [docs/theme-studio.md](docs/theme-studio.md).

## Tests

Python tests import `solvronix_desk`, so put a `custom_theme` checkout on the path:

```bash
PYTHONPATH=../custom_theme python3 -m unittest discover -s tests -p "test_*.py"
node --test tests/*.test.js
```

## License

MIT. Theme Studio was split out of Solvronix Desk, © 2026 Solvronix; see `license.txt`.
