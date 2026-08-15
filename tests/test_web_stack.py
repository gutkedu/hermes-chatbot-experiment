from __future__ import annotations

import json

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from stacks.web_stack import HermesWebStack


def _template() -> Template:
    app = App(context={"project_name": "hermes-test"})
    stack = HermesWebStack(
        app,
        "Web",
        user_pool_id="us-east-1_pool",
        user_pool_arn="arn:aws:cognito-idp:us-east-1:1:userpool/us-east-1_pool",
        agentcore_runtime_arn="arn:aws:bedrock:us-east-1:1:agent-runtime/hermes",
        agentcore_qualifier="live",
        env={"account": "1", "region": "us-east-1"},
    )
    return Template.from_stack(stack)


def test_web_stack_has_chat_scope_and_cognito_client():
    template = _template()
    template.has_resource_properties(
        "AWS::Cognito::UserPoolResourceServer",
        Match.object_like({
            "Identifier": "chat",
            "Scopes": Match.array_with([Match.object_like({"ScopeName": "send"})]),
        }),
    )
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        Match.object_like({
            "GenerateSecret": False,
            "AllowedOAuthFlows": ["code"],
            "AllowedOAuthScopes": Match.array_with(["chat/send"]),
        }),
    )


def test_cognito_domain_uses_cloudformation_pseudo_parameters():
    template = _template()
    domain = template.to_json()["Resources"]["UserPoolDomain"]["Properties"]["Domain"]

    assert domain == {
        "Fn::Sub": "hermes-test-${AWS::AccountId}-${AWS::Region}",
    }


def test_rest_api_uses_response_streaming_lambda_proxy():
    template = _template()
    resources = template.find_resources("AWS::ApiGateway::RestApi")
    serialized = json.dumps(resources)
    assert "response-streaming-invocations" in serialized
    assert '"responseTransferMode": "STREAM"' in serialized
    assert '"chat/send"' in serialized


def test_cors_preflight_declares_headers_for_api_gateway_mapping():
    operation = HermesWebStack._options_operation("https://example.com")

    assert set(operation["responses"]["204"]["headers"]) == {
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Headers",
        "Access-Control-Allow-Methods",
    }


def test_web_stack_has_private_site_and_scoped_agentcore_permission():
    template = _template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        Match.object_like({
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        }),
    )
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))
    assert "bedrock-agentcore:InvokeAgentRuntime" in policies
    assert "arn:aws:bedrock:us-east-1:1:agent-runtime/hermes" in policies


def test_web_stack_outputs_urls_and_client_id():
    template = _template()
    outputs = template.to_json().get("Outputs", {})
    assert {"SiteUrl", "ApiUrl", "UserPoolClientId"}.issubset(outputs)
