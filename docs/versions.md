# Image version inventory

This page provides one view of the explicitly pinned runtimes and first-order tools owned by each image. Child-image sections do not repeat inherited tools. Direct Debian packages are listed; transitive packages resolved from the reviewed snapshots are intentionally omitted. The [version manifest](../manifests/versions.json) and its referenced lockfiles remain authoritative for source revisions, dependency overrides, package revisions, checksums, and upstream image digests.

## `ci-utils`

The runtime inherits `ci-base`. Buildx and the capability helper reuse the existing `ci-go` toolchain; Go is not installed in the utility runtime.

| Component | Version |
| --- | --- |
| `Docker Buildx` | `0.38.2` |

Cleanup and its internal capability helper are repository-owned commands tied to the suite source revision, with no independent release stream.

## `ci-base`

| Component | Version |
| --- | --- |
| `Bash` | `5.3.20` |
| `Git` | `2.56.0` |
| `Git LFS` | `3.8.1` |
| `GitHub CLI` | `2.104.0` |
| `CPython` | `3.15.2` |
| `Docker CLI` | `29.9.3` |
| `Docker Compose` | `5.7.1` |
| `actionlint` | `1.7.12` |
| `gitleaks` | `8.30.1` |
| `jq` | `1.8.2` |
| `osv-scanner` | `2.7.1` |
| `ripgrep` | `15.2.0` |
| `ShellCheck` | `0.11.0` |
| `shellspec` | `0.28.1` |
| `shfmt` | `3.14.1` |
| `Trivy` | `0.76.2` |
| `yq` | `4.54.3` |

### Direct Debian packages

These packages are installed at exact revisions from the pinned Debian snapshots. Selected binary updates use the separate Sid snapshot with APT priority 1. Transitive packages remain snapshot-controlled and are covered by the image vulnerability scan. The Debian `git` package supplies system integration files; the exposed Git executable is the source-built version listed above. The Debian `bash` package remains installed for package management, with its binary diverted; the exposed Bash is the patched upstream version listed above.

| Package | Version |
| --- | --- |
| `bash` | `5.2.37-2+b10` |
| `bsdutils` | `1:2.42.4-1` |
| `ca-certificates` | `20250419+deb13u1` |
| `coreutils` | `9.7-3` |
| `curl` | `8.23.0-2` |
| `dash` | `0.5.12-12` |
| `diffutils` | `1:3.10-4` |
| `findutils` | `4.10.0-3` |
| `gawk` | `1:5.2.1-2+b1 (amd64) / 1:5.2.1-2+b2 (arm64)` |
| `git` | `1:2.47.3-0+deb13u1` |
| `grep` | `3.11-4 (amd64) / 3.11-4+b1 (arm64)` |
| `gzip` | `1.13-1+deb13u1` |
| `libacl1` | `2.4.0-1` |
| `libblkid1` | `2.42.4-1` |
| `libc-bin` | `2.43-7` |
| `libc-gconv-modules-extra` | `2.43-7` |
| `libc-l10n` | `2.43-7` |
| `libc6` | `2.43-7` |
| `libcurl3t64-gnutls` | `8.23.0-2` |
| `libcurl4-gnutls` | `8.23.0-2` |
| `libcurl4t64` | `8.23.0-2` |
| `libexpat1` | `2.10.0-1` |
| `liblastlog2-2` | `2.42.4-1` |
| `libmount1` | `2.42.4-1` |
| `libncursesw6` | `6.6+20260608-2` |
| `libnghttp3-9` | `1.17.0-1` |
| `libngtcp2-16` | `1.24.0-1` |
| `libngtcp2-crypto-gnutls8` | `1.24.0-1` |
| `libngtcp2-crypto-ossl0` | `1.24.0-1` |
| `libperl5.44` | `5.44.0-3` |
| `libsmartcols1` | `2.42.4-1` |
| `libsqlite3-0` | `3.54.1-2` |
| `libsystemd0` | `262.2-1` |
| `libtinfo6` | `6.6+20260608-2` |
| `libudev1` | `262.2-1` |
| `libuuid1` | `2.42.4-1` |
| `libx11-6` | `2:1.8.14-1` |
| `libx11-data` | `2:1.8.14-1` |
| `libxrender1` | `1:0.9.13-1` |
| `locales` | `2.43-7` |
| `login` | `1:4.16.0-2+really2.42.4-1` |
| `make` | `4.4.1-2` |
| `media-types` | `13.0.0` |
| `mount` | `2.42.4-1` |
| `ncurses-base` | `6.6+20260608-2` |
| `ncurses-bin` | `6.6+20260608-2` |
| `netbase` | `6.5` |
| `netcat-openbsd` | `1.229-1` |
| `openssl` | `3.5.7-1~deb13u3` |
| `perl` | `5.44.0-3` |
| `perl-base` | `5.44.0-3` |
| `perl-modules-5.44` | `5.44.0-3` |
| `procps` | `2:4.0.4-9` |
| `sed` | `4.9-2+deb13u1` |
| `tar` | `1.35+dfsg-3.1` |
| `tini` | `0.19.0-3+b8` |
| `tzdata` | `2026f-0+deb13u1` |
| `unzip` | `6.0-29+deb13u1` |
| `util-linux` | `2.42.4-1` |
| `wget` | `1.25.0-3` |
| `xz-utils` | `5.8.1-1+deb13u2` |
| `zip` | `3.0-15+deb13u1` |

