#!/usr/bin/env bash

# Only the disposable nested daemon receives cleanup requests.
set -euo pipefail

# Run fixtures on the selected local daemon's platform.
unset DOCKER_DEFAULT_PLATFORM

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
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
assets=$(cd "${1:?native release directory is required}" && pwd -P)
version=${2:?native release version is required}
certs=$(mktemp -d)
outer_daemon=$(docker info --format '{{.ID}}')

cleanup() {
	local status=$?
	trap - EXIT
	if ((status != 0)); then
		docker logs --tail 60 "$fixture" >&2 || true
	fi
	docker rm --force "${fixture}-controller" "$fixture" >/dev/null 2>&1 || true
	docker volume rm "${fixture}-run" "${fixture}-data" >/dev/null 2>&1 || true
	rm -rf -- "$certs"
	exit "$status"
}
trap cleanup EXIT

openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=ci-utils-fixture' \
	-addext 'subjectAltName=DNS:ghcr.io,DNS:api.github.com,DNS:github.com,DNS:raw.githubusercontent.com' \
	-keyout "$certs/key.pem" -out "$certs/ca.crt" 2>/dev/null

if ! docker image inspect "$dind_image" >/dev/null 2>&1; then
	docker pull --quiet "$dind_image" >/dev/null
fi
docker volume create "${fixture}-run" >/dev/null
docker volume create "${fixture}-data" >/dev/null
# Privilege is confined to the test daemon. No host socket, root, or PID namespace
# is mounted. The installed worker can reach only the disposable daemon.
docker run --detach --pull=never --privileged --network=none \
	--add-host ghcr.io:127.0.0.1 --add-host api.github.com:127.0.0.1 \
	--add-host github.com:127.0.0.1 --add-host raw.githubusercontent.com:127.0.0.1 \
	--mount "type=bind,src=$certs/ca.crt,dst=/etc/docker/certs.d/ghcr.io/ca.crt,readonly" \
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
# A small runnable workload is needed for Compose, volume and in-use image tests.
docker exec "$fixture" tar -C / -cf /run/ci-utils-test/workload.tar bin lib
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
			shellspec ci-utils/tests
		fi
		cd /workspace/scripts/ci-utils
		python3 -B -m tests.maintenance.native_docker_e2e
		socket=unix:///run/ci-utils-test/docker.sock
		docker --host "$socket" import /run/ci-utils-test/workload.tar "$CI_UTILS_TEST_FIXTURE:fixture" >/dev/null
		CI_UTILS_WORKLOAD_IMAGE=$(docker --host "$socket" image inspect "$CI_UTILS_TEST_FIXTURE:fixture" --format "{{.Id}}")
		export CI_UTILS_WORKLOAD_IMAGE
		exec python3 -B -m tests.maintenance.docker_e2e
	' bash "$version"
