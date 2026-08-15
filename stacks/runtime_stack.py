"""Explicit CDK deployment of the Hermes AgentCore Runtime."""

from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, CfnResource, Stack
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from constructs import Construct


class HermesRuntimeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, execution_role: iam.IRole, knowledge_base_id: str, knowledge_base_arn: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        project = self.node.try_get_context("project_name") or "hermes-agentcore"
        image = ecr_assets.DockerImageAsset(self, "HermesImage", directory=str(Path(__file__).parents[1] / "app" / "hermes"), platform=ecr_assets.Platform.LINUX_ARM64)
        execution_role.add_to_principal_policy(iam.PolicyStatement(
            sid="RetrieveOnlyFromProductKnowledgeBase",
            actions=["bedrock:Retrieve"],
            resources=[knowledge_base_arn],
        ))
        self.runtime = CfnResource(
            self,
            "Runtime",
            type="AWS::BedrockAgentCore::Runtime",
            properties={
                "AgentRuntimeName": "HermesProductSupport",
                "Description": "Hermes product support runtime grounded in the product Knowledge Base.",
                "AgentRuntimeArtifact": {"ContainerConfiguration": {"ContainerUri": image.image_uri}},
                "RoleArn": execution_role.role_arn,
                "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
                "ProtocolConfiguration": "HTTP",
                "EnvironmentVariables": {"KNOWLEDGE_BASE_ID": knowledge_base_id, "AWS_DEFAULT_REGION": Stack.of(self).region},
            },
        )
        CfnOutput(self, "RuntimeArn", value=self.runtime.ref)
