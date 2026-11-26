#!/usr/bin/env bash

# Only the disposable nested daemon receives cleanup requests.
set -euo pipefail

# Qualify the daemon's native platform, as the image resolver does.
unset DOCKER_DEFAULT_PLATFORM

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dind_image=docker.io/library/docker:29.10.1-dind@sha256:fbbc96e0af32cdc190aff92ba97a1281a115351a723afe21af78879cc55126b0
image_store=${CI_UTILS_TEST_IMAGE_STORE:-containerd}
case "$image_store" in
containerd) snapshotter=true ;;
classic) snapshotter=false ;;
*)
	printf 'test image store must be containerd or classic\n' >&2
	exit 2
	;;
esac
fixture="ci-utils-e2e-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
socket=unix:///run/ci-utils-test/docker.sock
assets=
daemon_args=()
if [[ ${1:-} == --native ]]; then
	assets=$(cd "${2:?native release directory is required}" && pwd -P)
	version=${3:?native release version is required}
	shift 3
else
	image_id=$(docker image inspect "${CI_UTILS_TEST_IMAGE:-ci-utils:test}" --format '{{.Id}}')
fi
outer_daemon=$(docker info --format '{{.ID}}')

cleanup() {
	local status=$?
	trap - EXIT
	if ((status != 0)); then
		docker logs --tail 60 "$fixture" >&2 || true
	fi
	docker rm --force "${fixture}-controller" "$fixture" >/dev/null 2>&1 || true
	docker volume rm "${fixture}-run" "${fixture}-data" >/dev/null 2>&1 || true
	if [[ -n $assets ]]; then
		rm -rf -- "$certs"
	else
		docker image rm "${fixture}:fixture" >/dev/null 2>&1 || true
	fi
	exit "$status"
}
if [[ -n $assets ]]; then
	certs=$(mktemp -d)
fi
trap cleanup EXIT

if [[ -n $assets ]]; then
	openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=ci-utils-fixture' \
		-addext 'subjectAltName=DNS:ghcr.io,DNS:api.github.com,DNS:github.com,DNS:raw.githubusercontent.com' \
		-keyout "$certs/key.pem" -out "$certs/ca.crt" 2>/dev/null
	daemon_args+=(--add-host ghcr.io:127.0.0.1 --add-host api.github.com:127.0.0.1
		--add-host github.com:127.0.0.1 --add-host raw.githubusercontent.com:127.0.0.1
		--mount "type=bind,src=$certs/ca.crt,dst=/etc/docker/certs.d/ghcr.io/ca.crt,readonly")
fi

if ! docker image inspect "$dind_image" >/dev/null 2>&1; then
	docker pull --quiet "$dind_image" >/dev/null
fi
docker volume create "${fixture}-run" >/dev/null
docker volume create "${fixture}-data" >/dev/null
# Privilege is confined to the test daemon. No host socket, root, or PID namespace
# is mounted. The production maintenance child retains its hardened profile.
docker run --detach --pull=never --privileged --network=none \
	"${daemon_args[@]}" \
	--name "$fixture" --label xyz.myflow.cleanup.protect=true \
	--env DOCKER_TLS_CERTDIR= \
	--mount "type=volume,src=${fixture}-run,dst=/run/ci-utils-test" \
	--mount "type=volume,src=${fixture}-data,dst=/var/lib/docker" \
	"$dind_image" dockerd --host="$socket" --feature "containerd-snapshotter=${snapshotter}" --label "ci-utils-test=${fixture}" >/dev/null

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
if [[ -n $assets ]]; then
	docker run --rm --init --network="container:$fixture" --user=0 \
		--name "${fixture}-controller" \
		--mount "type=volume,src=${fixture}-run,dst=/run/ci-utils-test" \
		--mount "type=volume,src=${fixture}-data,dst=/var/lib/docker,readonly" \
		--mount "type=bind,src=${repository_root},dst=/workspace,readonly" \
		--mount "type=bind,src=${assets},dst=/assets,readonly" \
		--mount "type=bind,src=${certs},dst=/fixture-tls,readonly" \
		--env "CI_UTILS_TEST_FIXTURE=${fixture}" --env "CI_UTILS_OUTER_DAEMON=${outer_daemon}" \
		--env SSL_CERT_FILE=/fixture-tls/ca.crt \
		"${CI_UTILS_NATIVE_CONTROLLER:-ci-base:test}" bash -ec '
			/workspace/scripts/ci-utils/install.sh "$1" --from-dir /assets
			if command -v shellspec >/dev/null; then
				cd /workspace/scripts
				export CI_UTILS_BIN=/usr/local/bin CI_UTILS_PROBE_ENDPOINT=unix:///run/ci-utils-test/docker.sock
				CI_UTILS_DAEMON_ID=$(docker --host "$CI_UTILS_PROBE_ENDPOINT" info --format "{{.ID}}")
				export CI_UTILS_DAEMON_ID
				shellspec tests/ci-utils
			fi
			exec python3 -B /workspace/tests/utils/native_docker_e2e.py
		' bash "$version"
	exit
fi
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
	"$image_id" python3 -B /workspace/tests/utils/docker_e2e.py "$@"
