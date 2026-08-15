#!/usr/bin/env bash
# Authorized-environment smoke test for the Cognito-protected web BFF.
# Token values are read from environment variables and are never printed.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: WEB_API_URL=... TOKEN_USER_A=... TOKEN_USER_B=... TOKEN_NO_SCOPE=... \
  scripts/verify_web_chat.sh

Required environment variables:
  WEB_API_URL      API Gateway stage URL (the .../prod output)
  TOKEN_USER_A     Access token with the chat/send scope
  TOKEN_USER_B     Access token for a second user with chat/send
  TOKEN_NO_SCOPE   Valid access token without chat/send

The script checks 401/403 behavior and makes two no-buffer SSE requests. It
prints status codes and event counts, never token values or response bodies.
AgentCore deployment and AWS credentials are prerequisites.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

: "${WEB_API_URL:?WEB_API_URL is required}"
: "${TOKEN_USER_A:?TOKEN_USER_A is required}"
: "${TOKEN_USER_B:?TOKEN_USER_B is required}"
: "${TOKEN_NO_SCOPE:?TOKEN_NO_SCOPE is required}"

API_URL="${WEB_API_URL%/}/chat"
MAX_TIME="${WEB_SMOKE_MAX_TIME:-120}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

status_without_token="$(curl --silent --show-error --output /dev/null \
    --write-out '%{http_code}' --max-time "$MAX_TIME" \
    -H 'Content-Type: application/json' \
    --data '{"message":"smoke"}' "$API_URL")"
[[ "$status_without_token" == "401" ]] || {
    echo "expected 401 without a token, got $status_without_token" >&2
    exit 1
}

status_without_scope="$(curl --silent --show-error --output /dev/null \
    --write-out '%{http_code}' --max-time "$MAX_TIME" \
    -H "Authorization: Bearer $TOKEN_NO_SCOPE" \
    -H 'Content-Type: application/json' \
    --data '{"message":"smoke"}' "$API_URL")"
[[ "$status_without_scope" == "403" ]] || {
    echo "expected 403 without chat/send, got $status_without_scope" >&2
    exit 1
}

run_stream_check() {
    local label="$1"
    local token="$2"
    local body_file="$TMP_DIR/$label.body"
    local status
    status="$(curl --silent --show-error --no-buffer --output "$body_file" \
        --write-out '%{http_code}' --max-time "$MAX_TIME" \
        -H "Authorization: Bearer $token" \
        -H 'Accept: text/event-stream' \
        -H 'Content-Type: application/json' \
        --data '{"message":"smoke"}' "$API_URL")"
    [[ "$status" == "200" ]] || {
        echo "$label authenticated request returned $status" >&2
        exit 1
    }
    local deltas
    deltas="$(awk '/^event: message.delta$/ { count++ } END { print count + 0 }' "$body_file")"
    [[ "$deltas" -gt 0 ]] || {
        echo "$label response contained no message.delta events" >&2
        exit 1
    }
    printf '%s: status 200, %s message.delta events\n' "$label" "$deltas"
}

echo "unauthenticated request: status 401"
echo "missing chat/send scope: status 403"
run_stream_check "user-a" "$TOKEN_USER_A"
run_stream_check "user-b" "$TOKEN_USER_B"
