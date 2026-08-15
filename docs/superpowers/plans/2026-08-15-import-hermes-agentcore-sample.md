# Import Hermes AgentCore Sample Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the complete AWS Hermes AgentCore sample at revision `b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce` as a traceable, reproducible baseline that can be tested and synthesized locally without deploying AWS resources.

**Architecture:** Preserve the upstream application, bridge, gateways, Lambda handlers, CDK stacks, scripts, tests, and documentation as the baseline. Keep this repository's MIT license at the root, preserve the upstream MIT-0 license under `THIRD_PARTY_LICENSES`, and record every intentional import exception in `UPSTREAM.md`. Add repository-level dependency locks and a single verification entrypoint without changing the runtime behavior.

**Tech Stack:** Python 3.10+, pytest, AWS CDK v2, Node.js 18+, npm, TypeScript, Jest, Docker metadata, Bash

---

## File structure

- `UPSTREAM.md`: immutable provenance, revision, import date, and intentional path mappings.
- `THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt`: exact upstream license text.
- `README.md`: project purpose, browser target, baseline status, setup, and verification.
- `app.py`, `cdk.json`, `stacks/`: Python CDK application imported from upstream.
- `app/hermes/`, `bridge/`, `gateway/`: AgentCore runtime, bridge, and optional Phase 4 gateway.
- `lambda/`, `scripts/`, `agentcore/`: Lambda handlers, deployment helpers, and AgentCore CDK assets.
- `docs/upstream/`: upstream documentation, including the original upstream README.
- `tests/`: upstream Python tests plus repository-baseline contract tests.
- `requirements.in`, `requirements-dev.in`, `requirements.lock`: declared and fully resolved Python dependency sets.
- `package.json`, `package-lock.json`: root CDK CLI dependency and reproducible npm resolution.
- `agentcore/cdk/package.json`, `agentcore/cdk/package-lock.json`: AgentCore TypeScript CDK dependencies and lock.
- `scripts/verify.sh`: no-deploy verification entrypoint.

### Task 1: Establish a failing repository baseline contract

**Files:**
- Create: `tests/test_repository_baseline.py`

- [ ] **Step 1: Write the failing provenance and completeness tests**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REVISION = "b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce"


