#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

.venv/bin/python -m pytest tests -q
npm --prefix agentcore/cdk test -- --runInBand
npm --prefix agentcore/cdk run build
npm run cdk:synth -- --quiet
