#!/usr/bin/env bash
# --------------------------------------------------------------------------
# Teardown script — destroy web-only resources and any legacy optional stacks.
#
# Usage:
#   ./scripts/teardown.sh              # Interactive (prompt before each step)
#   ./scripts/teardown.sh --force      # Non-interactive, destroy everything
#   ./scripts/teardown.sh --dry-run    # Show what would be destroyed
#
# Destruction order (reverse of deploy):
#   1. CDK stacks (web plus any legacy optional stacks)
#   2. AgentCore runtime and Knowledge Base
#   3. Base CDK stacks (agentcore and security)
#   4. Legacy retained resources (S3, DynamoDB, KMS, secrets)
#
# The Cognito user pool is intentionally preserved.
# --------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

MODE="${1:-interactive}"
PROJECT_NAME="hermes-agentcore"

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
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "${CYAN}[STEP]${NC} $*"; }

DRY_RUN=false
FORCE=false

case "$MODE" in
    --force)   FORCE=true ;;
    --dry-run) DRY_RUN=true ;;
    interactive) ;;
    *)
        error "Usage: $0 [--force|--dry-run]"
        exit 1
        ;;
esac

REGION="${AWS_DEFAULT_REGION}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

confirm() {
    if $FORCE; then return 0; fi
    if $DRY_RUN; then info "(dry-run) Would run: $1"; return 1; fi
    echo -en "${YELLOW}=> $1${NC}\n   Continue? [y/N] "
    read -r answer
    [[ "$answer" =~ ^[Yy] ]]
}

stack_exists() {
    aws cloudformation describe-stacks --stack-name "$1" &>/dev/null 2>&1
}

# --------------------------------------------------------------------------
# Pre-flight: show what will be destroyed
# --------------------------------------------------------------------------

echo ""
echo -e "${RED}========================================${NC}"
echo -e "${RED}  HERMES AGENTCORE — FULL TEARDOWN${NC}"
echo -e "${RED}========================================${NC}"
echo ""
info "Project:  $PROJECT_NAME"
info "Region:   $REGION"
info "Account:  $ACCOUNT"
echo ""

info "CloudFormation stacks to destroy:"
for STACK in \
    "${PROJECT_NAME}-gateway" \
    "${PROJECT_NAME}-web" \
    "${PROJECT_NAME}-token-monitoring" \
    "${PROJECT_NAME}-cron" \
    "${PROJECT_NAME}-router" \
    "${PROJECT_NAME}-runtime" \
    "${PROJECT_NAME}-knowledge-base" \
    "${PROJECT_NAME}-observability" \
    "${PROJECT_NAME}-agentcore" \
    "${PROJECT_NAME}-guardrails" \
    "${PROJECT_NAME}-security" \
    "${PROJECT_NAME}-vpc"; do
    if stack_exists "$STACK"; then
        echo -e "  ${RED}✗${NC} $STACK"
    else
        echo -e "  ${GREEN}✓${NC} $STACK (already gone)"
    fi
done

echo ""
info "Resources preserved by this teardown:"
echo "  - Cognito:  ${PROJECT_NAME}-users"
echo ""
info "Legacy retained resources to delete:"
echo "  - S3:       ${PROJECT_NAME}-user-files-${ACCOUNT}-${REGION}"
echo "  - S3 Vectors: ${PROJECT_NAME}-knowledge-vectors-${ACCOUNT}-${REGION} / hermes-product-support"
echo "  - DynamoDB: ${PROJECT_NAME}-identity"
echo "  - KMS:      alias/${PROJECT_NAME}"
echo ""

if $DRY_RUN; then
    info "Dry run complete. No resources were modified."
    exit 0
fi

if ! $FORCE; then
    echo -en "${RED}This will PERMANENTLY destroy all resources. Type 'destroy' to confirm: ${NC}"
    read -r answer
    if [ "$answer" != "destroy" ]; then
        info "Aborted."
        exit 0
    fi
    echo ""
fi

