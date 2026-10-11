# `ci-net`

`ghcr.io/myflow-xyz/ci-net` extends [`ci-base`](base.md) for network diagnostics
and isolated network integration tests.

## Included tools

| Package | Commands and purpose |
| --- | --- |
| `nftables` | `nft` for test-owned firewall tables and rules |
| `iproute2` | `ip`, `ss`, `tc`: interfaces, routes, sockets, traffic control |
| `iputils-ping` | `ping` for connectivity checks |
| `wireguard-tools` | `wg` and `wg-quick` for WireGuard configuration |
| `tcpdump` | Packet capture and capture-file inspection |

Both architecture package locks use the reviewed Debian snapshot inherited
from `ci-base`. See the [version inventory](../versions.md#ci-net) for exact
package revisions. Tools such as `curl` and `openssl` remain inherited.

Only WireGuard userspace tools are installed. The Debian `wireguard`
metapackage and kernel images are excluded. Installing packages inside a
container does not add WireGuard support to the running Docker host kernel.
The runner must already support WireGuard and nftables. Missing support is a
runner prerequisite failure; do not add `SYS_MODULE` or load host modules
from a test container.

## Runtime environment

The image retains the non-root `ci` user, UID `1001`, GID `2001`, `/workspace`,
and the shared environment from `ci-base`. Its default command is Bash. No
firewall rules, routes, tunnel configuration, or services are applied at startup.
The image grants no network capabilities. `ping` has no file capability or
set-user-ID permission; raw-socket permission is controlled at runtime.

## Security constraints

- Give each test container an independent network namespace. Use
  `--network none` when peers are unnecessary, or a dedicated internal Docker
  network for peer tests. Avoid `--network host` and do not join the runner's
  or an unrelated container's namespace.
- Never use `--privileged` or `--cap-add ALL`.
- Grant `NET_ADMIN` only to the disposable test container that changes network
  state. Do not grant it to the general CI job container, runner, Docker daemon
  container, or unrelated services. Ordinary command and version checks need
  no `NET_ADMIN`.
- Drop all capabilities before adding the required test capabilities.
  `NET_RAW` is needed for packet capture and raw-socket tests; restrict it to
  those test containers. Verify effective capabilities under the selected user.
- Avoid `nft flush ruleset`, including in failure cleanup. Create uniquely named
  test-owned tables and delete only resources created by that test. Do not load
  Debian's default `/etc/nftables.conf`, which starts with a global ruleset flush.
- Do not mount host network namespaces, the Docker socket, host module paths,
  or credentials into network test containers. Do not alter host firewall rules
  or routes from tests.

## Usage

Pin the image by its published index digest. Run ordinary diagnostics as the
default user without capabilities:

```sh
docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  ghcr.io/myflow-xyz/ci-net@sha256:<digest> ip -brief address
```

Tests that change interfaces, firewall rules, or WireGuard configuration require
an explicit capability grant. The following repository fixture uses a root
identity only in its disposable test container, with `NET_ADMIN` and `NET_RAW`.
This makes the effective capability set explicit without changing the image's
non-root default or the identity of the general CI job:

```sh
docker run --rm --interactive --network none --read-only \
  --user 0:0 --cap-drop ALL --cap-add NET_ADMIN --cap-add NET_RAW \
  --security-opt no-new-privileges \
  ghcr.io/myflow-xyz/ci-net@sha256:<digest> bash -s \
  < tests/smoke/net-rules.sh
```

The fixture verifies route and firewall behavior, then removes only its own
interface and table. It also cleans up after failure. The general CI job invokes
Docker through its existing trusted runner arrangement; the test container
receives no daemon access.

For capture in a test container using this capability set, use `tcpdump -p -Z
root` with an explicit interface, filter, and packet or time limit. This avoids
promiscuous mode and additional user-switching capabilities. Keep captures and
ephemeral WireGuard keys inside the disposable container. `wg-quick` features
such as `DNS=` require consumer-selected integration and are not configured by
this image.

## Verification

```sh
tests/build-local-image.sh net
tests/smoke-local.sh net
tests/scan-local-image.sh net
python3 tests/net-e2e.py
```

The E2E harness requires a local Unix Docker endpoint and a Linux daemon with
nftables and WireGuard support. It creates a unique internal network and
disposable containers without host mounts. It verifies permission denial,
namespace and capability boundaries through the Engine API and running
processes, targeted cleanup on success and injected failure, preservation of
unrelated tables, WireGuard peer traffic, and packet capture. It confirms removal
of its containers and network through the API. The ordinary smoke tests remain
unprivileged. Set `CI_NET_TEST_IMAGE` to test another locally available image.

CI runs these checks on native AMD64 and ARM64 runners before publication.
