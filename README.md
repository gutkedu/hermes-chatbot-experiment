# Hermes product-support chatbot

Authenticated product-support chatbot built with Hermes Agent on Amazon Bedrock AgentCore. The target channel is a web browser, with Amazon Cognito authentication and a backend boundary between the browser and AgentCore.

## Repository status

The current code is a baseline imported from the AWS sample recorded in [`UPSTREAM.md`](UPSTREAM.md). Existing messaging adapters remain for baseline fidelity; they are not the product's target interface. The next increment adds the authenticated web path.

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
./scripts/verify.sh
```

The verifier runs Python tests, the AgentCore TypeScript tests/build, and `cdk synth`. It does not run `cdk deploy` or `agentcore deploy`.

## Design

See [`docs/superpowers/specs/2026-08-15-hermes-agentcore-product-support-design.md`](docs/superpowers/specs/2026-08-15-hermes-agentcore-product-support-design.md).

## Upstream attribution

The imported AWS sample is licensed under MIT-0. See [`UPSTREAM.md`](UPSTREAM.md), [`THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt`](THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt), and the preserved [upstream README](docs/upstream/AWS_SAMPLE_README.md).
