#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="${repository_root}/manifests/versions.json"
target=${1:-all}

case "$target" in
all | base | go | node | vite | playwright | postgres) ;;
*)
	printf \
		'usage: %s [all|base|go|node|vite|playwright|postgres]\n' \
		"$0" \
		>&2
	exit 64
	;;
esac

json() {
	jq -r "$1" "$manifest"
}

smoke_script() {
	local image=$1
	local script=$2
	shift 2
	docker run \
		--rm \
		--volume "${repository_root}/tests:/tests:ro" \
		"$@" \
		"$image" \
		bash "/tests/smoke/${script}.sh"
}

if [[ $target == all || $target == base ]]; then
	smoke_script \
		ci-base:test \
		base \
		--env "EXPECTED_CI_UID=$(json '.ci_user.uid')" \
		--env "EXPECTED_NODE_VERSION=$(json '.tools.node.runtime')" \
		--env \
		"EXPECTED_MARKDOWNLINT_VERSION=$(json '.tools.base.markdownlint_cli2.version')"
fi

if [[ $target == all || $target == go ]]; then
	smoke_script \
		ci-go:test \
		go \
		--env "EXPECTED_GO_VERSION=$(json '.tools.go.runtime')" \
		--env "EXPECTED_SQLC_VERSION=$(json '.tools.go.sqlc.version')" \
		--env "EXPECTED_GOOSE_VERSION=$(json '.tools.go.goose.version')" \
		--env \
		"EXPECTED_GOLANGCI_LINT_VERSION=$(json '.tools.go.golangci_lint.version')" \
		--env \
		"EXPECTED_GOIMPORTS_VERSION=$(json '.tools.go.goimports.version')" \
		--env \
		"EXPECTED_GOVULNCHECK_VERSION=$(json '.tools.go.govulncheck.version')"
fi

if [[ $target == all || $target == node ]]; then
	smoke_script \
		ci-node:test \
		node \
		--env "EXPECTED_NODE_VERSION=$(json '.tools.node.runtime')" \
		--env \
		"EXPECTED_NODE_BUNDLE_VERSION=$(json '.tools.node.bundle_version')" \
		--env "EXPECTED_PNPM_VERSION=$(json '.tools.node.pnpm')" \
		--env "EXPECTED_REDOCLY_VERSION=$(json '.tools.node.redocly')"
fi

if [[ $target == all || $target == vite ]]; then
	smoke_script \
		ci-vite:test \
		vite \
		--env \
		"EXPECTED_VITE_BUNDLE_VERSION=$(json '.tools.vite.bundle_version')" \
		--env \
		"EXPECTED_TYPESCRIPT_VERSION=$(json '.tools.vite.typescript')" \
		--env "EXPECTED_VITE_VERSION=$(json '.tools.vite.vite')" \
		--env "EXPECTED_VITEST_VERSION=$(json '.tools.vite.vitest')" \
		--env \
		"EXPECTED_COVERAGE_V8_VERSION=$(json '.tools.vite.coverage_v8')" \
		--env "EXPECTED_OXLINT_VERSION=$(json '.tools.vite.oxlint')" \
		--env \
		"EXPECTED_OXLINT_TSGOLINT_VERSION=$(json '.tools.vite.oxlint_tsgolint')" \
		--env "EXPECTED_OXFMT_VERSION=$(json '.tools.vite.oxfmt')"
fi

if [[ $target == all || $target == playwright ]]; then
	smoke_script \
		ci-playwright:test \
		playwright \
		--ipc host \
		--env \
		"EXPECTED_PLAYWRIGHT_VERSION=$(json '.tools.playwright.version')"
fi

if [[ $target == all || $target == postgres ]]; then
	"${repository_root}/tests/smoke-postgres.sh"
fi
