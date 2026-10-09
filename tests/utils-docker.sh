#!/usr/bin/env bash

# Only the disposable nested daemon receives cleanup requests.
set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dind_image=docker.io/library/docker:29.9.0-dind@sha256:0b6d18a4a222e71c88be6034926b4f6cde2fc33c2218643d03ccfddc65995470
fixture="ci-utils-e2e-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
socket=unix:///run/ci-utils-test/docker.sock
image_id=$(docker image inspect ci-utils:test --format '{{.Id}}')
outer_daemon=$(docker info --format '{{.ID}}')

cleanup() {
	local status=$?
	trap - EXIT
	if ((status != 0)); then
		docker logs --tail 60 "$fixture" >&2 || true
	fi
	docker rm --force "${fixture}-controller" "$fixture" >/dev/null 2>&1 || true
	docker volume rm "${fixture}-run" "${fixture}-data" >/dev/null 2>&1 || true
	docker image rm "${fixture}:fixture" >/dev/null 2>&1 || true
	exit "$status"
}
trap cleanup EXIT

if ! docker image inspect "$dind_image" >/dev/null 2>&1; then
	docker pull --quiet "$dind_image" >/dev/null
fi
docker volume create "${fixture}-run" >/dev/null
docker volume create "${fixture}-data" >/dev/null
# Privilege is confined to the test daemon. No host socket, root, or PID namespace
# is mounted. The production maintenance child retains its hardened profile.
docker run --detach --pull=never --privileged --network=none \
	--name "$fixture" --label xyz.myflow.cleanup.protect=true \
	--env DOCKER_TLS_CERTDIR= \
	--mount "type=volume,src=${fixture}-run,dst=/run/ci-utils-test" \
	--mount "type=volume,src=${fixture}-data,dst=/var/lib/docker" \
	"$dind_image" dockerd --host="$socket" --label "ci-utils-test=${fixture}" >/dev/null

ready=false
for ((attempt = 0; attempt < 60; attempt++)); do
	if docker exec "$fixture" docker --host "$socket" info >/dev/null 2>&1; then
		ready=true
		break
	fi
	sleep 1
done
"$ready" || {
	printf 'disposable Docker daemon did not become ready\n' >&2
	exit 1
}
docker image tag "$image_id" "${fixture}:fixture"
docker image save "${fixture}:fixture" | docker exec --interactive "$fixture" docker --host "$socket" image load >/dev/null
imported_image=$(docker exec "$fixture" docker --host "$socket" image inspect "${fixture}:fixture" --format '{{.Id}}')
# Docker image stores can identify an imported manifest differently. Verify the
# actual filesystem and runtime configuration before using the inner store's ID.
outer_image=$(docker image inspect "$image_id")
inner_image=$(docker exec "$fixture" docker --host "$socket" image inspect "$imported_image")
python3 - "$outer_image" "$inner_image" <<'PY'
import json, sys
outer, inner = [json.loads(value)[0] for value in sys.argv[1:]]
assert outer['RootFS'] == inner['RootFS'], 'import changed filesystem layers'
for field in ('Cmd', 'Entrypoint', 'User', 'Env', 'WorkingDir', 'Volumes', 'Labels'):
    assert outer['Config'].get(field) == inner['Config'].get(field), f'import changed {field}'
PY

# The controller shares only the disposable daemon's PID and storage namespaces,
# as required by the host lease protocol. It cannot reach the outer daemon.
docker run --rm --init --pull=never --network=none --user=0 \
	--name "${fixture}-controller" --pid="container:${fixture}" \
	--label xyz.myflow.cleanup.protect=true \
	--mount "type=volume,src=${fixture}-run,dst=/run/ci-utils-test" \
	--mount "type=volume,src=${fixture}-data,dst=/var/lib/docker,readonly" \
	--mount "type=bind,src=${repository_root},dst=/workspace,readonly" \
	--env "CI_UTILS_TEST_FIXTURE=${fixture}" --env "CI_UTILS_TEST_IMAGE=${imported_image}" \
	--env "CI_UTILS_OUTER_DAEMON=${outer_daemon}" \
	"$image_id" python3 -B /workspace/tests/utils/docker_e2e.py
