"""Explicit CDK deployment of the Hermes AgentCore Runtime."""

from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, CfnResource, Stack
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from constructs import Construct


class HermesRuntimeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        execution_role: iam.IRole,
        workspace_bucket_name: str,
        memory_id: str,
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        project = self.node.try_get_context("project_name") or "hermes-agentcore"
        image = ecr_assets.DockerImageAsset(self, "HermesImage", directory=str(Path(__file__).parents[1] / "app" / "hermes"), platform=ecr_assets.Platform.LINUX_ARM64)
        image_pull_policy = iam.Policy(
            self,
            "RuntimeImagePullPolicy",
            roles=[execution_role],
            statements=[
                iam.PolicyStatement(
                    sid="AuthenticateToPullRuntimeImage",
                    actions=["ecr:GetAuthorizationToken"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="PullOnlyHermesRuntimeImage",
                    actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                    resources=[image.repository.repository_arn],
                ),
            ],
        )
        environment_variables = {
            "AGENTCORE_MEMORY_ID": memory_id,
            "S3_BUCKET": workspace_bucket_name,
            "EXECUTION_ROLE_ARN": execution_role.role_arn,
            "AWS_DEFAULT_REGION": Stack.of(self).region,
        }
        if guardrail_id and guardrail_version:
            environment_variables.update({
                "AGENTCORE_GUARDRAIL_ID": guardrail_id,
                "AGENTCORE_GUARDRAIL_VERSION": guardrail_version,
            })

        self.runtime = CfnResource(
            self,
            "Runtime",
            type="AWS::BedrockAgentCore::Runtime",
            properties={
                "AgentRuntimeName": "HermesProductSupport",
                "Description": "Hermes product support runtime for direct Bedrock chat.",
                "AgentRuntimeArtifact": {"ContainerConfiguration": {"ContainerUri": image.image_uri}},
                "RoleArn": execution_role.role_arn,
                "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
                "ProtocolConfiguration": "HTTP",
                "RequestHeaderConfiguration": {
                    "RequestHeaderAllowlist": [
                        "X-Amzn-Bedrock-AgentCore-Runtime-Custom-UserId",
                    ],
                },
                "EnvironmentVariables": environment_variables,
            },
        )
        self.runtime.add_dependency(image_pull_policy.node.default_child)
        CfnOutput(self, "RuntimeArn", value=self.runtime.get_att("AgentRuntimeArn").to_string())
