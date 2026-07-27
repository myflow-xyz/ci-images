# `ci-vite`

`ghcr.io/myflow-xyz/ci-vite` extends [`ci-node`](node.md) for TypeScript and
Vite quality, test, coverage, and production build jobs.

## Included tools

The initial compatibility bundle matches the PMem UI dependency graph:

- TypeScript 6.0.3;
- Vite 8.1.0;
- Vitest 4.1.9;
- `@vitest/coverage-v8` 4.1.9;
- Oxlint 1.71.0;
- `oxlint-tsgolint` 0.23.0;
- Oxfmt 0.56.0.

The bundle and its transitive dependencies are installed from a committed npm
lockfile into an immutable versioned directory.

## Repository-local execution

The image bundle is an audited compatibility and smoke-test baseline. It does
not replace a repository's frozen lockfile.

Normal jobs install the repository dependencies and run tools through package
scripts or `pnpm exec`. Those commands must resolve `node_modules/.bin` before
the image-global stable links. A mismatch between repository and image pins
fails a compatibility check; the job does not silently substitute the bundled
version.

## Consumers

PMem UI uses this image for formatting, lint, type-check, unit test, coverage,
and production build jobs.

Use [`ci-playwright`](playwright.md) when a job also launches Chromium.