def test_upstream_provenance_is_recorded() -> None:
    provenance = (ROOT / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore" in provenance
    assert UPSTREAM_REVISION in provenance
    assert "2026-08-15" in provenance


def test_upstream_license_is_preserved() -> None:
    license_text = (
        ROOT / "THIRD_PARTY_LICENSES" / "aws-sample-MIT-0.txt"
    ).read_text(encoding="utf-8")
    assert "MIT No Attribution" in license_text
    assert "Copyright Amazon.com, Inc. or its affiliates." in license_text


def test_complete_sample_areas_are_present() -> None:
    required_paths = (
        "agentcore/agentcore.json",
        "agentcore/cdk/lib/cdk-stack.ts",
        "app/hermes/main.py",
        "bridge/contract.py",
        "gateway/main.py",
        "lambda/router/index.py",
        "scripts/deploy.sh",
        "stacks/vpc_stack.py",
        "docs/upstream/AWS_SAMPLE_README.md",
    )
    missing = [path for path in required_paths if not (ROOT / path).exists()]
    assert missing == []
```

- [ ] **Step 2: Run the contract to verify it fails**

Run: `python3 -m pytest tests/test_repository_baseline.py -v`

Expected: FAIL because `UPSTREAM.md`, the third-party license, and imported sample paths do not exist.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_repository_baseline.py
git commit -m "test: define imported sample baseline"
```

### Task 2: Import the fixed upstream snapshot with provenance

**Files:**
- Create: `.claude/settings.json`
- Create: `.gitignore`
- Create: `CODE_OF_CONDUCT.md`
- Create: `CONTRIBUTING.md`
- Create: `UPSTREAM.md`
- Create: `THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt`
- Create: `agentcore/**`
- Create: `app.py`
- Create: `app/hermes/**`
- Create: `bridge/**`
- Create: `cdk.json`
- Create: `docs/upstream/**`
- Create: `gateway/**`
- Create: `lambda/**`
- Create: `package.json`
- Create: `requirements.in`
- Create: `scripts/**`
- Create: `stacks/**`
- Modify: `README.md`
- Preserve: `LICENSE`
- Preserve: `docs/superpowers/**`

- [ ] **Step 1: Materialize the exact upstream tree in a temporary directory**

```bash
IMPORT_DIR="$(mktemp -d)"
git clone --filter=blob:none \
  https://github.com/aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore.git \
  "$IMPORT_DIR/upstream"
git -C "$IMPORT_DIR/upstream" checkout b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce
test "$(git -C "$IMPORT_DIR/upstream" rev-parse HEAD)" = \
  "b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce"
```

Expected: the final `test` exits with status 0.

- [ ] **Step 2: Copy every tracked upstream path while mapping repository-owned files**

```bash
git -C "$IMPORT_DIR/upstream" ls-files -z \
  | while IFS= read -r -d '' path; do
      case "$path" in
        LICENSE)
          mkdir -p THIRD_PARTY_LICENSES
          cp "$IMPORT_DIR/upstream/$path" THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt
          ;;
        README.md)
          mkdir -p docs/upstream
          cp "$IMPORT_DIR/upstream/$path" docs/upstream/AWS_SAMPLE_README.md
          ;;
        README_ZH.md|docs/*)
          mkdir -p "docs/upstream/$(dirname "${path#docs/}")"
          cp "$IMPORT_DIR/upstream/$path" "docs/upstream/${path#docs/}"
          ;;
        tests/*)
          cp "$IMPORT_DIR/upstream/$path" "$path"
          ;;
        *)
          mkdir -p "$(dirname "$path")"
          cp "$IMPORT_DIR/upstream/$path" "$path"
          ;;
      esac
    done
```

Expected: all upstream tracked paths are copied, with the root license and README mapped to repository-owned locations. The pre-existing `tests/test_repository_baseline.py` and `docs/superpowers/` files remain intact.

- [ ] **Step 3: Add explicit provenance**

Create `UPSTREAM.md`:

````markdown
# Upstream baseline

This repository was bootstrapped from
[`aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore`](https://github.com/aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore).

- Upstream revision: `b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce`
- Upstream branch at selection time: `main`
- Import date: `2026-08-15`
- Import strategy: tracked-file snapshot; this repository does not pull upstream code at build time

## Intentional path mappings

- Upstream `LICENSE` is preserved as `THIRD_PARTY_LICENSES/aws-sample-MIT-0.txt`; the root `LICENSE` remains this project's MIT license.
- Upstream `README.md` is preserved as `docs/upstream/AWS_SAMPLE_README.md`; the root `README.md` describes this product.
- Upstream `README_ZH.md` and `docs/*` are preserved under `docs/upstream/`.

Future upstream updates must record the old and new revisions and review local adaptations before copying files.
````

- [ ] **Step 4: Run the baseline contract**

Run: `python3 -m pytest tests/test_repository_baseline.py -v`

Expected: 3 tests PASS.

- [ ] **Step 5: Review the imported agent settings and secret patterns**

Run:

```bash
git diff -- .claude/settings.json .gitignore
git grep -n -E '(AKIA[0-9A-Z]{16}|gh[opsu]_[A-Za-z0-9]{20,}|-----BEGIN (RSA |EC )?PRIVATE KEY-----)' -- . \
  ':!docs/superpowers/plans/2026-08-15-import-hermes-agentcore-sample.md'
```

Expected: the settings diff contains only upstream command permissions; the secret scan prints no matches.

- [ ] **Step 6: Commit the snapshot and provenance**

```bash
git add . ':!requirements.txt'
git commit -m "chore: import AWS Hermes AgentCore sample"
```

### Task 3: Make Python and Node dependency resolution reproducible

**Files:**
- Modify: `.gitignore`
- Modify: `package.json`
- Create: `package-lock.json`
- Create: `agentcore/cdk/package-lock.json`
- Create: `requirements.in`
- Create: `requirements-dev.in`
- Create: `requirements.lock`
- Test: `tests/test_repository_baseline.py`

- [ ] **Step 1: Extend the baseline contract with dependency-lock assertions**

Append to `tests/test_repository_baseline.py`:

```python
def test_dependency_locks_are_committed() -> None:
    required_locks = (
        "requirements.lock",
        "package-lock.json",
        "agentcore/cdk/package-lock.json",
    )
    missing = [path for path in required_locks if not (ROOT / path).is_file()]
    assert missing == []


def test_lockfiles_are_not_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "package-lock.json" not in gitignore
    assert "agentcore/cdk/package-lock.json" not in gitignore
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python3 -m pytest tests/test_repository_baseline.py -v`

Expected: the three original tests PASS and the two new tests FAIL because lockfiles are missing and ignored.

- [ ] **Step 3: Replace the loose Python requirements with input files**

Create `requirements.in`:

```text
aws-cdk-lib>=2.150.0,<3
constructs>=10.0.0,<11
boto3>=1.35.0
botocore>=1.35.0
litellm>=1.40.0
```

Create `requirements-dev.in`:

```text
-r requirements.in
pytest==8.4.2
```

Remove the imported `requirements.txt`; `requirements.lock` becomes the installable, resolved environment.

- [ ] **Step 4: Allow lockfiles and correct root package metadata**

Remove these two lines from `.gitignore`:

```text
package-lock.json
agentcore/cdk/package-lock.json
```

Replace the root `package.json` scripts and identity fields while retaining its CDK dependency:

```json
{
  "name": "hermes-chatbot-experiment",
  "version": "0.1.0",
  "private": true,
  "description": "Authenticated product-support chatbot built with Hermes Agent and Amazon Bedrock AgentCore",
  "scripts": {
    "cdk:synth": "cdk synth --app 'python3 app.py'"
  },
  "license": "MIT",
  "dependencies": {
    "aws-cdk": "2.1118.0"
  }
}
```

- [ ] **Step 5: Generate and commit deterministic locks**

Run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip pip-tools==7.5.0
.venv/bin/pip-compile --generate-hashes --output-file=requirements.lock requirements-dev.in
npm install --package-lock-only
npm --prefix agentcore/cdk install --package-lock-only
```

Expected: `requirements.lock`, `package-lock.json`, and `agentcore/cdk/package-lock.json` are created without dependency-resolution errors.

- [ ] **Step 6: Run the baseline contract**

Run: `.venv/bin/python -m pytest tests/test_repository_baseline.py -v`

Expected: 5 tests PASS.

- [ ] **Step 7: Commit dependency reproducibility**

```bash
git add .gitignore package.json package-lock.json agentcore/cdk/package-lock.json \
  requirements.in requirements-dev.in requirements.lock tests/test_repository_baseline.py
git commit -m "build: lock baseline dependencies"
```

### Task 4: Document the browser-targeted baseline and add one verification command

**Files:**
- Modify: `README.md`
- Create: `scripts/verify.sh`
- Test: `tests/test_repository_baseline.py`

- [ ] **Step 1: Add failing documentation and verifier assertions**

Append to `tests/test_repository_baseline.py`:

```python
def test_readme_declares_product_direction_and_baseline_status() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "web browser" in readme
    assert "amazon cognito" in readme
    assert "baseline" in readme
    assert "no aws resources" in readme


def test_verification_entrypoint_exists_and_is_executable() -> None:
    verifier = ROOT / "scripts" / "verify.sh"
    assert verifier.is_file()
    assert verifier.stat().st_mode & 0o111
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_repository_baseline.py -v`

Expected: 5 tests PASS and the two new tests FAIL.

- [ ] **Step 3: Replace the root README with product and baseline instructions**

Write `README.md` with these exact sections and facts:

````markdown
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
````

- [ ] **Step 4: Add the no-deploy verifier**

Create executable `scripts/verify.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

.venv/bin/python -m pytest tests -q
npm --prefix agentcore/cdk test -- --runInBand
npm --prefix agentcore/cdk run build
npm run cdk:synth -- --quiet
```

Run: `chmod +x scripts/verify.sh`

- [ ] **Step 5: Run the repository-baseline tests**

Run: `.venv/bin/python -m pytest tests/test_repository_baseline.py -v`

Expected: 7 tests PASS.

- [ ] **Step 6: Commit documentation and verification**

```bash
git add README.md scripts/verify.sh tests/test_repository_baseline.py
git commit -m "docs: describe and verify imported baseline"
```

### Task 5: Verify the complete no-deploy baseline

**Files:**
- Modify only if verification exposes an import or dependency defect.

- [ ] **Step 1: Install only from committed locks**

Run:

```bash
.venv/bin/python -m pip install --require-hashes -r requirements.lock
npm ci
npm --prefix agentcore/cdk ci
```

Expected: all three commands complete successfully without changing a lockfile.

- [ ] **Step 2: Run the complete verifier**

Run: `./scripts/verify.sh`

Expected: all Python tests PASS, AgentCore Jest tests PASS, TypeScript compilation succeeds, and every Python CDK stack synthesizes into `cdk.out/`. No deploy command is executed.

- [ ] **Step 3: Confirm generated files and credentials are not tracked**

Run:

```bash
git status --short
git ls-files | grep -E '(^|/)(\.env|credentials\.json|cdk\.out|node_modules|\.venv)(/|$)' && exit 1 || true
git grep -n -E '(AKIA[0-9A-Z]{16}|gh[opsu]_[A-Za-z0-9]{20,}|-----BEGIN (RSA |EC )?PRIVATE KEY-----)' -- . \
  ':!docs/superpowers/plans/2026-08-15-import-hermes-agentcore-sample.md'
```

Expected: `git status --short` is empty; the tracked-file and secret scans print no matches.

- [ ] **Step 4: Record the verification result in the pull request**

Include these results in the PR body:

```markdown
## Verification

- `./scripts/verify.sh`
- Python tests: passed
- AgentCore Jest tests and TypeScript build: passed
- Python CDK synthesis: passed
- No AWS deploy performed
```
