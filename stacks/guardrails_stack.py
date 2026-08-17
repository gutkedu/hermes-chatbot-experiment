"""Guardrails stack — Bedrock Guardrails for content safety.

Configures the generic safety policy used before model input and output reach
the Hermes runtime boundary.
"""

from __future__ import annotations

from aws_cdk import (
    Stack,
    aws_bedrock as bedrock,
    CfnOutput,
)
from constructs import Construct


class HermesGuardrailsStack(Stack):
    """Bedrock Guardrails: Standard content safety + sensitive information."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name") or "hermes-agentcore"
        enable = self.node.try_get_context("enable_guardrails")
        if enable is False:
            return

        # PROMPT_ATTACK requires the Standard tier. The US profile keeps
        # guardrail evaluation within the declared US geography.
        self.guardrail_profile_arns = [
            self.format_arn(
                service="bedrock",
                region=profile_region,
                resource="guardrail-profile/us.guardrail.v1:0",
            )
            for profile_region in ("us-east-1", "us-east-2", "us-west-2")
        ]
        guardrail_profile_arn = self.guardrail_profile_arns[0]

        # ---- Content filter categories -----------------------------------

        filters = [
            bedrock.CfnGuardrail.ContentFilterConfigProperty(
                type=cat,
                input_strength="MEDIUM",
                output_strength="NONE" if cat == "PROMPT_ATTACK" else "MEDIUM",
                input_action="BLOCK",
                output_action="NONE" if cat == "PROMPT_ATTACK" else "BLOCK",
            )
            for cat in [
                "SEXUAL",
                "VIOLENCE",
                "HATE",
                "INSULTS",
                "MISCONDUCT",
                "PROMPT_ATTACK",
            ]
        ]

        # ---- PII and secrets ---------------------------------------------

        pii_entities = [
            bedrock.CfnGuardrail.PiiEntityConfigProperty(
                type=t,
                action="ANONYMIZE",
                input_action="ANONYMIZE",
                output_action="ANONYMIZE",
            )
            for t in [
                "EMAIL",
                "PHONE",
                "NAME",
                "ADDRESS",
                "USERNAME",
                "IP_ADDRESS",
            ]
        ]
        pii_entities.extend(
            bedrock.CfnGuardrail.PiiEntityConfigProperty(
                type=t,
                action="BLOCK",
                input_action="BLOCK",
                output_action="BLOCK",
            )
            for t in [
                "PASSWORD",
                "AWS_ACCESS_KEY",
                "AWS_SECRET_KEY",
                "US_SOCIAL_SECURITY_NUMBER",
                "CREDIT_DEBIT_CARD_NUMBER",
            ]
        )

        # ---- Guardrail resource ------------------------------------------

        self.guardrail = bedrock.CfnGuardrail(
            self,
            "Guardrail",
            name=f"{project}-guardrail",
            description="Content safety guardrail for Hermes AgentCore",
            blocked_input_messaging="I can't help with that request.",
            blocked_outputs_messaging="I can't provide that response.",
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=filters,
                content_filters_tier_config=bedrock.CfnGuardrail.ContentFiltersTierConfigProperty(
                    tier_name="STANDARD",
                ),
            ),
            cross_region_config=bedrock.CfnGuardrail.GuardrailCrossRegionConfigProperty(
                guardrail_profile_arn=guardrail_profile_arn,
            ),
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=pii_entities,
            ),
        )

        self.guardrail_version = bedrock.CfnGuardrailVersion(
            self,
            "GuardrailVersion",
            guardrail_identifier=self.guardrail.attr_guardrail_id,
            description="Initial version",
        )

        # ---- Outputs -----------------------------------------------------

        CfnOutput(
            self,
            "GuardrailId",
            value=self.guardrail.attr_guardrail_id,
        )
        CfnOutput(
            self,
            "GuardrailVersionOutput",
            value=self.guardrail_version.attr_version,
            export_name=f"{project}-guardrail-version",
        )
