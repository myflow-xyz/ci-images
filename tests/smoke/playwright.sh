#!/usr/bin/env bash

set -euo pipefail

: "${EXPECTED_PLAYWRIGHT_VERSION:?EXPECTED_PLAYWRIGHT_VERSION is not set}"
expected_playwright=$EXPECTED_PLAYWRIGHT_VERSION

[[ $PLAYWRIGHT_VERSION == "$expected_playwright" ]]
[[ $PLAYWRIGHT_BROWSERS_PATH == /ms-playwright ]]
[[ $(ps -p 1 -o comm= | tr -d ' ') == tini ]]

check-playwright-version "$expected_playwright"

if mismatch_output=$(
	check-playwright-version 0.0.0 2>&1
); then
	printf 'mismatched Playwright version was accepted\n' >&2
	exit 1
fi
grep --fixed-strings \
	"repository=0.0.0 image=${expected_playwright}" \
	<<<"$mismatch_output" \
	>/dev/null

node <<'NODE'
(async () => {
  const path = [
    "/opt/ci-tools/playwright",
    process.env.PLAYWRIGHT_VERSION,
    "node_modules",
    "@playwright",
    "test"
  ].join("/");
  const { chromium } = require(path);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setContent("<main data-smoke='ready'>CI</main>");
  const state = await page.locator("main").getAttribute("data-smoke");
  await browser.close();
  if (state !== "ready") {
    throw new Error(`unexpected browser smoke state: ${state}`);
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
NODE
