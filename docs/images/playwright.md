# `ci-playwright`

`ghcr.io/myflow-xyz/ci-playwright` extends [`ci-vite`](vite.md) for browser
smoke and E2E jobs.

## Included browser contract

The initial image contract includes:

- Playwright compatibility metadata for `@playwright/test` 1.61.1;
- Chromium installed for that exact Playwright release;
- compatible Debian Bookworm browser libraries;
- a fixed browser path readable by the unprivileged CI user;
- stable `playwright` and version-check command links in `/opt/ci-tools/bin`;
- `tini` as the container entrypoint for browser subprocess cleanup.

The repository still installs its lockfile-managed Playwright package. The
image supplies the matching browser and operating-system dependencies so a job
does not download Chromium at runtime.

## Version enforcement

Before launching a browser, a consumer compares its resolved
`@playwright/test` version with `PLAYWRIGHT_VERSION`. A mismatch fails with a
clear diagnostic because mismatched packages and browser binaries cannot
reliably locate compatible executables.

Browser assets are not a general dependency cache. They are immutable image
content and change only when the image is rebuilt.

## Runtime requirements

Jobs should use the IPC configuration recommended by Playwright. They do not
receive broad Linux capabilities or Docker socket access.

PMem UI uses this image for Chromium smoke and E2E jobs. Non-browser frontend
jobs use [`ci-vite`](vite.md).
