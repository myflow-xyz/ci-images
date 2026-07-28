#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="${repository_root}/manifests/versions.json"
image=${1:-ci-postgres:test}
container_name="ci-postgres-smoke-$$"
database=ci_smoke
database_user=ci_smoke
database_password=ci-smoke-password

cleanup() {
	docker rm --force "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run \
	--detach \
	--name "$container_name" \
	--env "POSTGRES_DB=${database}" \
	--env "POSTGRES_PASSWORD=${database_password}" \
	--env "POSTGRES_USER=${database_user}" \
	"$image" \
	>/dev/null

for _ in $(seq 1 60); do
	health=$(
		docker inspect \
			--format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' \
			"$container_name"
	)
	if [[ $health == healthy ]]; then
		break
	fi
	if [[ $health == unhealthy ]]; then
		docker logs "$container_name" >&2
		exit 1
	fi
	sleep 1
done

[[ ${health:-} == healthy ]]

expected_postgres=$(jq -r '.tools.postgres.postgres' "$manifest")
expected_pgvector=$(jq -r '.tools.postgres.pgvector' "$manifest")
expected_gosu=$(jq -r '.tools.postgres.gosu.version' "$manifest")
expected_go=$(jq -r '.tools.go.runtime' "$manifest")

[[ $(docker exec "$container_name" gosu --version | awk '{print $1}') == "$expected_gosu" ]]
[[ $(docker exec "$container_name" sh -c 'command -v gosu') == /opt/ci-tools/bin/gosu ]]
[[ $(docker exec "$container_name" printenv PATH) == /opt/ci-tools/bin:* ]]
[[ $(docker exec "$container_name" sh -c 'command -v postgres') == "/usr/lib/postgresql/${expected_postgres}/bin/postgres" ]]
docker exec "$container_name" \
	grep \
	--binary-files=text \
	--fixed-strings \
	"go${expected_go}" \
	/opt/ci-tools/bin/gosu \
	>/dev/null

actual_postgres=$(
	docker exec "$container_name" postgres --version |
		awk '{print $3}' |
		cut -d. -f1
)
[[ $actual_postgres == "$expected_postgres" ]]

docker exec "$container_name" \
	psql \
	--dbname "$database" \
	--set ON_ERROR_STOP=1 \
	--username "$database_user" \
	--command 'CREATE EXTENSION vector;' \
	--command 'CREATE EXTENSION pgcrypto;' \
	--command \
	"CREATE TABLE smoke_vectors (id uuid DEFAULT gen_random_uuid(), embedding vector(3));" \
	--command \
	"INSERT INTO smoke_vectors (embedding) VALUES ('[1,2,3]');" \
	--command \
	"SELECT embedding <-> '[1,2,4]'::vector FROM smoke_vectors;" \
	>/dev/null

actual_pgvector=$(
	docker exec "$container_name" \
		psql \
		--tuples-only \
		--no-align \
		--dbname "$database" \
		--username "$database_user" \
		--command \
		"SELECT extversion FROM pg_extension WHERE extname = 'vector';"
)
[[ $actual_pgvector == "$expected_pgvector" ]]

docker exec "$container_name" \
	pg_dump \
	--dbname "$database" \
	--format custom \
	--file /tmp/ci-smoke.dump \
	--username "$database_user"
docker exec "$container_name" \
	createdb \
	--owner "$database_user" \
	--username "$database_user" \
	ci_smoke_restore
docker exec "$container_name" \
	pg_restore \
	--dbname ci_smoke_restore \
	--exit-on-error \
	--username "$database_user" \
	/tmp/ci-smoke.dump

restored_rows=$(
	docker exec "$container_name" \
		psql \
		--tuples-only \
		--no-align \
		--dbname ci_smoke_restore \
		--username "$database_user" \
		--command 'SELECT count(*) FROM smoke_vectors;'
)
[[ $restored_rows == 1 ]]
