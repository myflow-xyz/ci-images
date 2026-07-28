#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
next_version="${repository_root}/.github/scripts/next-version.sh"
promote_images="${repository_root}/.github/scripts/promote-images.sh"
release_images="${repository_root}/.github/scripts/release-images.sh"

fail() {
	printf 'release verification failed: %s\n' "$*" >&2
	exit 1
}

assert_equal() {
	local expected=$1
	local actual=$2
	local label=$3

	[[ $actual == "$expected" ]] ||
		fail "${label}: expected ${expected}, got ${actual}"
}

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

version_repository="${temporary_directory}/versions"
mkdir -p "$version_repository"
git -C "$version_repository" init --quiet
git -C "$version_repository" \
	-c user.name=ci-images-test \
	-c user.email=ci-images-test@example.invalid \
	commit --allow-empty --quiet -m initial

calculate_version() {
	local bump=$1

	(
		cd "$version_repository"
		"$next_version" "$bump"
	)
}

assert_equal v0.0.1 "$(calculate_version patch)" 'initial patch'
assert_equal v0.1.0 "$(calculate_version minor)" 'initial minor'
assert_equal v1.0.0 "$(calculate_version major)" 'initial major'

git -C "$version_repository" tag v1.2.3
git -C "$version_repository" tag v1.10.0
git -C "$version_repository" tag v9.0.0-rc.1
git -C "$version_repository" tag v01.0.0

assert_equal v1.10.1 "$(calculate_version patch)" 'stable patch'
assert_equal v1.11.0 "$(calculate_version minor)" 'stable minor'
assert_equal v2.0.0 "$(calculate_version major)" 'stable major'

if calculate_version unsupported >/dev/null 2>&1; then
	fail 'unsupported version bump was accepted'
else
	version_status=$?
fi
assert_equal 64 "$version_status" 'unsupported bump status'

fake_bin="${temporary_directory}/bin"
fake_state="${temporary_directory}/registry-state"
fake_log="${temporary_directory}/docker-log"
mkdir -p "$fake_bin"
: >"$fake_state"
: >"$fake_log"

cat >"${fake_bin}/docker" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

state=${FAKE_DOCKER_STATE:?}
log=${FAKE_DOCKER_LOG:?}

digest_for_name() {
	local name=$1
	local suffix

	case "$name" in
	base) suffix=1 ;;
	go) suffix=2 ;;
	node) suffix=3 ;;
	playwright) suffix=4 ;;
	postgres) suffix=5 ;;
	vite) suffix=6 ;;
	*) exit 1 ;;
	esac
	printf 'sha256:%064d\n' "$suffix"
}

