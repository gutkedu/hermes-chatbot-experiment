from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from stacks.agentcore_stack import HermesAgentCoreStack
from stacks.guardrails_stack import HermesGuardrailsStack
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


def test_default_synthesis_includes_the_active_guardrail() -> None:
    assert _synth_stack_names() == {
        "hermes-agentcore-security",
        "hermes-agentcore-guardrails",
        "hermes-agentcore-agentcore",
        "hermes-agentcore-runtime",
        "hermes-agentcore-web",
    }


def test_guardrails_stack_publishes_standard_policy_and_immutable_version() -> None:
    app = App(context={"project_name": "hermes-test"})
    template = Template.from_stack(HermesGuardrailsStack(app, "Guardrails"))

    template.resource_count_is("AWS::Bedrock::Guardrail", 1)
    template.resource_count_is("AWS::Bedrock::GuardrailVersion", 1)
    guardrail = template.find_resources("AWS::Bedrock::Guardrail")
    properties = next(iter(guardrail.values()))["Properties"]
    assert properties["ContentPolicyConfig"]["ContentFiltersTierConfig"] == {"TierName": "STANDARD"}
    assert properties["CrossRegionConfig"]["GuardrailProfileArn"]["Fn::Join"]
    assert {item["Type"] for item in properties["ContentPolicyConfig"]["FiltersConfig"]} == {
        "HATE",
        "INSULTS",
        "MISCONDUCT",
        "PROMPT_ATTACK",
        "SEXUAL",
        "VIOLENCE",
    }
    outputs = template.to_json()["Outputs"]
    assert "GuardrailId" in outputs
    assert "GuardrailVersionOutput" in outputs


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


def test_agentcore_workspace_bucket_is_private_versioned_and_prefix_scoped() -> None:
    app = App(context={"project_name": "hermes-test"})
    template = Template.from_stack(HermesAgentCoreStack(app, "AgentCore"))
    template.has_resource_properties("AWS::S3::Bucket", {
        "BucketEncryption": Match.any_value(),
        "PublicAccessBlockConfiguration": Match.object_like({"BlockPublicAcls": True}),
        "VersioningConfiguration": {"Status": "Enabled"},
    })
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))
    assert "s3:*" not in policies
    assert "s3:ListBucket" in policies
    assert "ws-*/*" in policies
    assert "grant_read_write" not in policies


def test_agentcore_stack_provisions_memory_with_required_strategies_and_outputs() -> None:
    app = App(context={"project_name": "hermes-test"})
    template = Template.from_stack(HermesAgentCoreStack(app, "AgentCore"))

    template.has_resource_properties(
        "AWS::BedrockAgentCore::Memory",
        {
            "EventExpiryDuration": 90,
            "Name": "hermes_test_memory",
            "MemoryStrategies": [
                {
                    "UserPreferenceMemoryStrategy": {
                        "Name": "UserPreferences",
                        "NamespaceTemplates": ["/users/{actorId}/preferences/"],
                    }
                },
                {
                    "SummaryMemoryStrategy": {
                        "Name": "SessionSummaries",
                        "NamespaceTemplates": ["/users/{actorId}/summaries/{sessionId}/"],
                    }
                },
            ],
        },
    )
    outputs = template.to_json()["Outputs"]
    assert "MemoryId" in outputs
    assert "MemoryArn" in outputs


def test_agentcore_memory_permissions_are_scoped_to_created_memory() -> None:
    app = App(context={"project_name": "hermes-test"})
    template = Template.from_stack(HermesAgentCoreStack(app, "AgentCore"))
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))

    for action in ("bedrock-agentcore:GetMemory", "bedrock-agentcore:CreateEvent", "bedrock-agentcore:RetrieveMemoryRecords"):
        assert action in policies
    assert '"Fn::GetAtt": ["Memory", "MemoryArn"]' in policies


def test_runtime_receives_workspace_bucket_and_execution_role_configuration() -> None:
    stack_names = _synth_stack_names()
    assert "hermes-agentcore-runtime" in stack_names
    with tempfile.TemporaryDirectory() as output_dir:
        command = [
            str(CDK), "synth", "hermes-agentcore-runtime", "--app",
            f"{PYTHON} {ROOT / 'app.py'}", "--output", output_dir, "--quiet",
        ]
        environment = os.environ.copy()
        environment["CDK_DISABLE_VERSION_CHECK"] = "1"
        subprocess.run(command, cwd=ROOT, check=True, env=environment, capture_output=True, text=True)
        template = json.loads((Path(output_dir) / "hermes-agentcore-runtime.template.json").read_text())
    runtime = next(value for value in template["Resources"].values() if value["Type"] == "AWS::BedrockAgentCore::Runtime")
    variables = runtime["Properties"]["EnvironmentVariables"]
    assert "S3_BUCKET" in variables
    assert "EXECUTION_ROLE_ARN" in variables
    assert "AGENTCORE_MEMORY_ID" in variables
    assert "AGENTCORE_GUARDRAIL_ID" in variables
    assert "AGENTCORE_GUARDRAIL_VERSION" in variables


def test_guardrail_iam_is_scoped_to_the_created_guardrail() -> None:
    app = App(context={"project_name": "hermes-test"})
    guardrails = HermesGuardrailsStack(app, "Guardrails")
    template = Template.from_stack(
        HermesAgentCoreStack(
            app,
            "AgentCore",
            guardrail_arn=guardrails.guardrail.attr_guardrail_arn,
        )
    )
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))

    assert "bedrock:ApplyGuardrail" in policies
    assert "guardrail/*" not in policies


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


def test_explicit_cdk_runtime_does_not_use_knowledge_base_configuration() -> None:
    stack_names = _synth_stack_names()
    assert "hermes-agentcore-runtime" in stack_names
    assert not any("knowledge-base" in name for name in stack_names)


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
    assert '"${PROJECT_NAME}-runtime"' in script
    assert '"${PROJECT_NAME}-web"' in script
    assert "--exclude='memory.py'" in script

    phase1 = script.split("phase1()", 1)[1].split("phase2()", 1)[0]
    assert phase1.index('"${PROJECT_NAME}-agentcore"') < phase1.index(
        '"${PROJECT_NAME}-security"'
    )
