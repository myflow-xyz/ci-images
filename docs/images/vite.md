# `ci-vite`

`ghcr.io/myflow-xyz/ci-vite` extends [`ci-node`](node.md) for TypeScript and
Vite quality, test, coverage, and production build jobs.

## Included tools

The compatibility bundle includes:

- TypeScript 7.0.2 (`tsc`), with TypeScript 6.0.3 available as `tsc6` for
  tools that still require its API;
- Vite 8.2.1;
- Vitest 4.1.10;
- `@vitest/coverage-v8` 4.1.10;
- Oxlint 1.78.0;
- `oxlint-tsgolint` 7.0.2001;
- Oxfmt 0.63.0.

The bundle and its transitive dependencies are installed from a committed npm
lockfile into an immutable versioned directory. The platform-specific `tsc`
and `tsgolint` executables are rebuilt from the exact upstream commits recorded
in the manifest with the same Go release as `ci-go`, then replace the matching
prebuilt executables from the npm packages. Reviewed dependency overrides for
those builds are also recorded in the manifest and verified by smoke tests.
The Go compiler and source trees are not retained in the runtime image.

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
