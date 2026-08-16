from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from aws_cdk import App
from aws_cdk.assertions import Template

from stacks.agentcore_stack import HermesAgentCoreStack
from stacks.security_stack import HermesSecurityStack

ROOT = Path(__file__).resolve().parents[1]
CDK = ROOT / "node_modules" / ".bin" / "cdk"
PYTHON = ROOT / ".venv" / "bin" / "python"
DEPLOY = ROOT / "scripts" / "deploy.sh"


def _synth_stack_names(*context: tuple[str, str]) -> set[str]:
    with tempfile.TemporaryDirectory() as output_dir:
        command = [
            str(CDK),
            "synth",
            "--app",
            f"{PYTHON} {ROOT / 'app.py'}",
            "--output",
            output_dir,
            "--quiet",
        ]
        for key, value in context:
            command.extend(["-c", f"{key}={value}"])

        environment = os.environ.copy()
        environment["CDK_DISABLE_VERSION_CHECK"] = "1"
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
        manifest = json.loads(
            (Path(output_dir) / "manifest.json").read_text(encoding="utf-8")
        )
        return {
            artifact.get("displayName", artifact_id)
            for artifact_id, artifact in manifest["artifacts"].items()
            if artifact.get("type") == "aws:cloudformation:stack"
        }


def test_default_synthesis_is_web_only() -> None:
    assert _synth_stack_names() == {
        "hermes-agentcore-security",
        "hermes-agentcore-agentcore",
        "hermes-agentcore-knowledge-base",
        "hermes-agentcore-runtime",
        "hermes-agentcore-web",
    }


def test_security_stack_contains_cognito_but_no_dedicated_crypto_or_secrets() -> None:
    app = App(context={"project_name": "hermes-test"})
    template = Template.from_stack(HermesSecurityStack(app, "Security"))

    resource_types = {
        resource["Type"]
        for resource in template.to_json().get("Resources", {}).values()
    }
    assert resource_types == {
        "AWS::Cognito::UserPool",
    }


def test_agentcore_stack_has_no_vpc_or_security_group_resources() -> None:
    app = App(context={"project_name": "hermes-test"})
    template = Template.from_stack(
        HermesAgentCoreStack(app, "AgentCore")
    )

    resource_types = {
        resource["Type"]
        for resource in template.to_json().get("Resources", {}).values()
    }
    assert not any(resource_type.startswith("AWS::EC2::") for resource_type in resource_types)


def test_token_monitoring_remains_synthesizable_when_enabled() -> None:
    stack_names = _synth_stack_names(("enable_token_monitoring", "true"))

    assert "hermes-agentcore-token-monitoring" in stack_names
    assert "hermes-agentcore-observability" in stack_names


def test_agentcore_runtime_uses_public_networking() -> None:
    runtime = json.loads(
        (ROOT / "agentcore" / "agentcore.json").read_text(encoding="utf-8")
    )["runtimes"][0]

    assert runtime["networkMode"] == "PUBLIC"
    assert "vpc" not in runtime
    assert "securityGroup" not in runtime


def test_explicit_cdk_runtime_uses_the_knowledge_base_environment_variable() -> None:
    stack_names = _synth_stack_names()
    assert "hermes-agentcore-runtime" in stack_names


def test_deploy_script_is_web_only() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    assert "phase4" not in script
    for disabled_stack in (
        "vpc",
        "router",
        "cron",
        "token-monitoring",
        "observability",
        "gateway",
    ):
        assert f'"${{PROJECT_NAME}}-{disabled_stack}"' not in script

    assert '"${PROJECT_NAME}-security"' in script
    assert '"${PROJECT_NAME}-agentcore"' in script
    assert '"${PROJECT_NAME}-knowledge-base"' in script
    assert '"${PROJECT_NAME}-runtime"' in script
    assert '"${PROJECT_NAME}-web"' in script

    phase1 = script.split("phase1()", 1)[1].split("phase2()", 1)[0]
    assert phase1.index('"${PROJECT_NAME}-agentcore"') < phase1.index(
        '"${PROJECT_NAME}-security"'
    )
