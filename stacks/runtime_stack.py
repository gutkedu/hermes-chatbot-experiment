"""Explicit CDK deployment of the Hermes AgentCore Runtime."""

from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, CfnResource, Stack
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_iam as iam
from constructs import Construct


class HermesRuntimeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, execution_role: iam.IRole, knowledge_base_id: str, knowledge_base_arn: str, workspace_bucket_name: str, **kwargs) -> None:
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
        retrieval_policy = iam.Policy(
            self,
            "KnowledgeBaseRetrievalPolicy",
            roles=[execution_role],
            statements=[iam.PolicyStatement(
                sid="RetrieveOnlyFromProductKnowledgeBase",
                actions=["bedrock:Retrieve"],
                resources=[knowledge_base_arn],
            )],
        )
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
                "EnvironmentVariables": {
                    "KNOWLEDGE_BASE_ID": knowledge_base_id,
                    "S3_BUCKET": workspace_bucket_name,
                    "EXECUTION_ROLE_ARN": execution_role.role_arn,
                    "AWS_DEFAULT_REGION": Stack.of(self).region,
                },
            },
        )
        self.runtime.add_dependency(image_pull_policy.node.default_child)
        self.runtime.add_dependency(retrieval_policy.node.default_child)
        CfnOutput(self, "RuntimeArn", value=self.runtime.get_att("AgentRuntimeArn").to_string())
