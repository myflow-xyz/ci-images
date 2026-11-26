#!/usr/bin/env bash

# Run this complete lifecycle inside `ci-docker-maintenance job`.
set -euo pipefail

: "${CI_DOCKER_JOB_ID:?run through the shared admission wrapper}"
: "${CI_DOCKER_ENDPOINT:?the host wrapper must select the daemon}"
: "${CI_COMPOSE_FILE:?set the reviewed Compose file with disposable project volumes}"

project="ci-${CI_DOCKER_JOB_ID}"
completion_unknown=false

docker_operation() {
	if docker --host "$CI_DOCKER_ENDPOINT" "$@"; then
		return 0
	fi
	completion_unknown=true
	return 1
}

finalize() {
	local job_status=$?
	trap - EXIT
	if "$completion_unknown"; then
		printf 'Docker completion is unknown; job admission remains blocked\n' >&2
		exit 6
	fi
	if ! docker_operation compose --project-name "$project" --file "$CI_COMPOSE_FILE" \
		down --volumes --remove-orphans; then
		printf 'Docker finalization failed; reconcile the job before retrying\n' >&2
		exit 6
	fi
	/usr/local/libexec/ci-utils/ci-docker-maintenance job-complete
	exit "$job_status"
}

trap finalize EXIT
trap 'completion_unknown=true; exit 130' INT TERM
docker_operation compose --project-name "$project" --file "$CI_COMPOSE_FILE" up --detach

# This command must join its children and finish all daemon work before return.
# Route Docker calls through a qualified adapter; the example treats every
# failed Docker command as unknown completion, even a known test failure.
"$@"
