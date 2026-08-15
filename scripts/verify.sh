#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

npm ci
npm ci --prefix lambda/web_chat
npm run test:bff
npm run test:web
.venv/bin/python -m pytest tests -q
npm run cdk:synth -- --quiet
