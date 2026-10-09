#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 8 ]]; then
	printf 'usage: %s <output-json> <seven-image-records>\n' "$0" >&2
	exit 64
fi

output_file=$1
shift

printf '%s\n' "$@" |
	jq --slurp --exit-status '
		if (
			type == "array" and
			length == 7 and
			([.[].name] | sort) == [
				"base",
				"go",
				"node",
				"playwright",
				"postgres",
				"utils",
				"vite"
			] and
			([
				.[] |
				.image == ("ghcr.io/myflow-xyz/ci-" + .name) and
				(.digest | test("^sha256:[0-9a-f]{64}$")) and
				.ref == (.image + "@" + .digest) and
				(try (
					(.image + ":candidate-") as $candidate_prefix |
					(.candidate | startswith($candidate_prefix)) and
					(
						.candidate |
						ltrimstr($candidate_prefix) |
						test("^[1-9][0-9]*-[1-9][0-9]*$")
					)
				) catch false)
			] | all)
		) then
			.
		else
			error("published image records violate the suite contract")
		end
	' >"$output_file"
