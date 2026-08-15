#!/usr/bin/env bash
# --------------------------------------------------------------------------
# Web-only deploy script for Hermes-Agent on Amazon Bedrock AgentCore.
#
# Usage:
#   ./scripts/deploy.sh           # Run base, runtime, and web phases
#   ./scripts/deploy.sh phase1    # CDK base stacks only
#   ./scripts/deploy.sh phase2    # AgentCore Toolkit (build + deploy runtime)
#   ./scripts/deploy.sh phase3    # Web/API stack only
#   ./scripts/deploy.sh cdk-only  # Base + web (skip runtime build)
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
# Phase 2: AgentCore Starter Toolkit
# --------------------------------------------------------------------------
phase2() {
    info "=== Phase 2: AgentCore Runtime (build + deploy) ==="

    # Check toolkit is installed.
    if ! command -v agentcore &>/dev/null; then
        info "Installing @aws/agentcore CLI …"
        npm install -g @aws/agentcore
    fi

    # Ensure aws-targets.json exists (agentcore CDK requires it).
    if [ ! -f "$PROJECT_DIR/agentcore/aws-targets.json" ]; then
        info "Generating agentcore/aws-targets.json from current AWS credentials …"
        _ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        _REGION=$(resolve_region)
        cat > "$PROJECT_DIR/agentcore/aws-targets.json" <<TARGETS
[
  {
    "name": "default",
    "description": "Default deployment target",
    "account": "$_ACCOUNT",
    "region": "$_REGION"
  }
]
TARGETS
        info "Created aws-targets.json (account=$_ACCOUNT, region=$_REGION)"
    fi

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
    rsync -a --delete --exclude='__pycache__' --exclude='Dockerfile' \
        "$PROJECT_DIR/bridge/" "$PROJECT_DIR/app/hermes/bridge/"

    # Build and deploy via agentcore CLI.
    info "Deploying to AgentCore …"
    agentcore deploy --yes --verbose

    # Extract runtime IDs and write back to cdk.json.
    info "Extracting runtime IDs …"
    # Strip ANSI escape sequences (agentcore CLI may emit cursor control codes).
    STATUS_JSON=$(agentcore status --json 2>/dev/null | sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' || echo "{}")
    RUNTIME_ARN=$(echo "$STATUS_JSON" | jq -r '
        .resources[0].identifier //
        .runtimes[0].agentRuntimeArn //
        .runtimes[0].runtimeArn //
        .agentRuntimeArn //
        .runtimeArn //
        empty' 2>/dev/null || echo "")
    # AgentCore qualifiers are endpoint IDs (DEFAULT unless a pinned endpoint is created).
    # Runtime IDs are not valid qualifiers.
    QUALIFIER=$(echo "$STATUS_JSON" | jq -r '
        .runtimes[0].qualifier //
        .qualifier //
        .endpointId //
        "DEFAULT"' 2>/dev/null | sed 's|.*/||' || echo "DEFAULT")

    if [ -n "$RUNTIME_ARN" ]; then
        info "Runtime ARN:  $RUNTIME_ARN"
        info "Qualifier:    $QUALIFIER"

        # Update cdk.json with runtime IDs.
        TMP=$(mktemp)
        jq ".context.agentcore_runtime_arn = \"$RUNTIME_ARN\" | \
            .context.agentcore_qualifier = \"$QUALIFIER\"" \
            cdk.json > "$TMP" && mv "$TMP" cdk.json

        info "cdk.json updated with runtime IDs."
    else
        warn "Could not extract runtime IDs automatically."
        warn "Run 'agentcore status --json' and set agentcore_runtime_arn / agentcore_qualifier in cdk.json manually."
    fi

    info "Phase 2 complete."
}

# --------------------------------------------------------------------------
# Phase 3: CDK web/API stack
# --------------------------------------------------------------------------
phase3() {
    info "=== Phase 3: Web/API Stack ==="

    # Verify runtime IDs are set.
    RUNTIME_ARN=$(jq -r '.context.agentcore_runtime_arn // empty' cdk.json)
    if [ -z "$RUNTIME_ARN" ]; then
        warn "agentcore_runtime_arn not set in cdk.json — Lambda will not be able to invoke AgentCore."
        warn "Run Phase 2 first, or set the values manually."
    fi

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
        phase3
        ;;
    *)
        error "Usage: $0 [all|phase1|phase2|phase3|cdk-only]"
        exit 1
        ;;
esac

info "=== Deploy complete ==="
