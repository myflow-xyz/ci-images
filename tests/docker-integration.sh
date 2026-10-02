#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
socket=${CI_IMAGES_DOCKER_SOCKET:?explicitly supply the approved Linux Docker socket}
[[ -S $socket ]] || {
	printf 'approved Docker socket is unavailable: %s\n' "$socket" >&2
	exit 1
}
# Inspect the supplied endpoint's numeric group inside the daemon's mount namespace.
socket_gid=$(
	docker run --rm --network none --volume "${socket}:/socket:ro" \
		ci-base:test stat --format=%g /socket
)
[[ $socket_gid =~ ^[0-9]+$ ]]

docker run --rm --network host \
	--group-add "$socket_gid" \
	--volume "${socket}:/var/run/docker.sock:ro" \
	--volume "${repository_root}/tests:/tests:ro" \
	--env DOCKER_HOST=unix:///var/run/docker.sock \
	--env CI_IMAGES_FIXTURE_IMAGE=ci-base:test \
	ci-base:test bash /tests/smoke/docker-integration.sh
