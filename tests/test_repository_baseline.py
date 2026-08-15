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
