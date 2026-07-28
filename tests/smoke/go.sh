#!/usr/bin/env bash

set -euo pipefail

expected_go=${EXPECTED_GO_VERSION:?EXPECTED_GO_VERSION is not set}
expected_sqlc=${EXPECTED_SQLC_VERSION:?EXPECTED_SQLC_VERSION is not set}
expected_goose=${EXPECTED_GOOSE_VERSION:?EXPECTED_GOOSE_VERSION is not set}
: "${EXPECTED_GOOSE_GRPC_VERSION:?EXPECTED_GOOSE_GRPC_VERSION is not set}"
: "${EXPECTED_GOOSE_X_CRYPTO_VERSION:?EXPECTED_GOOSE_X_CRYPTO_VERSION is not set}"
: "${EXPECTED_GOOSE_X_NET_VERSION:?EXPECTED_GOOSE_X_NET_VERSION is not set}"
: "${EXPECTED_GOLANGCI_LINT_VERSION:?EXPECTED_GOLANGCI_LINT_VERSION is not set}"
: "${EXPECTED_GOIMPORTS_VERSION:?EXPECTED_GOIMPORTS_VERSION is not set}"
: "${EXPECTED_GOVULNCHECK_VERSION:?EXPECTED_GOVULNCHECK_VERSION is not set}"
expected_golangci=$EXPECTED_GOLANGCI_LINT_VERSION
expected_goimports=$EXPECTED_GOIMPORTS_VERSION
expected_govulncheck=$EXPECTED_GOVULNCHECK_VERSION
: "${EXPECTED_SQLC_X_NET_VERSION:?EXPECTED_SQLC_X_NET_VERSION is not set}"
: "${EXPECTED_SQLC_GRPC_VERSION:?EXPECTED_SQLC_GRPC_VERSION is not set}"

[[ $(go version | awk '{print $3}') == "go${expected_go}" ]]
[[ $GOTOOLCHAIN == local ]]
[[ $GOMODCACHE == /cache/go/modules ]]
[[ $GOCACHE == /cache/go/build ]]
command -v gcc >/dev/null

assert_module_version() {
	local command=$1
	local module=$2
	local version=$3
	go version -m "$(command -v "$command")" |
		grep -F $'\tmod\t'"${module}"$'\t'"${version}" >/dev/null
}

assert_module_version \
	sqlc \
	github.com/sqlc-dev/sqlc \
	"$expected_sqlc"
assert_module_version \
	goose \
	github.com/pressly/goose/v3 \
	"$expected_goose"
assert_module_version \
	golangci-lint \
	github.com/golangci/golangci-lint/v2 \
	"$expected_golangci"
assert_module_version \
	goimports \
	golang.org/x/tools \
	"$expected_goimports"
assert_module_version \
	govulncheck \
	golang.org/x/vuln \
	"$expected_govulncheck"

assert_dependency_version() {
	local command=$1
	local module=$2
	local version=$3
	go version -m "$(command -v "$command")" |
		grep -F $'\tdep\t'"${module}"$'\t'"${version}" >/dev/null
}

assert_dependency_version \
	sqlc \
	golang.org/x/net \
	"$EXPECTED_SQLC_X_NET_VERSION"
assert_dependency_version \
	sqlc \
	google.golang.org/grpc \
	"$EXPECTED_SQLC_GRPC_VERSION"
assert_dependency_version \
	goose \
	golang.org/x/crypto \
	"$EXPECTED_GOOSE_X_CRYPTO_VERSION"
assert_dependency_version \
	goose \
	golang.org/x/net \
	"$EXPECTED_GOOSE_X_NET_VERSION"
assert_dependency_version \
	goose \
	google.golang.org/grpc \
	"$EXPECTED_GOOSE_GRPC_VERSION"

smoke_directory=$(mktemp -d /workspace/go-race-smoke.XXXXXX)
trap 'rm -rf "$smoke_directory"' EXIT

cat >"${smoke_directory}/go.mod" <<EOF
module example.invalid/ci-race-smoke

go ${expected_go%.*}
EOF

cat >"${smoke_directory}/counter.go" <<'EOF'
package smoke

func Add(left, right int) int {
	return left + right
}
EOF

cat >"${smoke_directory}/counter_test.go" <<'EOF'
package smoke

import "testing"

func TestAdd(t *testing.T) {
	t.Parallel()
	if got := Add(2, 3); got != 5 {
		t.Fatalf("Add(2, 3) = %d, want 5", got)
	}
}
EOF

(
	cd "$smoke_directory"
	go test -race ./...
)
