#!/usr/bin/env bash
set -euo pipefail

# Redacts sensitive values in:
# - KEY=VALUE
# - KEY: VALUE
# - KEY: "VALUE"
# - URLs containing credentials: scheme://user:pass@host
#
# Keeps structure for debugging while removing secrets.

# Regex for keys that are sensitive (case-insensitive)
SENSITIVE_KEYS_RE='(pass(word)?|secret|token|api[_-]?key|client[_-]?secret|private[_-]?key|dsn|bearer|authorization|cookie|session|refresh|access|jwt|signing|kc_db_password|nextauth_secret|openai_api_key|redis_password|postgres_password)'

# Redact function for KEY=VALUE and KEY: VALUE forms
redact_kv() {
  # Uses awk to handle both "=" and ":" separators.
  awk -v IGNORECASE=1 -v re="$SENSITIVE_KEYS_RE" '
  function ltrim(s){ sub(/^[ \t\r\n]+/, "", s); return s }
  function rtrim(s){ sub(/[ \t\r\n]+$/, "", s); return s }
  function trim(s){ return rtrim(ltrim(s)) }

  # redact URL credentials like proto://user:pass@host
  function redact_url(s,   out) {
    out = s
    gsub(/([a-zA-Z][a-zA-Z0-9+.-]*:\/\/)([^\/:@ \t"]+):([^\/@ \t"]+)@/, "\\1<REDACTED>:<REDACTED>@", out)
    return out
  }

  {
    line=$0

    # Always redact embedded URL creds even if key not matched
    line = redact_url(line)

    # Handle KEY=VALUE
    if (match(line, /^[ \t]*[A-Za-z_][A-Za-z0-9_]*=/)) {
      split(line, a, "=")
      key=a[1]
      val=substr(line, length(key)+2)
      key_trim=trim(key)
      if (key_trim ~ re) {
        # preserve quotes style
        if (val ~ /^[ \t]*"/) { sub(/=.*/, "=\"<REDACTED>\"", line) }
        else if (val ~ /^[ \t]*'\''/) { sub(/=.*/, "='\''<REDACTED>'\''", line) }
        else { sub(/=.*/, "=<REDACTED>", line) }
      }
      print line
      next
    }

    # Handle YAML KEY: VALUE (incl. indent)
    if (match(line, /^[ \t]*[A-Za-z_][A-Za-z0-9_]*:[ \t]*/)) {
      split(line, a, ":")
      key=a[1]
      rest=substr(line, length(key)+2)  # includes whitespace after colon
      key_trim=trim(key)
      if (key_trim ~ re) {
        # keep indentation and key, but redact the value
        indent=""
        if (match(key, /^[ \t]+/)) indent=substr(key, RSTART, RLENGTH)
        key_clean=trim(key)

        # preserve quoting if present
        rest_trim=trim(rest)
        if (rest_trim ~ /^"/)      print indent key_clean ": \"<REDACTED>\""
        else if (rest_trim ~ /^'\''/) print indent key_clean ": '\''<REDACTED>'\''"
        else                       print indent key_clean ": <REDACTED>"
        next
      }
      print line
      next
    }

    print line
  }'
}

redact_kv