## `ci-net`

The runtime inherits `ci-base` and adds these snapshot-pinned packages on both architectures. WireGuard kernel support is a Docker host prerequisite; no kernel image or `wireguard` metapackage is installed.

| Package | Version |
| --- | --- |
| `iproute2` | `6.15.0-1` |
| `iputils-ping` | `3:20240905-3` |
| `libpcap0.8t64` | `1.11.0-1` |
| `nftables` | `1.1.3-1` |
| `tcpdump` | `4.99.5-2` |
| `wireguard-tools` | `1.0.20210914-3` |

## `ci-go`

| Component | Version |
| --- | --- |
| `Go` | `1.27.4` |
| `linux-libc-dev` | `7.3.4-1` |
| `Hurl` | `8.1.0` |
| `sqlc` | `1.31.1` |
| `goose` | `3.30.1` |
| `golangci-lint` | `2.15.0` |
| `goimports` | `0.52.0` |
| `govulncheck` | `1.9.0` |

## `ci-node`

| Component | Version |
| --- | --- |
| `Node.js` | `26.13.1` |
| `npm` | `12.2.2` |
| `pnpm` | `12.20.0` |
| `markdownlint-cli2` | `0.24.0` |
| `@redocly/cli` | `2.77.0` |

## `ci-vite`

| Component | Version |
| --- | --- |
| `@typescript/native` | `7.0.2` |
| `TypeScript compatibility package` | `6.0.2` |
| `TypeScript legacy compiler` | `6.0.3` |
| `vite` | `8.3.8` |
| `vitest` | `5.1.0` |
| `@vitest/coverage-v8` | `5.1.0` |
| `oxlint` | `1.93.0` |
| `oxlint-tsgolint` | `7.0.2006` |
| `oxfmt` | `0.78.0` |

## `ci-playwright`

| Component | Version |
| --- | --- |
| `@playwright/test` | `1.65.0` |

| Package | Version |
| --- | --- |
| `libcups2t64` | `2.4.20-3` |
| `libx11-xcb1` | `2:1.8.14-1` |
| `libxi6` | `2:1.8.4-1` |
| `xserver-common` | `2:21.1.26-1` |
| `xvfb` | `2:21.1.26-1` |

## `ci-postgres`

| Component | Version |
| --- | --- |
| `PostgreSQL` | `18` |
| `pgvector` | `0.8.7` |
| `gosu` | `1.20` |

| Package | Version |
| --- | --- |
| `bsdutils` | `1:2.42.4-1` |
| `dirmngr` | `2.4.9-8` |
| `gnupg` | `2.4.9-8` |
| `gnupg-l10n` | `2.4.9-8` |
| `gpg` | `2.4.9-8` |
| `gpg-agent` | `2.4.9-8` |
| `gpgconf` | `2.4.9-8` |
| `gpgsm` | `2.4.9-8` |
| `libacl1` | `2.4.0-1` |
| `libblkid1` | `2.42.4-1` |
| `libc-bin` | `2.43-7` |
| `libc-gconv-modules-extra` | `2.43-7` |
| `libc-l10n` | `2.43-7` |
| `libc6` | `2.43-7` |
| `libgcrypt20` | `1.12.4-2` |
| `libgpg-error0` | `1.61-5` |
| `liblastlog2-2` | `2.42.4-1` |
| `libmount1` | `2.42.4-1` |
| `libncursesw6` | `6.6+20260608-2` |
| `libperl5.44` | `5.44.0-3` |
| `libsmartcols1` | `2.42.4-1` |
| `libsqlite3-0` | `3.54.1-2` |
| `libsystemd0` | `262.2-1` |
| `libtext-charwidth-perl` | `0.04-12+b2` |
| `libtinfo6` | `6.6+20260608-2` |
| `libudev1` | `262.2-1` |
| `libuuid1` | `2.42.4-1` |
| `locales` | `2.43-7` |
| `login` | `1:4.16.0-2+really2.42.4-1` |
| `mount` | `2.42.4-1` |
| `ncurses-base` | `6.6+20260608-2` |
| `ncurses-bin` | `6.6+20260608-2` |
| `perl` | `5.44.0-3` |
| `perl-base` | `5.44.0-3` |
| `perl-modules-5.44` | `5.44.0-3` |
| `util-linux` | `2.42.4-1` |
