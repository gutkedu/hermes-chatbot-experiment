# Hermes product-support chatbot

Authenticated product-support chatbot built with Hermes Agent on Amazon Bedrock AgentCore. The target channel is a web browser, with Amazon Cognito authentication and a backend boundary between the browser and AgentCore. The first end-to-end web path is documented in [`docs/authenticated-web-chat-runbook.md`](docs/authenticated-web-chat-runbook.md).

## Repository status

The current code is a baseline imported from the AWS sample recorded in [`UPSTREAM.md`](UPSTREAM.md). Existing messaging adapters remain for baseline fidelity; they are not the product's target interface. The next increment adds the authenticated web path.

## Deployment architecture

The default deployment is web-only:

`CloudFront/S3 → API Gateway → Lambda → AgentCore Runtime (PUBLIC) → Bedrock`

The default CDK synthesis contains the Cognito security stack, AgentCore base
role and workspace bucket, the private product Knowledge Base, the explicit
AgentCore runtime, and the authenticated web/API stack. VPC,
NAT Gateway, private endpoints, ECS, Router, Cron, Observability, and Token
Monitoring are not deployed. The latter stacks remain available for a later
rollout through explicit CDK context flags.

Runtime workspace state is persisted in the private, versioned workspace bucket
when configured. The backend derives an opaque `ws-<sha256(runtimeSessionId)>`
namespace from authenticated identity and the runtime validates that binding;
the browser cannot provide it. Restore runs before the first conversation,
periodic/final saves are best-effort, and missing S3 configuration leaves the
runtime explicitly ephemeral. Persisted skills are bounded `skills/<name>/SKILL.md`
Markdown instructions only—Python, shell, binary, and importable plugin files
are ignored and never executed.

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- npm

Docker, AWS CLI, AgentCore CLI, AWS credentials, and Bedrock model access are required only for container builds or deployment. Baseline verification creates no AWS resources and does not require an AWS login.

## Verify the baseline

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
npm ci
npm --prefix agentcore/cdk ci
npm ci --prefix lambda/web_chat
./scripts/verify.sh
```

The verifier runs the BFF and browser contract tests, Python tests, and `cdk
synth`. It does not run `cdk deploy`, ingestion, or the real chat smoke test.
For an authorized AWS smoke test after deployment, see
[`scripts/verify_web_chat.sh`](scripts/verify_web_chat.sh) and the runbook.

## Design

See [`docs/superpowers/specs/2026-08-15-hermes-agentcore-product-support-design.md`](docs/superpowers/specs/2026-08-15-hermes-agentcore-product-support-design.md).

## Upstream attribution

The imported AWS sample is licensed under MIT-0. See [`UPSTREAM.md`](UPSTREAM.md), [`THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt`](THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt), and the preserved [upstream README](docs/upstream/AWS_SAMPLE_README.md).
