#!/usr/bin/env bash
# Start and observe a deliberate Bedrock Knowledge Base ingestion job.
set -euo pipefail

project_name="${PROJECT_NAME:-hermes-agentcore}"
region="${AWS_DEFAULT_REGION:-${AWS_REGION:-us-east-1}}"
export AWS_PROFILE="${AWS_PROFILE:-gutkedu}"
export AWS_DEFAULT_REGION="$region"

output() {
  aws cloudformation describe-stacks --stack-name "${project_name}-knowledge-base" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

knowledge_base_id="$(output KnowledgeBaseId)"
data_source_id="$(output DataSourceId)"
if [[ -z "$knowledge_base_id" || "$knowledge_base_id" == "None" || -z "$data_source_id" || "$data_source_id" == "None" ]]; then
  echo "Knowledge Base outputs were not found for ${project_name}-knowledge-base." >&2
  exit 1
fi

job_id="$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$knowledge_base_id" --data-source-id "$data_source_id" --query 'ingestionJob.ingestionJobId' --output text)"
echo "Started ingestion job ${job_id}."

while :; do
  status="$(aws bedrock-agent get-ingestion-job --knowledge-base-id "$knowledge_base_id" --data-source-id "$data_source_id" --ingestion-job-id "$job_id" --query 'ingestionJob.status' --output text)"
  case "$status" in
    COMPLETE)
      echo "Ingestion completed."
      exit 0
      ;;
    FAILED|STOPPED)
      echo "Ingestion ${status,,}. Inspect the safe failure reasons in the Bedrock console or run:" >&2
      echo "aws bedrock-agent get-ingestion-job --knowledge-base-id '$knowledge_base_id' --data-source-id '$data_source_id' --ingestion-job-id '$job_id'" >&2
      exit 1
      ;;
    *)
      echo "Ingestion status: $status"
      sleep 10
      ;;
  esac
done
