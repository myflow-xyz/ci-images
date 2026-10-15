# Stable toolchain maintenance and security qualification

This is the maintained qualification guide and latest verification record.
Keep scan procedures, compatibility decisions, and material exceptions here.
Generate current findings with the scanners; do not commit generated scan
inventories. Record the review date, source revision, and manifest hash with
each assessment. Previous assessments remain in Git history.

PMem `task_000524` refreshes the eight-image suite from `main` commit
`c9250a386f1d8ed183c25311a39e307949270624`. The review uses upstream metadata
and vulnerability feeds retrieved on 2026-10-15 UTC. It preserves the existing
runtime release lines, image names, user/cache contracts, and release policy.
This record qualifies the local implementation; it does not confirm publication.

## Dependency selection

The audit covered manifest tools and overrides, all five npm locks, the Go
capability-helper module, both architectures' Debian package candidates, OCI
parents, build infrastructure, six pinned actions, and the test-daemon image.
The [manifest](../../manifests/versions.json) and locks contain exact pins.

| Component | Previous | Selected |
| --- | --- | --- |
| Debian snapshot | `20261011T082723Z` | `20261015T030350Z` |
| curl and libcurl | `8.14.1-2+deb13u5` | `8.14.1-2+deb13u7` |
| Node.js | `26.11.1` | `26.12.0` |
| Docker CLI | `29.9.0` | `29.9.1` |
| OSV-Scanner | `2.6.0` | `2.7.0` |
| Trivy, including the Actions scanner | `0.75.0` | `0.76.0` |
| Goose | `3.28.0` | `3.29.0` |
| Redocly CLI | `2.62.1` | `2.63.0` |
| Vitest and V8 coverage | `5.0.3` | `5.0.4` |
| Oxlint | `1.87.0` | `1.88.0` |
| Playwright and matching Chromium installer | `1.64.0` | `1.64.1` |
| npm's `ip-address` replacement | `10.7.3` | `10.7.4` |
| gitleaks compression override | `1.20.1` | `1.20.3` |
| gitleaks RAR decoder override | `2.4.3` | `2.4.5` |
| Goose libc override | `1.77.1` | `1.78.0` |

The Vite lock also advances Rolldown to `1.2.14`, PostCSS to `8.5.30`, and
upstream-selected Vitest/Oxlint dependencies. The capability helper advances
`go-winio`, containerd, gRPC Gateway, compression, and Google API/RPC modules.
Upstream Go tool graphs otherwise follow their selected releases and reviewed
overrides; this change does not force arbitrary transitive major upgrades.

