#!/usr/bin/env python3
"""CDK app entry point for Hermes-Agent on Amazon Bedrock AgentCore.

Instantiates the web-only stacks in dependency order, including the explicit
AgentCore runtime.

Router, cron, observability, and token monitoring remain available as opt-in
stacks through CDK context flags. Guardrails are enabled by default for the
active deployment.
"""

from __future__ import annotations

import aws_cdk as cdk

from stacks.security_stack import HermesSecurityStack
from stacks.guardrails_stack import HermesGuardrailsStack
from stacks.agentcore_stack import HermesAgentCoreStack
from stacks.runtime_stack import HermesRuntimeStack
from stacks.observability_stack import HermesObservabilityStack
from stacks.router_stack import HermesRouterStack
from stacks.cron_stack import HermesCronStack
from stacks.token_monitoring_stack import HermesTokenMonitoringStack
from stacks.web_stack import HermesWebStack

app = cdk.App()


def context_bool(key: str, default: bool = False) -> bool:
    value = app.node.try_get_context(key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


project = app.node.try_get_context("project_name") or "hermes-agentcore"

alarm_email = app.node.try_get_context("alarm_email") or ""

# --------------------------------------------------------------------------
# Base stacks (no runtime IDs required)
# --------------------------------------------------------------------------

security_stack = HermesSecurityStack(app, f"{project}-security")

guardrails_stack = None
if context_bool("enable_guardrails", default=True):
    guardrails_stack = HermesGuardrailsStack(app, f"{project}-guardrails")

agentcore_stack = HermesAgentCoreStack(
    app,
    f"{project}-agentcore",
    guardrail_arn=(
        guardrails_stack.guardrail.attr_guardrail_arn
        if guardrails_stack is not None
        else None
    ),
)
if guardrails_stack is not None:
    agentcore_stack.add_dependency(guardrails_stack)

runtime_stack = HermesRuntimeStack(
    app,
    f"{project}-runtime",
    execution_role=agentcore_stack.execution_role,
    workspace_bucket_name=agentcore_stack.bucket.bucket_name,
    memory_id=agentcore_stack.memory.get_att("MemoryId").to_string(),
    guardrail_id=(
        guardrails_stack.guardrail.attr_guardrail_id
        if guardrails_stack is not None
        else None
    ),
    guardrail_version=(
        guardrails_stack.guardrail_version.attr_version
        if guardrails_stack is not None
        else None
    ),
)
runtime_stack.add_dependency(agentcore_stack)
if guardrails_stack is not None:
    runtime_stack.add_dependency(guardrails_stack)

enable_token_monitoring = context_bool("enable_token_monitoring")
enable_observability = enable_token_monitoring or context_bool("enable_observability")

observability_stack = None
if enable_observability:
    observability_stack = HermesObservabilityStack(
        app,
        f"{project}-observability",
        alarm_email=alarm_email,
    )

if context_bool("enable_router"):
    router_stack = HermesRouterStack(
        app,
        f"{project}-router",
        execution_role_arn=agentcore_stack.execution_role.role_arn,
        bucket_name=agentcore_stack.bucket.bucket_name,
        agentcore_runtime_arn=runtime_stack.runtime.get_att("AgentRuntimeArn").to_string(),
        agentcore_qualifier="DEFAULT",
    )
    router_stack.add_dependency(agentcore_stack)

if context_bool("enable_cron"):
    HermesCronStack(
        app,
        f"{project}-cron",
        agentcore_runtime_arn=runtime_stack.runtime.get_att("AgentRuntimeArn").to_string(),
        agentcore_qualifier="DEFAULT",
    )

if enable_token_monitoring:
    alarm_topic_arn = (
        observability_stack.alarm_topic.topic_arn
        if observability_stack is not None
        else ""
    )
    HermesTokenMonitoringStack(
        app,
        f"{project}-token-monitoring",
        alarm_topic_arn=alarm_topic_arn,
    )

# --------------------------------------------------------------------------
# Phase 3 web stack (authenticated browser chat)
# --------------------------------------------------------------------------

web_stack = HermesWebStack(
    app,
    f"{project}-web",
    user_pool_id=security_stack.user_pool.user_pool_id,
    user_pool_arn=security_stack.user_pool.user_pool_arn,
    agentcore_runtime_arn=runtime_stack.runtime.get_att("AgentRuntimeArn").to_string(),
    agentcore_qualifier="DEFAULT",
)
web_stack.add_dependency(security_stack)
web_stack.add_dependency(runtime_stack)

app.synth()
