#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
	printf 'usage: %s <patch|minor|major>\n' "$0" >&2
	exit 64
fi

bump=$1
case "$bump" in
patch | minor | major) ;;
*)
	printf 'unsupported version bump: %s\n' "$bump" >&2
	exit 64
	;;
esac

git rev-parse --git-dir >/dev/null
tags=$(git tag --list 'v*' --sort=-version:refname)
current_version=v0.0.0

while IFS= read -r tag; do
	if [[ $tag =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
		current_version=$tag
		break
	fi
done <<<"$tags"

[[ $current_version =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]
major=$((10#${BASH_REMATCH[1]}))
minor=$((10#${BASH_REMATCH[2]}))
patch=$((10#${BASH_REMATCH[3]}))

case "$bump" in
patch)
	patch=$((patch + 1))
	;;
minor)
	minor=$((minor + 1))
	patch=0
	;;
major)
	major=$((major + 1))
	minor=0
	patch=0
	;;
esac

printf 'v%d.%d.%d\n' "$major" "$minor" "$patch"
