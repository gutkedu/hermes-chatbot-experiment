#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

npm ci
npm ci --prefix lambda/web_chat
npm ci --prefix agentcore/cdk
npm run test:bff
npm run test:web
.venv/bin/python -m pytest tests -q
npm --prefix agentcore/cdk test -- --runInBand
npm --prefix agentcore/cdk run build
npm run cdk:synth -- --quiet