if [[ ${1-} == buildx && ${2-} == imagetools &&
	${3-} == inspect ]]; then
	reference=${4:?}
	state_digest=$(
		awk -F '\t' -v reference="$reference" '
			$1 == reference { digest = $2 }
			END { print digest }
		' "$state"
	)
	if [[ -n $state_digest ]]; then
		printf '%s\n' "$state_digest"
		exit 0
	fi

	image=${reference%:*}
	name=${image##*/}
	name=${name#ci-}
	tag=${reference##*:}
	digest=$(digest_for_name "$name")

	if [[ $tag == candidate-* || $tag == sha-* || $tag == latest ]]; then
		if [[ $tag == latest &&
			${FAKE_LATEST_MISMATCH_IMAGE:-} == "$name" ]]; then
			printf 'sha256:%064d\n' 9
		else
			printf '%s\n' "$digest"
		fi
		exit 0
	fi

	if [[ $tag == v* ]]; then
		if [[ ${FAKE_VERSION_ERROR_IMAGE:-} == "$name" ]]; then
			printf 'unauthorized\n' >&2
			exit 1
		fi
		if [[ ${FAKE_VERSION_CONFLICT_IMAGE:-} == "$name" ]]; then
			printf 'sha256:%064d\n' 9
			exit 0
		fi
		if [[ ${FAKE_EXISTING_VERSION_IMAGE:-} == "$name" ]]; then
			printf '%s\n' "$digest"
			exit 0
		fi
		printf 'manifest unknown\n' >&2
		exit 1
	fi
fi

if [[ ${1-} == buildx && ${2-} == imagetools &&
	${3-} == create && ${4-} == --tag ]]; then
	shift 3
	declare -a targets
	source=
	while (($# > 0)); do
		case "$1" in
		--tag)
			targets+=("${2:?}")
			shift 2
			;;
		*)
			source=$1
			shift
			;;
		esac
	done
	[[ -n $source && ${#targets[@]} -gt 0 ]]
	digest=${source##*@}
	for target in "${targets[@]}"; do
		printf '%s\t%s\n' "$target" "$digest" >>"$state"
		printf '%s\n' "$target" >>"$log"
	done
	exit 0
fi

printf 'unsupported fake docker invocation\n' >&2
exit 1
EOF
chmod 0755 "${fake_bin}/docker"

export PATH="${fake_bin}:${PATH}"
export FAKE_DOCKER_LOG="$fake_log"
export FAKE_DOCKER_STATE="$fake_state"
export GITHUB_SHA=1111111111111111111111111111111111111111

output_file="${temporary_directory}/released-images.json"
failure_output="${temporary_directory}/failure-output"

reset_registry() {
	: >"$fake_state"
	: >"$fake_log"
	rm -f "$output_file" "$failure_output"
}

create_count() {
	wc -l <"$fake_log" | tr -d ' '
}

assert_release_output() {
	jq --exit-status \
		--arg revision "$GITHUB_SHA" \
		--arg version v0.1.0 \
		'
			length == 6 and
			([.[].name] | sort) == [
				"base",
				"go",
				"node",
				"playwright",
				"postgres",
				"vite"
			] and
			([
				.[] |
				.version == $version and
				(.digest | test("^sha256:[0-9a-f]{64}$")) and
				.revision_ref ==
					(.image + ":sha-" + $revision) and
				.release_ref == (.image + ":" + $version) and
				(has("needs_promotion") | not)
			] | all)
		' \
		"$output_file" >/dev/null ||
		fail 'release output contract'
}

reset_registry
"$release_images" v0.1.0 "$output_file"
assert_equal 6 "$(create_count)" 'new release promotions'
assert_release_output

: >"$fake_log"
"$release_images" v0.1.0 "$output_file"
assert_equal 0 "$(create_count)" 'idempotent release promotions'
assert_release_output

reset_registry
if FAKE_LATEST_MISMATCH_IMAGE=go \
	"$release_images" v0.1.0 "$output_file" \
	>"$failure_output" 2>&1; then
	fail 'latest mismatch was accepted'
fi
grep -q 'latest does not identify the selected revision' "$failure_output" ||
	fail 'latest mismatch diagnostic'
assert_equal 0 "$(create_count)" 'latest mismatch promotions'

reset_registry
if FAKE_VERSION_CONFLICT_IMAGE=base \
	"$release_images" v0.1.0 "$output_file" \
	>"$failure_output" 2>&1; then
	fail 'conflicting stable tag was accepted'
fi
grep -q 'stable tag already identifies another digest' "$failure_output" ||
	fail 'stable tag conflict diagnostic'
assert_equal 0 "$(create_count)" 'stable tag conflict promotions'

reset_registry
if FAKE_VERSION_ERROR_IMAGE=base \
	"$release_images" v0.1.0 "$output_file" \
	>"$failure_output" 2>&1; then
	fail 'registry inspection error was treated as a missing tag'
fi
grep -q 'unable to determine whether release tag exists' "$failure_output" ||
	fail 'registry inspection diagnostic'
assert_equal 0 "$(create_count)" 'registry inspection error promotions'

reset_registry
base_digest=$(docker buildx imagetools inspect \
	ghcr.io/myflow-xyz/ci-base:latest \
	--format '{{.Manifest.Digest}}')
printf '%s\t%s\n' \
	ghcr.io/myflow-xyz/ci-base:v0.1.0 \
	"$base_digest" \
	>"$fake_state"
"$release_images" v0.1.0 "$output_file"
assert_equal 5 "$(create_count)" 'partial release retry promotions'
assert_release_output

published_images="${temporary_directory}/published-images.json"
jq '
	[
		.[] |
		{
			name,
			image,
			digest,
			ref: (.image + "@" + .digest)
		}
	]
' "$output_file" >"$published_images"

reset_registry
GITHUB_EVENT_NAME=workflow_dispatch \
	GITHUB_REF_NAME=main \
	GITHUB_REF_TYPE=branch \
	GITHUB_RUN_ATTEMPT=1 \
	GITHUB_RUN_ID=123 \
	"$promote_images" "$published_images"
assert_equal 6 \
	"$(grep -c ':run-123$' "$fake_log")" \
	'manual publication aliases'
if grep -Eq ':(edge|latest|v[0-9])' "$fake_log"; then
	fail 'manual publication created a moving or stable alias'
fi

reset_registry
GITHUB_EVENT_NAME=push \
	GITHUB_REF_NAME=main \
	GITHUB_REF_TYPE=branch \
	GITHUB_RUN_ATTEMPT=1 \
	GITHUB_RUN_ID=124 \
	"$promote_images" "$published_images"
assert_equal 6 \
	"$(grep -c ':latest$' "$fake_log")" \
	'main publication aliases'

reset_registry
if GITHUB_EVENT_NAME=push \
	GITHUB_REF_NAME=v0.1.0 \
	GITHUB_REF_TYPE=tag \
	GITHUB_RUN_ATTEMPT=1 \
	GITHUB_RUN_ID=125 \
	"$promote_images" "$published_images" \
	>"$failure_output" 2>&1; then
	fail 'tag publication was accepted'
fi
grep -q 'no promotion policy' "$failure_output" ||
	fail 'tag publication diagnostic'
assert_equal 0 "$(create_count)" 'tag publication promotions'

printf 'release verification passed\n'
