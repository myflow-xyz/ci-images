#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="${repository_root}/manifests/versions.json"

image_reference() {
	local name=$1
	jq -r \
		--arg name "$name" \
		'.upstream_images[$name] | "\(.reference)@\(.digest)"' \
		"$manifest"
}

node_image=$(image_reference node)
pgvector_image=$(image_reference pgvector)

docker buildx build \
	--call=check \
	--file "${repository_root}/images/base/Dockerfile" \
	--build-arg "BASE_IMAGE=${node_image}" \
	"$repository_root"

docker buildx build \
	--call=check \
	--file "${repository_root}/images/go/Dockerfile" \
	--build-arg "BASE_IMAGE=${node_image}" \
	"$repository_root"

for image in node vite playwright; do
	docker buildx build \
		--call=check \
		--file "${repository_root}/images/${image}/Dockerfile" \
		--build-arg "BASE_IMAGE=${node_image}" \
		"$repository_root"
done

docker buildx build \
	--call=check \
	--file "${repository_root}/images/postgres/Dockerfile" \
	--build-arg "PGVECTOR_IMAGE=${pgvector_image}" \
	"$repository_root"