The official [Node release](https://nodejs.org/en/blog/release/v26.12.0),
[Docker release notes](https://docs.docker.com/engine/release-notes/29/),
[OSV-Scanner release](https://github.com/google/osv-scanner/releases/tag/v2.7.0),
[Goose release](https://github.com/pressly/goose/releases/tag/v3.29.0), and
[Trivy changelog](https://github.com/aquasecurity/trivy/blob/v0.76.0/CHANGELOG.md)
support the release selection. Node archives use official SHA-256 values for
AMD64 and ARM64. Debian candidates were resolved through signed snapshot
indexes for both architectures; only curl changed in the direct package locks.

### Retained versions and compatibility limits

- [Go `1.27.2`](https://go.dev/dl/?mode=json), Vite `8.3.4`, TypeScript `7.0.2`,
  the paired tsgolint source, npm `12.2.0`, and the remaining manifest tools
  were already current on their selected compatible release lines.
- CPython remains on `3.14.8`; adopting the new `3.15` feature line requires
  separate compatibility qualification.
- Oxfmt remains on `0.72.0`: [the `0.73.0` release][oxfmt-release] explicitly
  changes CLI migration and TOML configuration behavior. Oxlint's `1.88.0`
  breaking-change entries concern internal Rust AST APIs; the installed CLI
  remains on its existing major line and passes its image smoke contract.
- pnpm remains on the official native release `12.11.2`. The npm registry
  contains newer version records, but both its `latest` tag and the GitHub
  latest release still select `12.11.2`. Undici remains on the compatible
  `6.29.0` line used by npm's reviewed replacement.
- Debian, pgvector, Dockerfile frontend `1.28.0`, BuildKit `0.34.0`, the Syft
  generator `1.12.0`, Buildx `0.38.0`, and action pins still match upstream
  release metadata. Action tag commits were checked individually.
- The isolated Docker test daemon remains on the current published
  `29.9.0-dind` digest. A `29.9.1-dind` image was unavailable at selection.
- Playwright consumers must retain the existing exact package/browser matching
  contract when adopting this suite: the selected package is now `1.64.1`.

[oxfmt-release]: https://github.com/oxc-project/oxc/releases/tag/oxfmt_v0.73.0

## Security changes

The stable Debian update resolves four curl advisories:
[CVE-2026-8286][curl-8286], [CVE-2026-8927][curl-8927],
[CVE-2026-92392][curl-92392], and [CVE-2026-8924][curl-8924]. Baseline scans
reported 84 fixed-version matches across curl/libcurl in seven job images.
The rebuilt images remove all 84 matches. PostgreSQL had none of these matches.

The repository already applies depth guards for [the braces advisory][braces]
in the Node image. The host CI documentation job previously installed the
unpatched package. It now applies the same checksum-guarded patch and runs the
existing public API and Markdown CLI security regressions before linting.
That regression failed on a clean unpatched install and passed after the patch.
Package version `3.0.3` is preserved so scanners and SBOMs retain the advisory.

[curl-8286]: https://security-tracker.debian.org/tracker/CVE-2026-8286
[curl-8927]: https://security-tracker.debian.org/tracker/CVE-2026-8927
[curl-92392]: https://security-tracker.debian.org/tracker/CVE-2026-92392
[curl-8924]: https://security-tracker.debian.org/tracker/CVE-2026-8924
[braces]: https://github.com/advisories/GHSA-vfj7-8cjw-p6xm

## Verification

All eight images built and passed native ARM64 smoke checks. The checks cover
non-root identity, caches, protected Git configuration, Go race execution,
sqlc generation/CEL rules, npm replacements, Markdown math and depth guards,
frontend compiler/lint/test commands, repository-local tool precedence,
Chromium launch, PostgreSQL/pgvector, and Docker/Compose offline behavior.
A new Goose smoke fixture verifies SQLite migration application, persisted data,
and rollback after the Goose/libc updates. The capability helper's race tests
pass during its image build.

Static/release/publication/helper regressions, shell syntax, ShellCheck, shfmt,
workflow validation, all eight Dockerfile checks, and Markdown lint pass.
The workflow tests pass 3 cases, image-resolution tests pass 16 cases, and
Linux utility tests pass 114 cases. Four network E2E cases pass. Real-daemon
Compose fixtures pass HTTP behavior, intentional failure, and owned cleanup.
The containerd utility suite passes 16 cases with its documented dangling-image
case skipped; all 17 cases pass with classic overlay2, including that case.

Standalone systemd verification returns success when its missing Docker service
dependency is supplied as a test fixture. It reports the pre-existing warning
`Unknown key 'ConditionPathIsSocket' in section [Unit], ignoring.` The service
examples are unchanged from the baseline; correcting that unsupported condition
requires separate host-adapter review. This check does not qualify deployment.

All image labels and final scans match manifest SHA-256:

`56346731b530731d092704906853390cfde847ec9bdb3f3cf8a644de3dc693b3`

Trivy `0.76.0` scans all severities and OS/library packages with vulnerability
metadata updated at `2026-10-15T01:13:01Z`. The unchanged fixed HIGH/CRITICAL
scan gate passes on all eight images. Baseline inventories used local builds;
three matched the baseline manifest and five used the preceding local manifest.
They establish the installed curl versions, not exact published-main layers.

`govulncheck` `1.9.0` scans 30 distinct Go executables, including Go compiler
tools, frontend native binaries, Buildx, the capability helper, and gosu. Its
current feed reports modification time `2026-10-08T22:31:09Z`. No finding with
a recorded fixed version remains in that feed. Binary findings do not establish
runtime exploitability or complete source-level reachability.

npm `12.2.0` audits report zero findings for the Node, npm-replacement, Vite,
and Playwright locks. The Markdown lock reports five HIGH dependency entries
from the single braces advisory. Lockfile auditing cannot recognize the local
build-time patch; its behavior is checked separately.

## Remaining findings

The current scanners are the source for the complete finding list. The notes
below explain material exceptions and follow-up decisions from this assessment.
No scan inventory is stored in the repository. A gate pass does not establish
that unfixed findings are absent or that reported code is unreachable.

- The only remaining Trivy match with a fixed version is MEDIUM
  [CVE-2026-33997][docker-advisory] in Buildx's legacy
  `github.com/docker/docker v28.5.2+incompatible` module. The advisory concerns
  Docker Engine plugin privilege validation and names Engine `29.3.1` as fixed.
  The legacy module's latest release is still `v28.5.2+incompatible`; querying
  its `v29.3.1+incompatible` module returns 404. The utility image contains a
  client, not a Docker daemon. A module migration or qualified backport remains
  upstream work; this report neither suppresses the finding nor claims the
  embedded code is fixed.
- The Go feed retains [GO-2026-5932][openpgp] in the unmaintained OpenPGP
  packages and five legacy Docker-module advisories in Buildx. Current module
  releases provide no recorded compatible fix. Symbol detection is preserved
  by the scanner; runtime reachability remains unqualified.
- Critical OS findings remain against `gawk`, `libxml2`, and `linux-libc-dev`,
  with no fixed version recorded for the installed stable packages. The latter
  is userspace development headers and does not describe the host's kernel.
  These and other unfixed OS findings remain review risks.
- `http-cache-semantics` `4.3.0` still reproduces the shared-cache Set-Cookie /
  `max-stale` scenario reproduced below.
  The installed npm caller still explicitly uses `shared: false`. Retain the
  manual [CVE-2026-93748][cache-advisory] observation for other callers; the
  package upgrade is not proof that this advisory is resolved.

### Critical OS finding context

| Finding | Package | Affected images |
| --- | --- | --- |
| [CVE-2026-40468][gawk-overflow] | `gawk` | All seven job images |
| [CVE-2026-40469][gawk-32bit] | `gawk` | All seven job images |
| [CVE-2026-6653][libxml2] | `libxml2` | Go, Playwright, PostgreSQL |
| CVE-2026-43185 | `linux-libc-dev` | Go |

Debian classifies both gawk issues as minor and records upstream patch commits,
but has no fixed Trixie package. CVE-2026-40469 affects 32-bit builds; this
assessment retains the scanner's reported severity for the supported 64-bit
images. Debian also classifies the libxml2 issue as minor for Trixie. Its fix is
available in the development distribution; replacing the stable library needs
separate compatibility qualification. `linux-libc-dev` contains userspace
headers, not a running kernel.

[gawk-overflow]: https://security-tracker.debian.org/tracker/CVE-2026-40468
[gawk-32bit]: https://security-tracker.debian.org/tracker/CVE-2026-40469
[libxml2]: https://security-tracker.debian.org/tracker/CVE-2026-6653

### Cache-library observation

The existing Node smoke test verifies that `http-cache-semantics` `4.3.0`
rejects cache reuse for a mixed `Vary: accept, *` header. The separate shared
cache scenario below still permits reuse despite `Set-Cookie` and a computed
maximum age of zero. Run it with the installed npm dependency in `ci-node`:

```javascript
const CachePolicy = require(
  '/opt/ci-tools/npm/12.2.0/node_modules/http-cache-semantics'
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

The installed npm `make-fetch-happen` caller explicitly selects `shared: false`.
Retain this explanation even when a scanner omits the library version from
its advisory range. No new vulnerability ignore rule is added.

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

Inspect all severities and unfixed findings separately. Use the selected Trivy
version from the manifest and current vulnerability data:

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

The Go command shows one executable. Qualification covers all distinct Go
executables, including compiler tools, base tools, frontend native binaries,
Buildx, the capability helper, and gosu. Extract binaries from images without
the scanner and inspect them with `govulncheck -mode=binary` as well. Review
scanner errors and exit statuses separately from reported vulnerabilities.

Use temporary or CI artifact storage when full reports are needed for review;
keep generated CSV, JSON, and full Markdown inventories out of this repository.
Update this document only with meaningful verification results, decisions,
mitigations, and remaining actions.

## Delivery and release limits

Native AMD64 execution and multi-architecture SBOM/provenance/publication were
not performed locally. They remain release gates. The repository currently
runs automatic image CI only for `main` pushes and pull requests to `main`;
the runbook's pull request to `develop` does not trigger that workflow.

Accept the implementation and residual findings through review, then qualify
the accepted `main` revision before a separate stable release. No stable tag,
release, or deployment is changed by this maintenance. Passing the existing
security gate does not mean that all security issues are resolved.
