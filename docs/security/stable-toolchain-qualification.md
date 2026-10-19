# Stable toolchain maintenance and security qualification

This page retains the previously accepted qualification record. The [manifest](../../manifests/versions.json) and lockfiles provide current pins. Record new maintenance findings, verification evidence, and compatibility decisions in the PMem task. Generate current findings with the scanners; keep generated scan inventories outside the repository.

PMem `task_000533` requalifies the accepted maintenance from `task_000524` at `develop` commit `d780a25e0c26b8ebaf6ab3b94af384468b60f44f`. Stable `main` remains at `c9250a386f1d8ed183c25311a39e307949270624`; PR 41's compatible updates are already merged into `develop`. This assessment uses upstream metadata and vulnerability feeds retrieved on 2026-10-15 America/Los_Angeles (2026-10-16 UTC). It preserves runtime release lines, image names, user/cache contracts, and release policy. Local qualification does not confirm stable promotion or publication.

## Dependency selection

The audit covers all eight images, manifest tools and overrides, all five npm locks, the Go capability-helper module, both architectures' direct Debian package candidates, installed OS package upgrade plans, OCI parents, build infrastructure, six pinned actions, and the test-daemon image. The [manifest](../../manifests/versions.json) and locks contain exact pins.

These updates are additional to the accepted PR 41 maintenance:

| Component | Previous | Selected |
| --- | --- | --- |
| npm and npx | `12.2.0` | `12.2.1` |
| npm's Undici replacement | `6.29.0` | `6.29.1` |
| Redocly CLI | `2.63.0` | `2.64.0` |
| Vitest and V8 coverage | `5.0.4` | `5.0.5` |
| Markdown's transitive argparse | `3.0.2` | `3.0.3` |

All five npm graphs were resolved with the selected npm release. The Vite lock also advances the paired Vitest mocker and spy packages to `5.0.5`. The Playwright lock is unchanged. Go modules and reviewed overrides remain current; this assessment does not force transitive major upgrades or downgrade the capability helper's upstream-selected prerelease module.

The official [npm release][npm-release], [Undici release][undici-release], [Redocly changelog][redocly-release], and [Vitest release][vitest-release] support selection. npm's GitHub latest release is a non-prerelease `12.2.1`, although the registry's `latest` tag still names `12.2.0`. Its published archive was checked against registry SHA-512 integrity before recording its SHA-256 pin.

[npm-release]: https://github.com/npm/cli/releases/tag/v12.2.1
[undici-release]: https://github.com/nodejs/undici/releases/tag/v6.29.1
[redocly-release]: https://redocly.com/docs/cli/changelog
[vitest-release]: https://github.com/vitest-dev/vitest/releases/tag/v5.0.5

### Retained versions and compatibility limits

