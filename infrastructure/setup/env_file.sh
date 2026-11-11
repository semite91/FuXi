#!/usr/bin/env bash
# Shared helpers to read and complete KEY=VALUE env files without executing them.
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

# Gives a key the value when the key is missing or empty. A key that has a value
# and every other line stay as they are, so running it again changes nothing.
ensure_env_value() {
  local env_file="$1" key="$2" value="$3" line content=""
  if [ -n "$(read_env_value "${env_file}" "${key}")" ]; then
    return
  fi
  if ! grep -q -E "^${key}=" "${env_file}"; then
    append_env_line "${env_file}" "${key}=${value}"
    return
  fi
  while IFS= read -r line || [ -n "${line}" ]; do
    if [ "${line}" = "${key}=" ]; then
      line="${key}=${value}"
    fi
    content+="${line}"$'\n'
  done < "${env_file}"
  printf '%s' "${content}" > "${env_file}"
}

# Adds a line at the end, after ending a last line that has no line break.
append_env_line() {
  local env_file="$1" line="$2"
  if [ -n "$(tail -c 1 "${env_file}")" ]; then
    echo >> "${env_file}"
  fi
  printf '%s\n' "${line}" >> "${env_file}"
}
