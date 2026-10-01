#!/usr/bin/env bash

set -euo pipefail

[[ $(id -u) == 1001 && $(id -g) == 2001 ]]
[[ ${DOCKER_HOST:?explicit daemon access is required} == unix:///var/run/docker.sock ]]
[[ $(docker info --format '{{.OSType}}') == linux ]]
server=$(docker version --format '{{json .Server}}')
printf '%s\n' "$server" | jq --exit-status '.Version | test("^29\\.[3-8]\\.")' >/dev/null
printf 'Compose integration: client %s; platform %s; daemon %s; API %s\n' \
	"$(docker --version)" "$(uname -m)" \
	"$(jq -r .Version <<<"$server")" "$(jq -r .ApiVersion <<<"$server")"

test_directory=$(mktemp -d)
project="ci-client-$(date +%s)-${RANDOM}-${RANDOM}"
export CI_IMAGES_RECEIPT=$project
export DOCKER_CONFIG="${test_directory}/docker-config"
install -d -m 0700 "$DOCKER_CONFIG"
compose_file="${test_directory}/compose.yaml"
compose() {
	docker compose --project-name "$project" --file "$compose_file" "$@"
}
cleanup() {
	compose down --volumes --remove-orphans >/dev/null
}
finish() {
	local result=$?
	trap - EXIT
	if ! cleanup; then result=1; fi
	rm -rf "$test_directory"
	exit "$result"
}
trap finish EXIT
cat >"$compose_file" <<'YAML'
services:
  receipt:
    image: ${CI_IMAGES_FIXTURE_IMAGE:?}
    pull_policy: never
    environment:
      RECEIPT: ${CI_IMAGES_RECEIPT:?}
    command:
      - python3
      - -u
      - -c
      - |
        import http.server, os
        with open('/workspace/receipt.txt', 'w') as receipt:
            receipt.write(os.environ['RECEIPT'])
        http.server.HTTPServer(('0.0.0.0', 8080), http.server.SimpleHTTPRequestHandler).serve_forever()
    ports: ["127.0.0.1::8080"]
    volumes: ["receipt:/workspace"]
volumes:
  receipt: {}
YAML

assert_cleaned() {
	local owned_filter="label=com.docker.compose.project=${project}"
	local containers networks volumes
	containers=$(docker container ls --all --quiet --filter "$owned_filter")
	networks=$(docker network ls --quiet --filter "$owned_filter")
	volumes=$(docker volume ls --quiet --filter "$owned_filter")
	[[ -z $containers && -z $networks && -z $volumes ]]
}

start_and_verify() {
	compose up --detach >/dev/null
	local endpoint receipt
	endpoint=$(compose port receipt 8080)
	[[ $endpoint =~ ^127\.0\.0\.1:[0-9]+$ ]]
	if ! receipt=$(curl --fail --silent --show-error --max-time 2 \
		--retry 15 --retry-delay 1 --retry-all-errors --retry-max-time 30 \
		"http://${endpoint}/receipt.txt"); then
		compose logs --no-color receipt >&2
		return 1
	fi
	[[ $receipt == "$CI_IMAGES_RECEIPT" ]]
	[[ $(compose ps --format json | jq -r .State) == running ]]
	[[ -n $(docker volume ls --quiet --filter "label=com.docker.compose.project=${project}") ]]
}

start_and_verify
cleanup
assert_cleaned

# Verify exit cleanup when receipt validation fails after startup.
set +e
(
	set -e
	trap cleanup EXIT
	start_and_verify
	curl --fail --silent --output /dev/null --max-time 5 \
		"http://$(compose port receipt 8080)/missing-receipt"
)
failure_status=$?
set -e
if [[ $failure_status != 22 ]]; then
	printf 'intentional HTTP failure returned unexpected status: %s\n' "$failure_status" >&2
	exit 1
fi
assert_cleaned
printf 'non-root Compose HTTP success, intentional failure and owned cleanup passed\n'
