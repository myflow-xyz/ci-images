#!/usr/bin/env bash

set -euo pipefail

expected_go=${EXPECTED_GO_VERSION:?EXPECTED_GO_VERSION is not set}
expected_sqlc=${EXPECTED_SQLC_VERSION:?EXPECTED_SQLC_VERSION is not set}
expected_goose=${EXPECTED_GOOSE_VERSION:?EXPECTED_GOOSE_VERSION is not set}
: "${EXPECTED_GOOSE_GRPC_VERSION:?EXPECTED_GOOSE_GRPC_VERSION is not set}"
: "${EXPECTED_GOOSE_MODERNC_LIBC_VERSION:?EXPECTED_GOOSE_MODERNC_LIBC_VERSION is not set}"
: "${EXPECTED_GOOSE_X_CRYPTO_VERSION:?EXPECTED_GOOSE_X_CRYPTO_VERSION is not set}"
: "${EXPECTED_GOOSE_X_NET_VERSION:?EXPECTED_GOOSE_X_NET_VERSION is not set}"
: "${EXPECTED_GOLANGCI_LINT_VERSION:?EXPECTED_GOLANGCI_LINT_VERSION is not set}"
: "${EXPECTED_GOLANGCI_LINT_X_TEXT_VERSION:?EXPECTED_GOLANGCI_LINT_X_TEXT_VERSION is not set}"
: "${EXPECTED_GOIMPORTS_VERSION:?EXPECTED_GOIMPORTS_VERSION is not set}"
: "${EXPECTED_GOIMPORTS_X_MOD_VERSION:?EXPECTED_GOIMPORTS_X_MOD_VERSION is not set}"
: "${EXPECTED_GOVULNCHECK_VERSION:?EXPECTED_GOVULNCHECK_VERSION is not set}"
: "${EXPECTED_GOVULNCHECK_X_MOD_VERSION:?EXPECTED_GOVULNCHECK_X_MOD_VERSION is not set}"
: "${EXPECTED_HURL_VERSION:?EXPECTED_HURL_VERSION is not set}"
expected_golangci=$EXPECTED_GOLANGCI_LINT_VERSION
expected_goimports=$EXPECTED_GOIMPORTS_VERSION
expected_govulncheck=$EXPECTED_GOVULNCHECK_VERSION
: "${EXPECTED_SQLC_X_NET_VERSION:?EXPECTED_SQLC_X_NET_VERSION is not set}"
: "${EXPECTED_SQLC_GRPC_VERSION:?EXPECTED_SQLC_GRPC_VERSION is not set}"

expected_path=/usr/local/go/bin:/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[[ $(go version | awk '{print $3}') == "go${expected_go}" ]]
[[ $GOBIN == /opt/ci-tools/bin ]]
[[ $GOCACHE == /var/cache/go/build ]]
[[ -z ${GOEXPERIMENT:-} ]]
[[ $GOMODCACHE == /var/cache/go/mod ]]
[[ $GOPATH == /var/lib/go ]]
[[ $GOROOT == /usr/local/go ]]
[[ $GOTMPDIR == /var/tmp/go ]]
[[ $GOTOOLCHAIN == local ]]
[[ $PATH == "$expected_path" ]]
command -v gcc >/dev/null

touch \
	/var/cache/go/build/.write-probe \
	/var/cache/go/mod/.write-probe \
	/var/lib/go/.write-probe \
	/var/tmp/go/.write-probe
rm -f \
	/var/cache/go/build/.write-probe \
	/var/cache/go/mod/.write-probe \
	/var/lib/go/.write-probe \
	/var/tmp/go/.write-probe

for command in \
	goimports \
	golangci-lint \
	goose \
	govulncheck \
	hurl \
	hurlfmt \
	sqlc; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

hurl --version |
	grep --fixed-strings "hurl ${EXPECTED_HURL_VERSION}" >/dev/null
hurlfmt --version |
	grep --fixed-strings "hurlfmt ${EXPECTED_HURL_VERSION}" >/dev/null

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
assert_dependency_version \
	goose \
	modernc.org/libc \
	"$EXPECTED_GOOSE_MODERNC_LIBC_VERSION"
assert_dependency_version \
	golangci-lint \
	golang.org/x/text \
	"$EXPECTED_GOLANGCI_LINT_X_TEXT_VERSION"
assert_dependency_version \
	goimports \
	golang.org/x/mod \
	"$EXPECTED_GOIMPORTS_X_MOD_VERSION"
assert_dependency_version \
	govulncheck \
	golang.org/x/mod \
	"$EXPECTED_GOVULNCHECK_X_MOD_VERSION"

hurl_smoke_directory=$(mktemp -d /var/tmp/hurl-smoke.XXXXXX)
hurl_request="${hurl_smoke_directory}/request.hurl"
hurl_server_pid=
cleanup_hurl_smoke() {
	if [[ -n $hurl_server_pid ]]; then
		kill "$hurl_server_pid" >/dev/null 2>&1 || true
		wait "$hurl_server_pid" 2>/dev/null || true
	fi
	rm -f "${hurl_smoke_directory}/health.json" "$hurl_request"
	rmdir "$hurl_smoke_directory"
}
trap cleanup_hurl_smoke EXIT

printf '{"ok":true}\n' >"${hurl_smoke_directory}/health.json"
printf '%s\n' \
	'GET http://127.0.0.1:18080/health.json' \
	'HTTP 200' \
	'[Asserts]' \
	'header "Content-Type" startsWith "application/json"' \
	'jsonpath "$.ok" == true' \
	>"$hurl_request"

python3 -m http.server \
	18080 \
	--bind 127.0.0.1 \
	--directory "$hurl_smoke_directory" \
	>/dev/null 2>&1 &
hurl_server_pid=$!

hurl_server_ready=false
for _ in {1..50}; do
	if curl --fail --silent http://127.0.0.1:18080/health.json \
		>/dev/null 2>&1; then
		hurl_server_ready=true
		break
	fi
	sleep 0.1
done
$hurl_server_ready
hurl --test "$hurl_request"

cleanup_hurl_smoke
trap - EXIT

smoke_directory=$(mktemp -d "${GOTMPDIR}/go-race-smoke.XXXXXX")
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
