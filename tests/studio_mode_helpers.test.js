const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const studioPath = path.join(
  __dirname, "..", "theme_studio", "theme_studio", "page", "theme_studio", "theme_studio.js"
);

test("Theme Studio uses the runtime's non-persisting mode helpers", () => {
  const studio = fs.readFileSync(studioPath, "utf8");

  assert.match(studio, /window\.stApplyThemeMode\(c\.preferred_mode\)/);
  assert.doesNotMatch(studio, /preferred_mode: response\.message\.config\.preferred_mode/);
  assert.match(studio, /st-theme-os-mode-change\.stsThemeMode/);
});
