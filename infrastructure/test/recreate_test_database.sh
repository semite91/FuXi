#!/usr/bin/env bash
# Drops and recreates the test database named in .env.test.
# It refuses any database whose name does not end with _test.
set -euo pipefail

readonly TEST_DB_SUFFIX="_test"
readonly MAINTENANCE_DATABASE="postgres"
readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly ENV_FILE="${FUXI_ENV_FILE:-${REPOSITORY_ROOT}/.env.test}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck source=infrastructure/setup/env_file.sh
. "${REPOSITORY_ROOT}/infrastructure/setup/env_file.sh"

FUXI_DB_NAME="$(require_env_value "${ENV_FILE}" FUXI_DB_NAME)"

if [[ "${FUXI_DB_NAME}" != *"${TEST_DB_SUFFIX}" ]]; then
  echo "Refused: FUXI_DB_NAME must end with ${TEST_DB_SUFFIX}." >&2
  exit 1
fi

PGHOST="$(require_env_value "${ENV_FILE}" FUXI_DB_HOST)"
PGPORT="$(require_env_value "${ENV_FILE}" FUXI_DB_PORT)"
PGUSER="$(require_env_value "${ENV_FILE}" FUXI_DB_USER)"
PGPASSWORD="$(require_env_value "${ENV_FILE}" FUXI_DB_PASSWORD)"
export PGHOST PGPORT PGUSER PGPASSWORD

psql -v ON_ERROR_STOP=1 -q -d "${MAINTENANCE_DATABASE}" -v database="${FUXI_DB_NAME}" <<'SQL'
SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE)', :'database') \gexec
SELECT format('CREATE DATABASE %I', :'database') \gexec
SQL
echo "Test database ${FUXI_DB_NAME} was recreated."
