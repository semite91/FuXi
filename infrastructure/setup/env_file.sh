#!/usr/bin/env bash
# Shared helpers to read KEY=VALUE env files without executing them.
# Values are taken literally, the same way the backend reads them.

# Prints the value of a key. Prints nothing when the key is missing.
read_env_value() {
  local env_file="$1" key="$2" line
  line="$(grep -E "^${key}=" "${env_file}" | head -n 1 || true)"
  printf '%s' "${line#*=}"
}

# Prints the value of a key, or stops with a message when it is missing or empty.
require_env_value() {
  local env_file="$1" key="$2" value
  value="$(read_env_value "${env_file}" "${key}")"
  if [ -z "${value}" ]; then
    echo "${key} is missing or empty in ${env_file}." >&2
    exit 1
  fi
  printf '%s' "${value}"
}
