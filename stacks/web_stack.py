"""Authenticated browser, Cognito OAuth, and streaming chat API resources."""

from __future__ import annotations

import json
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
)
from constructs import Construct


class HermesWebStack(Stack):
    """Static web application and Cognito-protected streaming BFF."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        user_pool_id: str,
        user_pool_arn: str,
        agentcore_runtime_arn: str,
        agentcore_qualifier: str = "",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project = self.node.try_get_context("project_name") or "hermes-agentcore"
        region = Stack.of(self).region
        account = Stack.of(self).account

        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
        )
        web_origin = f"https://{distribution.domain_name}"
        redirect_uri = f"{web_origin}/"

        domain_prefix = f"{project}-{account}-{region}".lower().replace("_", "-")
        user_pool_domain = cognito.CfnUserPoolDomain(
            self,
            "UserPoolDomain",
            domain=domain_prefix,
            user_pool_id=user_pool_id,
        )
        resource_server = cognito.CfnUserPoolResourceServer(
            self,
            "ChatResourceServer",
            identifier="chat",
            name="Hermes chat API",
            user_pool_id=user_pool_id,
            scopes=[
                cognito.CfnUserPoolResourceServer.ResourceServerScopeTypeProperty(
                    scope_name="send",
                    scope_description="Send messages to Hermes",
                ),
            ],
        )
        web_client = cognito.CfnUserPoolClient(
            self,
            "WebClient",
            user_pool_id=user_pool_id,
            client_name=f"{project}-web",
            generate_secret=False,
            allowed_o_auth_flows_user_pool_client=True,
            allowed_o_auth_flows=["code"],
            allowed_o_auth_scopes=["openid", "email", "chat/send"],
            callback_ur_ls=[redirect_uri],
            default_redirect_uri=redirect_uri,
            logout_ur_ls=[redirect_uri],
            supported_identity_providers=["COGNITO"],
        )
        web_client.add_resource_dependency(resource_server)
        web_client.add_resource_dependency(user_pool_domain)
        cognito_domain = Fn.sub(
            "https://${Domain}.auth.${AWS::Region}.amazoncognito.com",
            {"Domain": domain_prefix},
        )

        log_group = logs.LogGroup(
            self,
            "WebChatLogs",
            log_group_name=f"/aws/lambda/{project}-web-chat",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        web_chat = lambda_.Function(
            self,
            "WebChatFunction",
            function_name=f"{project}-web-chat",
            runtime=lambda_.Runtime.NODEJS_22_X,
            handler="index.handler",
            code=lambda_.Code.from_asset(str(Path(__file__).parents[1] / "lambda" / "web_chat")),
            timeout=Duration.seconds(900),
            memory_size=512,
            log_group=log_group,
            environment={
                "AGENTCORE_RUNTIME_ARN": agentcore_runtime_arn,
                "AGENTCORE_QUALIFIER": agentcore_qualifier,
                "USER_POOL_ID": user_pool_id,
                "USER_POOL_CLIENT_ID": web_client.ref,
                "COGNITO_DOMAIN": cognito_domain,
                "WEB_REDIRECT_URI": redirect_uri,
                "ALLOWED_ORIGIN": web_origin,
            },
        )
        web_chat.add_to_role_policy(
            iam.PolicyStatement(
                sid="InvokeConfiguredAgentCoreRuntime",
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:InvokeAgentRuntimeForUser",
                ],
                resources=[agentcore_runtime_arn, f"{agentcore_runtime_arn}/*"],
            )
        )

        invoke_uri = Fn.sub(
            "arn:${AWS::Partition}:apigateway:${AWS::Region}:lambda:path/2021-11-15/functions/${FunctionArn}/response-streaming-invocations",
            {"FunctionArn": web_chat.function_arn},
        )
        api_body = {
            "openapi": "3.0.1",
            "info": {"title": f"{project} web chat", "version": "1.0"},
            "components": {
                "securitySchemes": {
                    "cognito": {
                        "type": "apiKey",
                        "name": "Authorization",
                        "in": "header",
                        "x-amazon-apigateway-authtype": "cognito_user_pools",
                        "x-amazon-apigateway-authorizer": {
                            "type": "cognito_user_pools",
                            "providerARNs": [user_pool_arn],
                        },
                    },
                },
            },
            "paths": {
                "/chat": {
                    "options": self._options_operation(web_origin),
                    "post": {
                        "security": [{"cognito": ["chat/send"]}],
                        "x-amazon-apigateway-integration": self._proxy_integration(invoke_uri),
                    },
                },
                "/config": {
                    "get": {
                        "x-amazon-apigateway-integration": self._proxy_integration(invoke_uri),
                    },
                },
            },
        }
        rest_api = apigateway.CfnRestApi(
            self,
            "WebChatApi",
            name=f"{project}-web-chat",
            description="Cognito-protected streaming Hermes chat API",
            endpoint_configuration={"types": ["REGIONAL"]},
            body=api_body,
            mode="merge",
        )
        permission = lambda_.CfnPermission(
            self,
            "ApiInvokePermission",
            action="lambda:InvokeFunction",
            function_name=web_chat.function_name,
            principal="apigateway.amazonaws.com",
            source_arn=Fn.sub(
                "arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${ApiId}/*/*",
                {"ApiId": rest_api.ref},
            ),
        )
        deployment = apigateway.CfnDeployment(
            self,
            "WebChatDeployment",
            rest_api_id=rest_api.ref,
            stage_name="prod",
        )
        deployment.add_resource_dependency(permission)
        deployment.add_resource_dependency(rest_api)
        for response_type in ("DEFAULT_4XX", "UNAUTHORIZED"):
            apigateway.CfnGatewayResponse(
                self,
                response_type.title().replace("_", "") + "Response",
                response_type=response_type,
                rest_api_id=rest_api.ref,
                response_parameters={
                    "gatewayresponse.header.Access-Control-Allow-Origin": f"'{web_origin}'",
                    "gatewayresponse.header.Access-Control-Allow-Headers": "'Authorization,Content-Type'",
                    "gatewayresponse.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
                },
            )

        api_url = Fn.sub(
            "https://${ApiId}.execute-api.${AWS::Region}.${AWS::URLSuffix}/prod",
            {"ApiId": rest_api.ref},
        )
        web_assets = s3_deployment.BucketDeployment(
            self,
            "WebAssets",
            destination_bucket=site_bucket,
            sources=[
                s3_deployment.Source.asset(str(Path(__file__).parents[1] / "web")),
                s3_deployment.Source.data(
                    "runtime-config.js",
                    f"window.HERMES_API_BASE = {json.dumps(api_url)};",
                ),
            ],
            distribution=distribution,
            distribution_paths=["/*"],
            prune=True,
        )
        # BucketDeployment is a high-level construct; attach ordering through
        # its construct node so the API and Cognito client exist before the
        # browser assets are uploaded.
        web_assets.node.add_dependency(deployment)
        web_assets.node.add_dependency(web_client)

        CfnOutput(self, "SiteUrl", value=web_origin)
        CfnOutput(self, "ApiUrl", value=api_url)
        CfnOutput(self, "CognitoDomain", value=cognito_domain)
        CfnOutput(self, "UserPoolClientId", value=web_client.ref)

    @staticmethod
    def _proxy_integration(uri: str) -> dict:
        return {
            "type": "aws_proxy",
            "httpMethod": "POST",
            "uri": uri,
            "timeoutInMillis": 900000,
            "responseTransferMode": "STREAM",
        }

    @staticmethod
    def _options_operation(origin: str) -> dict:
        return {
            "responses": {"204": {"description": "CORS preflight"}},
            "x-amazon-apigateway-integration": {
                "type": "mock",
                "requestTemplates": {"application/json": '{"statusCode": 204}'},
                "responses": {
                    "default": {
                        "statusCode": "204",
                        "responseParameters": {
                            "method.response.header.Access-Control-Allow-Origin": f"'{origin}'",
                            "method.response.header.Access-Control-Allow-Headers": "'Authorization,Content-Type'",
                            "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
                        },
                    },
                },
            },
        }
