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
readonly VAPID_PUBLIC_KEY_KEY="VAPID_PUBLIC_KEY"
readonly VAPID_PRIVATE_KEY_KEY="VAPID_PRIVATE_KEY"
readonly VAPID_SUBJECT_KEY="VAPID_SUBJECT"
# The VAPID contact that push services may use. Replace it with your own mailto: or https: address.
readonly DEFAULT_VAPID_SUBJECT="mailto:learner@fuxi.local"
readonly BACKEND_PROJECT="backend/fuxi_api"
readonly GENERATE_VAPID_KEYS_COMMAND="generate-vapid-keys"
# RAG engine (Python). Secrets stay empty for the developer to fill.
readonly RAG_PYTHON="python3.13"
readonly RAG_DIRECTORY="rag"
readonly RAG_VENV=".venv"
# Git-ignored folders readable by the developer only: the Google service account key and Letterboxd's watched.csv.
readonly RAG_PRIVATE_DIRECTORIES=("secrets" "data" "data/letterboxd")
readonly PRIVATE_DIRECTORY_MODE=700
readonly RAG_SECRET_KEYS=("RAG_NOTION_TOKEN" "RAG_GEMINI_API_KEY" "RAG_GOOGLE_SERVICE_ACCOUNT_FILE" "RAG_TMDB_TOKEN" "RAG_LETTERBOXD_WATCHED_FILE" "RAG_LIVE_TESTS")
readonly RAG_DEFAULT_SETTINGS=("RAG_GEMINI_MODEL=gemini-3.8-flash" "RAG_TEXT_THRESHOLD=0.5" "RAG_IMAGE_THRESHOLD=0.25" "RAG_BATCH_SIZE=16" "RAG_REBUILD_COOLDOWN_MINUTES=10")
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
VAPID_SUBJECT=
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
  # Build output left by root from an earlier run would stop the key command below.
  give_to_invoking_user "${REPOSITORY_ROOT}/${BACKEND_PROJECT}/bin" "${REPOSITORY_ROOT}/${BACKEND_PROJECT}/obj"
  local file
  for file in "${env_file}" "${test_env_file}"; do
    ensure_env_value "${file}" "${API_URL_KEY}" "${DEFAULT_API_URL}"
    ensure_env_value "${file}" "${RAG_URL_KEY}" "${DEFAULT_RAG_URL}"
    ensure_env_value "${file}" "${VAPID_SUBJECT_KEY}" "${DEFAULT_VAPID_SUBJECT}"
    ensure_vapid_keys "${file}"
    ensure_rag_keys "${file}"
  done
  give_to_invoking_user "${env_file}" "${test_env_file}"
}

# The script runs as root through sudo. Files it creates in the repository must belong to the
# developer who called sudo, or their own later "dotnet build" and "dotnet run" cannot write
# bin/ and obj/ or read the env files. Prints nothing when there is no such developer.
invoking_user() {
  if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    printf '%s' "${SUDO_USER}"
  fi
}

run_as_invoking_user() {
  local user
  user="$(invoking_user)"
  if [ -n "${user}" ]; then
    runuser -u "${user}" -- "$@"
    return
  fi
  "$@"
}

# Gives the paths that exist to the developer who called sudo, with their login group.
give_to_invoking_user() {
  local user path
  user="$(invoking_user)"
  if [ -z "${user}" ]; then
    return
  fi
  for path in "$@"; do
    if [ -e "${path}" ]; then
      chown -R "${user}:" "${path}"
    fi
  done
}

# Generates the VAPID keys once with the backend command and writes them to the env file.
# Keys that exist are never replaced. The private key is kept out of the terminal.
ensure_vapid_keys() {
  local env_file="$1" public_key private_key keys
  public_key="$(read_env_value "${env_file}" "${VAPID_PUBLIC_KEY_KEY}")"
  private_key="$(read_env_value "${env_file}" "${VAPID_PRIVATE_KEY_KEY}")"
  if [ -n "${public_key}" ] && [ -n "${private_key}" ]; then
    return
  fi
  if [ -n "${public_key}" ] || [ -n "${private_key}" ]; then
    echo "Only one VAPID key is filled in ${env_file}. Fill both or empty both." >&2
    exit 1
  fi
  keys="$(run_as_invoking_user dotnet run --verbosity quiet --project "${REPOSITORY_ROOT}/${BACKEND_PROJECT}" -- "${GENERATE_VAPID_KEYS_COMMAND}")"
  public_key="$(grep -E "^${VAPID_PUBLIC_KEY_KEY}=" <<< "${keys}" | head -n 1 | cut -d= -f2-)"
  private_key="$(grep -E "^${VAPID_PRIVATE_KEY_KEY}=" <<< "${keys}" | head -n 1 | cut -d= -f2-)"
  if [ -z "${public_key}" ] || [ -z "${private_key}" ]; then
    echo "The VAPID keys could not be generated." >&2
    exit 1
  fi
  ensure_env_value "${env_file}" "${VAPID_PUBLIC_KEY_KEY}" "${public_key}"
  ensure_env_value "${env_file}" "${VAPID_PRIVATE_KEY_KEY}" "${private_key}"
  echo "VAPID keys were generated for ${env_file}."
}

# Adds the RAG keys: settings get their defaults, secrets are added empty for the developer.
ensure_rag_keys() {
  local env_file="$1" key setting
  for setting in "${RAG_DEFAULT_SETTINGS[@]}"; do
    ensure_env_value "${env_file}" "${setting%%=*}" "${setting#*=}"
  done
  for key in "${RAG_SECRET_KEYS[@]}"; do
    if ! grep -q -E "^${key}=" "${env_file}"; then
      append_env_line "${env_file}" "${key}="
    fi
  done
}

# Creates rag/secrets (Google service account key) and rag/data/letterboxd (watched.csv).
create_rag_private_directories() {
  local directory private_path
  for directory in "${RAG_PRIVATE_DIRECTORIES[@]}"; do
    private_path="${REPOSITORY_ROOT}/${RAG_DIRECTORY}/${directory}"
    mkdir -p "${private_path}"
    chmod "${PRIVATE_DIRECTORY_MODE}" "${private_path}"
    give_to_invoking_user "${private_path}"
  done
}

# Creates rag/.venv and installs the locked Python packages when Python 3.13 exists.
# The packages are large (PyTorch), so this step can take several minutes the first time.
create_rag_environment() {
  local rag_path="${REPOSITORY_ROOT}/${RAG_DIRECTORY}"
  if ! command -v "${RAG_PYTHON}" >/dev/null; then
    RAG_ENVIRONMENT_MISSING="true"
    return
  fi
  give_to_invoking_user "${rag_path}/${RAG_VENV}"
  if [ ! -d "${rag_path}/${RAG_VENV}" ]; then
    run_as_invoking_user "${RAG_PYTHON}" -m venv "${rag_path}/${RAG_VENV}"
  fi
  run_as_invoking_user "${rag_path}/${RAG_VENV}/bin/pip" install --quiet -r "${rag_path}/requirements.txt"
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
create_rag_private_directories
create_rag_environment
if [ "${RAG_ENVIRONMENT_MISSING:-}" = "true" ]; then
  echo "Environment is ready, except the RAG engine: install ${RAG_PYTHON} and run this script again." >&2
else
  echo "Environment is ready."
fi
