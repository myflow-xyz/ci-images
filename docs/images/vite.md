# `ci-vite`

`ghcr.io/myflow-xyz/ci-vite` extends [`ci-node`](node.md) for TypeScript and
Vite quality, test, coverage, and production build jobs.

## Included tools

The compatibility bundle includes:

- TypeScript 6.0.3;
- Vite 8.1.0;
- Vitest 4.1.9;
- `@vitest/coverage-v8` 4.1.9;
- Oxlint 1.71.0;
- `oxlint-tsgolint` 0.23.0;
- Oxfmt 0.56.0.

The bundle and its transitive dependencies are installed from a committed npm
lockfile into an immutable versioned directory. The platform-specific
`tsgolint` executable is rebuilt from the exact upstream and TypeScript-Go
commits recorded in the manifest with Go 1.26.5, then replaces the matching
prebuilt executable from the npm package. The Go compiler and source trees are
not retained in the runtime image.

## Runtime environment

This image sets no additional runtime environment variables. It inherits the
[`ci-node` environment](node.md#runtime-environment) unchanged.

## Repository-local execution

The image bundle is an audited compatibility and smoke-test baseline. It does
not replace a repository's frozen lockfile.

Normal jobs install the repository dependencies and run tools through package
scripts or `pnpm exec`. Those commands must resolve `node_modules/.bin` before
the image-global stable links. A mismatch between repository and image pins
fails a compatibility check; the job does not silently substitute the bundled
version.

## Usage

Use `ci-vite` for formatting, lint, type-check, unit test, coverage, and
production build jobs.

Use [`ci-playwright`](playwright.md) when a job also launches Chromium.
