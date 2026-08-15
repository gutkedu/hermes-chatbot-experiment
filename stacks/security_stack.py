"""Security stack — Cognito.

Provides the user-pool authentication used by the web-only deployment.
"""

from __future__ import annotations

from aws_cdk import RemovalPolicy, Stack, aws_cognito as cognito, CfnOutput
from constructs import Construct


class HermesSecurityStack(Stack):
    """Cognito user pool for the authenticated web application."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name") or "hermes-agentcore"

        # ---- Cognito ------------------------------------------------------

        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"{project}-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=False,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ---- Outputs -----------------------------------------------------

        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