# --------------------------------------------------------------------------
# Step 1: Destroy legacy ECS gateway stack, if present
# --------------------------------------------------------------------------

step "1/5  Destroying legacy ECS gateway stack …"

if stack_exists "${PROJECT_NAME}-gateway"; then
    $CDK destroy "${PROJECT_NAME}-gateway" --force 2>/dev/null \
        || warn "Legacy gateway stack may have already been deleted."
    info "Legacy gateway stack destroyed."
else
    info "Legacy gateway stack not deployed — skipping."
fi

# --------------------------------------------------------------------------
# Step 2: Destroy Phase 3 CDK stacks
# --------------------------------------------------------------------------

step "2/5  Destroying Phase 3 stacks (web, router, cron, token-monitoring) …"

$CDK destroy \
    "${PROJECT_NAME}-web" \
    "${PROJECT_NAME}-token-monitoring" \
    "${PROJECT_NAME}-cron" \
    "${PROJECT_NAME}-router" \
    --force 2>/dev/null || warn "Some Phase 3 stacks may have already been deleted."

info "Phase 3 stacks destroyed."

# --------------------------------------------------------------------------
# Step 3: Destroy Phase 2 AgentCore runtime
# --------------------------------------------------------------------------

step "3/5  Destroying Phase 2 (AgentCore runtime and Knowledge Base) …"

$CDK destroy "${PROJECT_NAME}-runtime" "${PROJECT_NAME}-knowledge-base" --force 2>/dev/null \
    || warn "The runtime or Knowledge Base stack may already be deleted."

# Clean up ECR repository if it was created by the toolkit.
ECR_REPO=$(aws ecr describe-repositories --query "repositories[?contains(repositoryName, 'hermes')].repositoryName" --output text 2>/dev/null || echo "")
if [ -n "$ECR_REPO" ]; then
    for repo in $ECR_REPO; do
        info "Deleting ECR repository: $repo"
        aws ecr delete-repository --repository-name "$repo" --force 2>/dev/null \
            || warn "Could not delete ECR repo: $repo"
    done
fi

info "Phase 2 resources destroyed."

# --------------------------------------------------------------------------
# Step 4: Destroy Phase 1 CDK stacks
# --------------------------------------------------------------------------

step "4/5  Destroying Phase 1 stacks (observability, agentcore, guardrails, security, vpc) …"

# Destroy in reverse dependency order.
$CDK destroy \
    "${PROJECT_NAME}-observability" \
    "${PROJECT_NAME}-agentcore" \
    "${PROJECT_NAME}-guardrails" \
    "${PROJECT_NAME}-security" \
    "${PROJECT_NAME}-vpc" \
    --force 2>/dev/null || warn "Some Phase 1 stacks may have already been deleted."

info "Phase 1 stacks destroyed."

# --------------------------------------------------------------------------
# Step 4: Clean up retained resources
# --------------------------------------------------------------------------

step "5/5  Cleaning up retained resources (RemovalPolicy.RETAIN) …"

# 4a. S3 bucket — must empty before deletion.
BUCKET="${PROJECT_NAME}-user-files-${ACCOUNT}-${REGION}"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    info "Emptying S3 bucket: $BUCKET (including versions) …"
    aws s3api list-object-versions --bucket "$BUCKET" --output json \
        --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' 2>/dev/null | \
        jq -c 'select(.Objects != null and (.Objects | length) > 0)' | \
    while read -r batch; do
        aws s3api delete-objects --bucket "$BUCKET" --delete "$batch" >/dev/null 2>&1
    done
    # Also delete delete-markers.
    aws s3api list-object-versions --bucket "$BUCKET" --output json \
        --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' 2>/dev/null | \
        jq -c 'select(.Objects != null and (.Objects | length) > 0)' | \
    while read -r batch; do
        aws s3api delete-objects --bucket "$BUCKET" --delete "$batch" >/dev/null 2>&1
    done
    info "Deleting S3 bucket: $BUCKET"
    aws s3 rb "s3://$BUCKET" 2>/dev/null || warn "Could not delete bucket $BUCKET"
