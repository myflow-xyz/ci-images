#!/usr/bin/env bash

set -euo pipefail

[[ $(id -u) == 1001 ]]
[[ $(id -g) == 2001 ]]
command -v docker >/dev/null 2>&1 || {
	printf 'required Docker CLI is missing from the job image\n' >&2
	exit 1
}
[[ $(command -v docker) == /opt/ci-tools/bin/docker ]]
[[ $(docker --version) == "Docker version ${EXPECTED_DOCKER_VERSION},"* ]]
[[ $(docker compose version --short) == "${EXPECTED_COMPOSE_VERSION}" ]]
[[ ! -S /var/run/docker.sock ]]
[[ -z ${DOCKER_HOST:-} && -z ${DOCKER_API_VERSION:-} ]]
plugin=/usr/local/lib/docker/cli-plugins/docker-compose
[[ -x $plugin && ! -w $plugin ]]
[[ $(stat --format=%u "$plugin") == 0 ]]

for command in dockerd containerd ctr runc docker-compose; do
	if command -v "$command" >/dev/null 2>&1; then
		printf 'unexpected daemon or legacy Compose command: %s\n' "$command" >&2
		exit 1
	fi
done
[[ ! -e /usr/local/lib/docker/cli-plugins/docker-buildx ]]

test_directory=$(mktemp -d)
trap 'rm -rf "$test_directory"' EXIT
cat >"${test_directory}/compose.yaml" <<'YAML'
services:
  fixture:
    image: ci-base:test
    command: ["python3", "-m", "http.server", "8080"]
    ports: ["127.0.0.1::8080"]
    volumes: ["receipt:/receipt"]
volumes:
  receipt: {}
YAML

verify_offline_config() {
	docker compose --project-name ci-offline --file "${test_directory}/compose.yaml" \
		config --format json |
		jq --exit-status '
          .name == "ci-offline" and
          .services.fixture.image == "ci-base:test" and
          .services.fixture.ports[0].target == 8080 and
          .volumes.receipt.name == "ci-offline_receipt"
        ' >/dev/null
}
verify_offline_config

export DOCKER_CONFIG="${test_directory}/private-config"
install -d -m 0700 "$DOCKER_CONFIG"
[[ $(docker compose version --short) == "${EXPECTED_COMPOSE_VERSION}" ]]
verify_offline_config
[[ ! -e ${DOCKER_CONFIG}/cli-plugins ]]

if docker info >"${test_directory}/no-daemon.log" 2>&1; then
	printf 'daemon operation unexpectedly succeeded without an endpoint\n' >&2
	exit 1
fi
grep --ignore-case --extended-regexp \
	'cannot connect|connection refused|no such file or directory' \
	"${test_directory}/no-daemon.log" >/dev/null
[[ ! -S /var/run/docker.sock ]]
printf 'non-root Docker %s / Compose %s offline discovery and no-access checks passed\n' \
	"$EXPECTED_DOCKER_VERSION" "$EXPECTED_COMPOSE_VERSION"