- [Go `1.27.2`](https://go.dev/dl/?mode=json), Node `26.12.0`, Vite `8.3.4`, TypeScript `7.0.2`, the paired tsgolint source, and the remaining manifest tools are current on their selected compatible release lines.
- CPython remains on `3.14.8`; adopting the new `3.15` feature line requires separate compatibility qualification.
- Oxfmt remains on `0.72.0`: [the `0.73.0` release][oxfmt-release] explicitly changes CLI migration and TOML configuration behavior. Oxlint's `1.88.0` breaking-change entries concern internal Rust AST APIs; the installed CLI remains on its existing major line and passes its image smoke contract.
- pnpm remains on the official native release `12.11.2`. The npm registry contains newer version records, but both its `latest` tag and the GitHub latest release still select `12.11.2`. Undici retains npm's compatible `6.x` release line.
- The existing Debian snapshot `20261015T030350Z` is retained. Signed indexes at `20261016T023245Z` offer no newer direct base/network packages on AMD64 or ARM64. Native base, Go, Playwright, and PostgreSQL upgrade plans report zero upgrades.
- Debian, pgvector, Dockerfile frontend `1.28.0`, BuildKit `0.34.0`, the Syft generator `1.12.0`, Buildx `0.38.0`, and action pins still match upstream release metadata. Action tag commits were checked individually.
- The isolated Docker test daemon remains on the current published `29.9.0-dind` digest. A `29.9.1-dind` image was unavailable at selection.
- Playwright consumers must retain the existing exact package/browser matching contract when adopting this suite: the selected package is now `1.64.1`.

[oxfmt-release]: https://github.com/oxc-project/oxc/releases/tag/oxfmt_v0.73.0

## Security changes

The accepted PR 41 Debian update already resolves four curl advisories: [CVE-2026-8286][curl-8286], [CVE-2026-8927][curl-8927], [CVE-2026-92392][curl-92392], and [CVE-2026-8924][curl-8924]. Those fixes remain in place. No additional stable Debian package fix is available in this assessment.

Undici `6.29.1` fixes three HIGH and two MEDIUM issues in the npm replacement: TLS verification callback loss, TLS renegotiation errors, excessive content encodings, EventSource parser state, and WebSocket PONG buffering. The [upstream release][undici-release] lists the advisories. New runtime regressions use a trusted local TLS fixture to require custom certificate rejection and a malformed HTTP response to require controlled fetch rejection. Against `6.29.0`, the TLS callback is lost and the malformed response crashes the process despite a caught fetch rejection. Both regressions pass against the replacement `6.29.1`. These checks cover npm's installed module, not Node's separate built-in copy.

The checksum-guarded [braces mitigation][braces] remains in the Node image and host CI Markdown checks. The public API and Markdown CLI regressions remain required. Package version `3.0.3` stays truthful so scanners and SBOMs retain the upstream advisory.

[curl-8286]: https://security-tracker.debian.org/tracker/CVE-2026-8286
[curl-8927]: https://security-tracker.debian.org/tracker/CVE-2026-8927
[curl-92392]: https://security-tracker.debian.org/tracker/CVE-2026-92392
[curl-8924]: https://security-tracker.debian.org/tracker/CVE-2026-8924
[braces]: https://github.com/advisories/GHSA-vfj7-8cjw-p6xm

## Verification

All eight images were rebuilt and passed native ARM64 smoke checks for this assessment. The checks cover non-root identity, caches, protected Git settings, Go race execution, Goose SQLite migrations and rollback, sqlc/CEL behavior, npm replacements, Markdown math and depth guards, frontend commands and local tool precedence, Chromium launch, PostgreSQL/pgvector, and Docker/Compose offline behavior. The new npm Undici regressions pass inside the rebuilt Node image.

A separate frontend fixture passes Vitest `5.0.5` with its paired V8 coverage provider and 100% line coverage of the fixture, TypeScript checking, and a Vite production build. Static/release/publication/helper regressions, ShellCheck, shfmt, JavaScript syntax, and Markdown security checks pass. Utility unit tests pass 114 cases in Linux; image-resolution tests pass 16 cases; workflow tests pass 3 cases.

All image labels and final scans match manifest SHA-256:

`ce41588a79b4a4771e6ad27740633f60d8544974e6fdb8174d73a52c24bd73fe`

Trivy `0.76.0` scans all eight final images at all severities with vulnerability metadata updated at `2026-10-16T01:13:54Z`. The unchanged fixed HIGH/CRITICAL scan gate passes on every image. Baseline images for this assessment all match the accepted PR 41 manifest. The material fixed-version exception remains the legacy Buildx module described below.

`govulncheck` `1.9.0` scans 30 distinct Go executables from the final images, including compiler tools, frontend native binaries, Buildx, the capability helper, and gosu. Its feed reports modification time `2026-10-08T22:31:09Z`. No finding has a recorded fixed version. Binary findings do not establish runtime exploitability or complete source-level reachability.

npm `12.2.1` audits report zero findings for the Node, npm-replacement, Vite, and Playwright locks. The Markdown lock still reports five HIGH dependency entries from the single braces advisory; lock auditing cannot recognize the verified local patch. The audits did not report the new Undici issues even before the update. Upstream release evidence and behavior regressions establish the npm fix; zero audit findings do not establish complete security coverage.

The Docker Engine cleanup/Compose E2E, network E2E, and systemd host-adapter suites from `task_000524` were not repeated. Their implementation, daemon pin, Go tools, Python, and OS package versions are unchanged. That prior systemd check reports an ignored `ConditionPathIsSocket` key; host deployment still requires separate correction and qualification.

## Remaining findings

The current scanners are the source for the complete finding list. The notes below explain material exceptions and follow-up decisions from this assessment. No scan inventory is stored in the repository. A gate pass does not establish that unfixed findings are absent or that reported code is unreachable.

| Finding | Component | Assessment and required action |
| --- | --- | --- |
| [GHSA-xjj6-f33q-929c][undici-encoding] | Node `26.12.0`, built-in Undici `8.11.2` | Built-in `fetch` crashes after a caught rejection on excessive content codings and early close. A disposable-container probe confirms an unhandled `UND_ERR_SOCKET`. Upstream Undici fixes start at `8.12.2`; no newer stable Node `26.x` archive is published. Adopt and qualify a fixed Node release. npm's replacement does not change this runtime copy. |
| MEDIUM [CVE-2026-33997][docker-advisory] | Buildx's `github.com/docker/docker v28.5.2+incompatible` | The only Trivy match with a fixed version names Engine `29.3.1`. That release is unavailable on the legacy module path; its latest version is still `v28.5.2+incompatible`. The image contains a client, not a daemon, but embedded code is not claimed fixed. A qualified upstream migration or backport remains needed. |
| [GO-2026-5932][openpgp] and legacy Docker advisories | Unmaintained OpenPGP packages and Buildx | The Go feed records no compatible fixed version. Binary symbol detection does not establish runtime reachability. Retain upstream follow-up. |
| Critical OS advisories | Stable OS packages | See context below. |
| [CVE-2026-93748][cache-advisory] | `http-cache-semantics 4.3.0` | The shared-cache Set-Cookie / `max-stale` scenario still reproduces. npm's installed caller uses `shared: false`. Retain the observation for other callers; the version update alone does not establish a fix. |

The Node runtime finding is established by direct reproduction and upstream advisory ranges. Package-lock and image scans do not establish its absence. No new vulnerability ignore rule is added.

### Critical OS finding context

| Finding | Package | Affected images |
| --- | --- | --- |
| [CVE-2026-40468][gawk-overflow] | `gawk` | All seven job images |
| [CVE-2026-40469][gawk-32bit] | `gawk` | All seven job images |
| [CVE-2026-6653][libxml2] | `libxml2` | Go, Playwright, PostgreSQL |
| CVE-2026-43185 | `linux-libc-dev` | Go |

Debian classifies both gawk issues as minor and records upstream patch commits, but has no fixed Trixie package. CVE-2026-40469 affects 32-bit builds; this assessment retains the scanner's reported severity for the supported 64-bit images. Debian also classifies the libxml2 issue as minor for Trixie. Its fix is available in the development distribution; replacing the stable library needs separate compatibility qualification. `linux-libc-dev` contains userspace headers, not a running kernel.

[gawk-overflow]: https://security-tracker.debian.org/tracker/CVE-2026-40468
[gawk-32bit]: https://security-tracker.debian.org/tracker/CVE-2026-40469
[libxml2]: https://security-tracker.debian.org/tracker/CVE-2026-6653

### Cache-library observation

The existing Node smoke test verifies that `http-cache-semantics` `4.3.0` rejects cache reuse for a mixed `Vary: accept, *` header. The separate shared cache scenario below still permits reuse despite `Set-Cookie` and a computed maximum age of zero. Run it with the installed npm dependency in `ci-node`:

```javascript
const CachePolicy = require(
  '/opt/ci-tools/npm/12.2.1/node_modules/http-cache-semantics'
);
const request = {
  url: 'https://registry.example/package', method: 'GET', headers: {}
};
const response = {
  status: 200, headers: {
    'cache-control': 'max-age=600', 'set-cookie': 'test=fixture'
  }
};
const policy = new CachePolicy(request, response);
console.log(policy.maxAge()); // 0
console.log(policy.satisfiesWithoutRevalidation({
  ...request, headers: { 'cache-control': 'max-stale=3600' }
})); // true
```

The installed npm `make-fetch-happen` caller explicitly selects `shared: false`. Retain this explanation even when a scanner omits the library version from its advisory range. No new vulnerability ignore rule is added.

[undici-encoding]: https://github.com/nodejs/undici/security/advisories/GHSA-xjj6-f33q-929c
[docker-advisory]: https://github.com/moby/moby/security/advisories/GHSA-pxq6-2prw-chj9
[openpgp]: https://pkg.go.dev/vuln/GO-2026-5932
[cache-advisory]: https://github.com/advisories/GHSA-ch52-4w7c-c8xp

## Run current checks

Use the repository's build, runtime, and fixed HIGH/CRITICAL security gates:

```sh
tests/build-local-image.sh all
tests/smoke-local.sh all
tests/scan-local-image.sh all
```

Inspect all severities and unfixed findings separately. Use the selected Trivy version from the manifest and current vulnerability data:

```sh
for image in base go node vite playwright postgres utils net; do
  trivy image --image-src docker --scanners vuln --pkg-types os,library \
    "ci-${image}:test"
done
```

Audit each committed npm graph, and inspect Go executables with the Go feed:

```sh
for bundle in images/node/npm images/node/npm-runtime images/node/markdownlint \
  images/vite/npm images/playwright/npm; do
  npm audit --package-lock-only --prefix "$bundle"
done

docker run --rm ci-go:test sh -c \
  'govulncheck -mode=binary "$(command -v goose)"'
```

The Go command shows one executable. Qualification covers all distinct Go executables, including compiler tools, base tools, frontend native binaries, Buildx, the capability helper, and gosu. Extract binaries from images without the scanner and inspect them with `govulncheck -mode=binary` as well. Review scanner errors and exit statuses separately from reported vulnerabilities.

Use temporary or CI artifact storage when full reports are needed for review; keep generated CSV, JSON, and full Markdown inventories out of this repository. Update this document only with meaningful verification results, decisions, mitigations, and remaining actions.

## Delivery and release limits

Native AMD64 execution and multi-architecture SBOM/provenance/publication were not performed locally. They remain release gates. The repository currently runs automatic image CI only for `main` pushes and pull requests to `main`; the runbook's pull request to `develop` does not trigger that workflow.

Accept the implementation and residual findings through review, then qualify the accepted `main` revision before a separate stable release. No stable tag, release, or deployment is changed by this maintenance. Passing the existing security gate does not mean that all security issues are resolved.