else
    info "S3 bucket $BUCKET does not exist."
fi

# 4b. S3 Vectors — delete the index before its vector bucket. These are
# retained by CloudFormation because a non-empty vector bucket cannot be
# deleted by the service during stack deletion.
VECTOR_BUCKET="${PROJECT_NAME}-knowledge-vectors-${ACCOUNT}-${REGION}"
VECTOR_INDEX="hermes-product-support"
if aws s3vectors get-index --vector-bucket-name "$VECTOR_BUCKET" --index-name "$VECTOR_INDEX" >/dev/null 2>&1; then
    info "Deleting S3 Vectors index: $VECTOR_BUCKET/$VECTOR_INDEX"
    aws s3vectors delete-index --vector-bucket-name "$VECTOR_BUCKET" --index-name "$VECTOR_INDEX"
fi
if aws s3vectors get-vector-bucket --vector-bucket-name "$VECTOR_BUCKET" >/dev/null 2>&1; then
    info "Deleting S3 Vectors bucket: $VECTOR_BUCKET"
    aws s3vectors delete-vector-bucket --vector-bucket-name "$VECTOR_BUCKET"
fi

# 4c. DynamoDB table.
TABLE="${PROJECT_NAME}-identity"
if aws dynamodb describe-table --table-name "$TABLE" &>/dev/null 2>&1; then
    info "Deleting DynamoDB table: $TABLE"
    aws dynamodb delete-table --table-name "$TABLE" >/dev/null 2>&1
else
    info "DynamoDB table $TABLE does not exist."
fi

# 4c. KMS key — schedule for deletion (minimum 7-day waiting period).
KMS_ALIAS="alias/${PROJECT_NAME}"
KMS_KEY_ID=$(aws kms describe-key --key-id "$KMS_ALIAS" --query "KeyMetadata.KeyId" --output text 2>/dev/null || echo "")
if [ -n "$KMS_KEY_ID" ] && [ "$KMS_KEY_ID" != "None" ]; then
    info "Scheduling KMS key for deletion (7-day wait): $KMS_KEY_ID"
    aws kms schedule-key-deletion --key-id "$KMS_KEY_ID" --pending-window-in-days 7 2>/dev/null \
        || warn "Could not schedule KMS key deletion."
    aws kms delete-alias --alias-name "$KMS_ALIAS" 2>/dev/null || true
else
    info "KMS key $KMS_ALIAS does not exist."
fi

# 4d. Secrets Manager — force delete (no recovery).
info "Deleting Secrets Manager secrets (hermes/*) …"
SECRETS=$(aws secretsmanager list-secrets --query "SecretList[?starts_with(Name, 'hermes/')].Name" --output text 2>/dev/null || echo "")
if [ -n "$SECRETS" ]; then
    for secret in $SECRETS; do
        info "  Deleting secret: $secret"
        aws secretsmanager delete-secret --secret-id "$secret" --force-delete-without-recovery 2>/dev/null || true
    done
else
    info "  No hermes/* secrets found."
fi

# 4f. CloudWatch log groups.
info "Deleting CloudWatch log groups (/aws/lambda/${PROJECT_NAME}-*) …"
LOG_GROUPS=$(aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/${PROJECT_NAME}-" --query "logGroups[].logGroupName" --output text 2>/dev/null || echo "")
if [ -n "$LOG_GROUPS" ]; then
    for lg in $LOG_GROUPS; do
        info "  Deleting log group: $lg"
        aws logs delete-log-group --log-group-name "$lg" 2>/dev/null || true
    done
else
    info "  No log groups found."
fi

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TEARDOWN COMPLETE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
info "All resources from deploy.sh have been destroyed."
info "Note: KMS key deletion has a 7-day waiting period."
info "Run 'aws cloudformation list-stacks --stack-status-filter DELETE_COMPLETE' to verify."
