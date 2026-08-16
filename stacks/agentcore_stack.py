"""AgentCore base stack — IAM execution role and S3 bucket.

Defines the IAM role that AgentCore containers assume, the S3 bucket for
per-user workspace persistence, and the permissions needed by the public
AgentCore runtime.
"""

from __future__ import annotations

from aws_cdk import (
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    CfnOutput,
)
from constructs import Construct


class HermesAgentCoreStack(Stack):
    """IAM role and S3 user-files bucket for AgentCore."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name") or "hermes-agentcore"
        region = Stack.of(self).region
        account = Stack.of(self).account

        # ---- S3 bucket for user files ------------------------------------

        self.bucket = s3.Bucket(
            self,
            "UserFilesBucket",
            bucket_name=f"{project}-user-files-{account}-{region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="CleanupOldVersions",
                    noncurrent_version_expiration=Duration.days(90),
                ),
            ],
        )

        # ---- IAM execution role ------------------------------------------
        # This role is assumed by the AgentCore runtime containers.

        self.execution_role = iam.Role(
            self,
            "ExecutionRole",
            role_name=f"{project}-execution-role",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": Fn.sub("arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:runtime/*")},
                },
            ),
        )
        self.execution_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                sid="AllowRuntimeRoleToRefreshScopedSessions",
                actions=["sts:AssumeRole"],
                principals=[iam.AccountPrincipal(account).with_conditions({
                    "ArnEquals": {
                        "aws:PrincipalArn": Fn.sub(
                            f"arn:${{AWS::Partition}}:iam::${{AWS::AccountId}}:role/{project}-execution-role"
                        ),
                    },
                })],
            )
        )

        # Bedrock model invocation.
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockInvoke",
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    Stack.of(self).format_arn(
                        service="bedrock", region=region, account="", resource="foundation-model/amazon.nova-lite-v1:0"
                    ),
                ],
            )
        )

        # Bedrock Guardrails.
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockGuardrails",
                actions=["bedrock:ApplyGuardrail"],
                resources=[f"arn:aws:bedrock:{region}:{account}:guardrail/*"],
            )
        )

        # S3 — workspace objects only. The runtime receives an additional
        # short-lived STS session policy for the concrete ws-* namespace.
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="WorkspaceObjectsByOpaquePrefix",
                actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                resources=[self.bucket.arn_for_objects("ws-*/*")],
            )
        )
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="WorkspaceListByOpaquePrefix",
                actions=["s3:ListBucket"],
                resources=[self.bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": ["ws-*/*"]}},
            )
        )

        # STS — self-assume for scoped credentials.
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="SelfAssume",
                actions=["sts:AssumeRole"],
                resources=[self.execution_role.role_arn],
            )
        )

        # CloudWatch — logging and metrics.
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatch",
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "cloudwatch:PutMetricData",
                ],
                resources=["*"],
            )
        )

        # ---- Outputs -----------------------------------------------------

        CfnOutput(self, "ExecutionRoleArn", value=self.execution_role.role_arn)
        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
