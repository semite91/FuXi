#!/usr/bin/env bash
# Installs the .NET SDK and PostgreSQL server, creates local env files if they
# are missing, and creates the database role. Safe to run more than once.
# Run as root on Ubuntu.
set -euo pipefail

readonly DOTNET_PACKAGE="dotnet-sdk-10.0"
readonly POSTGRES_VERSION="16"
readonly POSTGRES_PACKAGE="postgresql-${POSTGRES_VERSION}"
readonly POSTGRES_CLUSTER="main"
readonly DEFAULT_DB_HOST="127.0.0.1"
readonly DEFAULT_DB_PORT="5432"
readonly DEFAULT_DB_USER="fuxi"
readonly DEFAULT_DB_NAME="fuxi"
readonly TEST_DB_SUFFIX="_test"
readonly CORS_ORIGINS_KEY="FUXI_CORS_ORIGINS"
# The Vite dev server and the preview of the build (vite.config.ts APP_PORT).
readonly DEFAULT_CORS_ORIGINS="http://localhost:5173"
readonly API_URL_KEY="VITE_FUXI_API_URL"
# The address that "dotnet run" listens on.
readonly DEFAULT_API_URL="http://localhost:5000"
readonly RAG_URL_KEY="VITE_FUXI_RAG_URL"
# The address of the FastAPI engine.
readonly DEFAULT_RAG_URL="http://localhost:8000"
readonly PASSWORD_BYTES=24
readonly PRIVATE_FILE_UMASK=077
readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# shellcheck source=infrastructure/setup/env_file.sh
. "${REPOSITORY_ROOT}/infrastructure/setup/env_file.sh"

install_packages() {
  if command -v dotnet >/dev/null && [ -d "/usr/lib/postgresql/${POSTGRES_VERSION}" ]; then
    return
  fi
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${DOTNET_PACKAGE}" "${POSTGRES_PACKAGE}"
}

start_postgres() {
  if ! pg_isready -q -h "${DEFAULT_DB_HOST}" -p "${DEFAULT_DB_PORT}"; then
    pg_ctlcluster "${POSTGRES_VERSION}" "${POSTGRES_CLUSTER}" start
  fi
  local attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    pg_isready -q -h "${DEFAULT_DB_HOST}" -p "${DEFAULT_DB_PORT}" && return
    sleep 1
  done
  echo "PostgreSQL did not start." >&2
  exit 1
}

# Writes an env file with local-only values when it does not exist yet.
create_env_file() {
  local env_file="$1" database_name="$2" user="$3" password="$4"
  if [ -f "${env_file}" ]; then
    return
  fi
  (
    umask "${PRIVATE_FILE_UMASK}"
    cat > "${env_file}" <<ENV
FUXI_DB_HOST=${DEFAULT_DB_HOST}
FUXI_DB_PORT=${DEFAULT_DB_PORT}
FUXI_DB_NAME=${database_name}
FUXI_DB_USER=${user}
FUXI_DB_PASSWORD=${password}
${CORS_ORIGINS_KEY}=${DEFAULT_CORS_ORIGINS}
${API_URL_KEY}=${DEFAULT_API_URL}
${RAG_URL_KEY}=${DEFAULT_RAG_URL}
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
ENV
  )
}

# The test env file reuses the role of the development env file.
# Env files from before the API or the frontend existed get the keys they lack.
create_env_files() {
  local env_file="${REPOSITORY_ROOT}/.env" test_env_file="${REPOSITORY_ROOT}/.env.test" user password
  create_env_file "${env_file}" "${DEFAULT_DB_NAME}" "${DEFAULT_DB_USER}" "$(openssl rand -hex "${PASSWORD_BYTES}")"
  user="$(require_env_value "${env_file}" FUXI_DB_USER)"
  password="$(require_env_value "${env_file}" FUXI_DB_PASSWORD)"
  create_env_file "${test_env_file}" "${DEFAULT_DB_NAME}${TEST_DB_SUFFIX}" "${user}" "${password}"
  ensure_env_value "${env_file}" "${CORS_ORIGINS_KEY}" "${DEFAULT_CORS_ORIGINS}"
  ensure_env_value "${test_env_file}" "${CORS_ORIGINS_KEY}" "${DEFAULT_CORS_ORIGINS}"
  local file
  for file in "${env_file}" "${test_env_file}"; do
    ensure_env_value "${file}" "${API_URL_KEY}" "${DEFAULT_API_URL}"
    ensure_env_value "${file}" "${RAG_URL_KEY}" "${DEFAULT_RAG_URL}"
  done
}

# Creates or updates the role and creates the development database.
# Values reach psql through the environment, so no shell parses them again.
create_role_and_database() {
  local env_file="${REPOSITORY_ROOT}/.env"
  FUXI_SETUP_USER="$(require_env_value "${env_file}" FUXI_DB_USER)" \
  FUXI_SETUP_PASSWORD="$(require_env_value "${env_file}" FUXI_DB_PASSWORD)" \
  FUXI_SETUP_DATABASE="$(require_env_value "${env_file}" FUXI_DB_NAME)" \
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<'SQL'
\getenv user FUXI_SETUP_USER
\getenv password FUXI_SETUP_PASSWORD
\getenv database FUXI_SETUP_DATABASE
SELECT format('CREATE ROLE %I LOGIN CREATEDB', :'user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'user') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'user', :'password') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database') \gexec
SQL
}

install_packages
start_postgres
create_env_files
create_role_and_database
echo "Environment is ready."
