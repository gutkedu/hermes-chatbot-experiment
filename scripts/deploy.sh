#!/usr/bin/env bash
# --------------------------------------------------------------------------
# Deploy Hermes direct chat and the authenticated web chat.
#
# Usage:
#   ./scripts/deploy.sh           # Run base, runtime, and web phases
#   ./scripts/deploy.sh phase1    # CDK base stacks only
#   ./scripts/deploy.sh phase2    # CDK-built AgentCore runtime
#   ./scripts/deploy.sh phase3    # Web/API stack only
#   ./scripts/deploy.sh cdk-only  # CDK stacks only (identical to all)
# --------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

PHASE="${1:-all}"
PROJECT_NAME="hermes-agentcore"

# Deployment defaults from the web-only rollout plan. Explicit environment
# values still take precedence for operators using another account/region.
export AWS_PROFILE="${AWS_PROFILE:-gutkedu}"
if [ -z "${AWS_DEFAULT_REGION:-}" ]; then
    export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
fi

# Activate virtual environment if present.
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Use local npx cdk if global cdk is not available.
if command -v cdk &>/dev/null; then
    CDK="cdk"
else
    CDK="npx cdk"
fi

# Colours.
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

resolve_region() {
    local detected_region
    detected_region="${AWS_DEFAULT_REGION:-${AWS_REGION:-}}"
    if [ -z "$detected_region" ]; then
        detected_region="$(aws configure get region 2>/dev/null || true)"
    fi
    printf '%s\n' "${detected_region:-us-east-1}"
}

# --------------------------------------------------------------------------
# Phase 1: CDK web-only base stacks
# --------------------------------------------------------------------------
phase1() {
    info "=== Phase 1: CDK Web-only Base Stacks ==="

    # Ensure CDK is bootstrapped.
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit &>/dev/null; then
        info "Bootstrapping CDK …"
        $CDK bootstrap
    fi

    $CDK deploy \
        "${PROJECT_NAME}-agentcore" \
        "${PROJECT_NAME}-security" \
        --require-approval never

    info "Phase 1 complete."
}

# --------------------------------------------------------------------------
# Phase 2: explicit AgentCore runtime
# --------------------------------------------------------------------------
phase2() {
    info "=== Phase 2: AgentCore Runtime ==="

    # Copy hermes-agent source into the app/hermes/ Docker build context.
    if [ ! -d "$PROJECT_DIR/app/hermes/hermes-agent" ]; then
        if [ ! -d "$HOME/hermes-agent" ]; then
            info "hermes-agent not found at $HOME/hermes-agent — cloning …"
            git clone https://github.com/NousResearch/hermes-agent.git "$HOME/hermes-agent"
        fi
        info "Copying hermes-agent source into app/hermes/ for Docker build …"
        rsync -a --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
            "$HOME/hermes-agent/" "$PROJECT_DIR/app/hermes/hermes-agent/"
    fi

    # Copy bridge/ into app/hermes/ so Dockerfile can access it.
    info "Syncing bridge/ into app/hermes/bridge/ …"
    rsync -a --delete --exclude='__pycache__' --exclude='Dockerfile' --exclude='memory.py' \
        "$PROJECT_DIR/bridge/" "$PROJECT_DIR/app/hermes/bridge/"

    $CDK deploy "${PROJECT_NAME}-runtime" --require-approval never

    info "Phase 2 complete."
}

# --------------------------------------------------------------------------
# Phase 3: CDK web/API stack
# --------------------------------------------------------------------------
phase3() {
    info "=== Phase 3: Web/API Stack ==="

    # Stage the BFF's production dependency tree before CDK packages the
    # Lambda asset. This is intentionally credential-free and deterministic.
    npm ci --omit=dev --prefix "$PROJECT_DIR/lambda/web_chat"

    $CDK deploy "${PROJECT_NAME}-web" --require-approval never

    # Print API and browser URLs without exposing tokens or runtime state.
    WEB_SITE_URL=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-web" \
        --query "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue" \
        --output text 2>/dev/null || echo "")
    WEB_API_URL=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-web" \
        --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
        --output text 2>/dev/null || echo "")
    COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-web" \
        --query "Stacks[0].Outputs[?OutputKey=='CognitoDomain'].OutputValue" \
        --output text 2>/dev/null || echo "")
    USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks \
        --stack-name "${PROJECT_NAME}-web" \
        --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
        --output text 2>/dev/null || echo "")
    [ -n "$WEB_SITE_URL" ] && info "Web chat site: $WEB_SITE_URL"
    [ -n "$WEB_API_URL" ] && info "Web chat API: $WEB_API_URL"
    [ -n "$COGNITO_DOMAIN" ] && info "Cognito domain: $COGNITO_DOMAIN"
    [ -n "$USER_POOL_CLIENT_ID" ] && info "Web client ID: $USER_POOL_CLIENT_ID"

    info "Phase 3 complete."
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
case "$PHASE" in
    all)
        phase1
        phase2
        phase3
        ;;
    phase1)
        phase1
        ;;
    phase2)
        phase2
        ;;
    phase3)
        phase3
        ;;
    cdk-only)
        phase1
        phase2
        phase3
        ;;
    *)
        error "Usage: $0 [all|phase1|phase2|phase3|cdk-only]"
        exit 1
        ;;
esac

info "=== Deploy complete ==="
