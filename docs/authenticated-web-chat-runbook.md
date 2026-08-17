# Authenticated web chat runbook

This runbook is for an AWS account where the operator is authorized to create
and remove Cognito, CloudFront, S3, API Gateway, Lambda, and AgentCore
resources. The local verifier is credential-free; the smoke test below is the
authorized-environment check.

## Deploy

1. Install the prerequisites from `README.md`, configure AWS credentials, and
   choose `us-east-1` as the region. Set `project_name` in `cdk.json`.
2. Deploy the foundation and runtime:

   ```bash
   ./scripts/deploy.sh phase1
   ./scripts/deploy.sh phase2
   ./scripts/deploy.sh phase3
   ```

   Phase 2 creates the AgentCore runtime, workspace bucket, and persistent
   Memory. The runtime answers directly through the configured Bedrock model;
   there is no document ingestion step.
   Phase 3 deploys only the `hermes-agentcore-web` stack. It prints the
   CloudFront site URL, streaming API URL, Cognito domain, and public web
   client ID.

   Phase 1 also deploys `hermes-agentcore-guardrails`. It creates the generic
   Standard-tier content policy and publishes a numbered immutable version;
   the runtime receives that exact Guardrail ID/version and never uses `DRAFT`.
3. Create two test users in the retained user pool. The pool ID is the
   `UserPoolId` output of `hermes-agentcore-security`:

   ```bash
   read -r -s TEMP_PASSWORD
   aws cognito-idp admin-create-user \
     --user-pool-id "$USER_POOL_ID" --username user-a@example.com \
     --temporary-password "$TEMP_PASSWORD"
   aws cognito-idp admin-create-user \
     --user-pool-id "$USER_POOL_ID" --username user-b@example.com \
     --temporary-password "$TEMP_PASSWORD"
   unset TEMP_PASSWORD
   ```

   Use private password handling appropriate for the account; do not commit
   passwords, access tokens, or client secrets.
4. Open the printed CloudFront site URL. Sign in through the Cognito Hosted UI,
   complete the first-login password change if prompted, and send a message.
   The assistant bubble should appear immediately and grow as
   `message.delta` SSE events arrive.

## Region, model access, and cost envelope

The demonstrated deployment is pinned to `us-east-1` and uses
`amazon.nova-lite-v1:0` through Bedrock Converse. Enable access to that model
in the account before deployment. The Standard Guardrail uses the US
cross-Region profile; its execution role therefore allows `ApplyGuardrail` on
the guardrail plus the `us-east-1`, `us-east-2`, and `us-west-2` profile ARNs.
See the [cross-Region Guardrail permission guide](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrail-profiles-permissions.html)
and [current Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) before
changing region, model, or policy tier.

This is a usage-priced experiment: model tokens, Lambda/API Gateway, S3/ECR,
CloudWatch, Guardrail text units, Memory events/records/retrievals, and
AgentCore Runtime CPU/memory are separate line items. For orientation only,
the current AgentCore Runtime rates are `$0.0895/vCPU-hour` and
`$0.00945/GB-hour`; a conservative 60-second, 1-vCPU/1-GB fully-active
example is about `$0.00165` before model and other service charges. A short
one-kilobyte input plus one-kilobyte output consumes two Guardrail evaluations
and is normally well below one cent; actual billing is based on text units and
the configured safeguards. Use Cost Explorer after a smoke run rather than
treating these figures as a quote. See the
[AgentCore pricing page](https://aws.amazon.com/bedrock/agentcore/pricing/)
for live rates and billing rules.

## Verify authentication and streaming

After sign-in, send a normal support question through the authenticated chat.
The answer is generated directly by the configured Bedrock model and should
arrive as incremental `message.delta` events. The browser contract contains no
document citations or retrieval-specific status.

The BFF derives opaque AgentCore session and user IDs from the Cognito `iss`
and `sub` claims. It never accepts a browser-provided session identifier. It
passes the derived user ID as the allowlisted
`X-Amzn-Bedrock-AgentCore-Runtime-Custom-UserId` header; the runtime uses that
header for the Memory actor and ignores the payload's untrusted `userId`.

## Guardrail policy and operations

The active policy is intentionally generic. Harmful content and prompt attacks
are blocked in both directions. Common PII (`EMAIL`, `PHONE`, `NAME`,
`ADDRESS`, `USERNAME`, and `IP_ADDRESS`) is anonymized in input and output.
Passwords, AWS access keys/secrets, Social Security numbers, and payment card
numbers are blocked. A blocked input is stopped before Memory or model work;
an output is accumulated and checked before any browser delta is emitted.

Guardrail intervention is a terminal `guardrail.intervened` browser event and
does not offer retry for the same content. Guardrail service failures are a
separate retryable `guardrail_unavailable` error. Provider errors and other
runtime failures use a generic `runtime_failure` code; raw prompts, outputs,
tokens, credentials, detected values, and AWS exception text are not exposed.

To inspect the active policy without printing content values, use the stack
outputs and the AWS control plane:

```bash
aws cloudformation describe-stacks \
  --stack-name hermes-agentcore-guardrails \
  --query 'Stacks[0].Outputs[?OutputKey==`GuardrailId` || OutputKey==`GuardrailVersionOutput`].[OutputKey,OutputValue]' \
  --output table
```

Tune the policy by changing `stacks/guardrails_stack.py`, deploy it, and verify
the new numbered `GuardrailVersionOutput` before the runtime rollout. Treat
each numbered version as immutable; do not replace the runtime environment
with `DRAFT`. Record expected false positives (for example, support tickets
that contain contact details) and adjust only the relevant PII action or
filter strength. Re-run the credential-free tests and the authorized web
smoke check after each policy change.

## Workspace persistence and skills

When `S3_BUCKET` is configured, the BFF/router sends an internal
`workspaceNamespace` in the form `ws-<64 lowercase hex characters>`. It is
derived from the AgentCore `runtimeSessionId`; the runtime validates the
binding against `context.session_id`. The browser may send only `message` and
cannot select a session, namespace, S3 key, or skill path.

The runtime restores the namespace before agent creation, starts
periodic saves using `WORKSPACE_SYNC_INTERVAL` (300 seconds by default), saves
after each invocation, and attempts one final synchronous save during
shutdown. Individual S3 download/upload failures are logged as safe error
types and do not stop the remaining files or the conversation. Logs never
include file contents, prompts, model output, tokens, or credentials.
The hosted runtime also raises the log level for Hermes' conversation-turn,
API-usage, and turn-finalizer diagnostics because their INFO messages can
contain prompt previews or token counts; warnings and errors remain available
for operations.

Without `S3_BUCKET`, the runtime explicitly operates with an ephemeral
workspace. With persistence enabled, a missing, malformed, traversal-like, or
session-mismatched namespace rejects workspace access.

## AgentCore Memory and personalization

Phase 2 also creates one persistent `AWS::BedrockAgentCore::Memory` resource.
It retains events for 90 days and has two long-term extraction strategies:

- `USER_PREFERENCE` writes actor-wide preferences under
  `/users/{actorId}/preferences/`.
- `SUMMARIZATION` writes session summaries under
  `/users/{actorId}/summaries/{sessionId}/`.

The runtime maps the authenticated AgentCore `runtimeUserId` to `actorId` and
uses `context.session_id` as `sessionId`. The browser payload is not trusted
for either identity. Retrieved records are bounded and inserted into the
prompt as explicitly untrusted context; Memory IAM permissions are scoped to
the created resource.

These stores have distinct responsibilities:

- AgentCore Memory stores conversational events and extracted personalization,
  such as preferences and prior-session summaries.
- The workspace bucket/S3 stores files, skills, and Hermes' local workspace
  state. It is not a substitute for long-term conversational memory.
- The Bedrock model answers the current request directly. AgentCore Memory is
  the only persistent conversational context source in this experiment.

Long-term extraction is asynchronous. A successful turn is written once as a
`USER` plus `ASSISTANT` event after the response stream completes, but a later
read in the same request is intentionally not attempted. A preference may
become searchable only after the extraction delay and is normally demonstrated
in a subsequent conversation or session.

Memory failures, a missing `AGENTCORE_MEMORY_ID`, a resource still being
created, and a failed or timed-out readiness check are silent to the user. The
runtime continues with a direct chat response, and a later invocation may
retry Memory readiness.

To demonstrate the path in an authorized environment:

1. In one authenticated session, say a durable preference explicitly, for
   example: “Prefiro respostas curtas e em português.”
2. Wait for asynchronous extraction; do not expect the preference immediately
   in the same response.
3. Start a new session for the same user and ask a related question. The
   runtime should retrieve a bounded preference record and use it as
   explicitly untrusted personalization context for the direct response.
4. Repeat with the second test user. Their actor-scoped namespace must not
   retrieve the first user's preference.

The Memory API uses the control-plane `bedrock-agentcore-control` client for
readiness checks and the data-plane `bedrock-agentcore` client for events and
records. See the [official Memory SDK guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-sdk-memory.html)
and [namespace guidance](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/specify-long-term-memory-organization.html)
for the service-level contracts.

Relevant service limits include a 33-character minimum runtime session ID,
100 MB invocation payloads, 10 MB streaming chunks, and up to 1,000 active
sessions in `us-east-1` (subject to account quotas). This stack keeps Memory
events for 90 days and caps persisted skill Markdown at 64 KiB. See the
[AgentCore quotas](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
and [Runtime configuration reference](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime.html)
for current service limits.

Persisted skills are instructions only. The only accepted skill file is
`skills/<name>/SKILL.md`, where `<name>` is a bounded opaque-safe directory
name and the Markdown is valid bounded UTF-8 text. Python, shell, binary, and
other files are ignored; Markdown is inserted into a clearly delimited prompt
section and is never imported or executed.

Run the smoke check with short-lived access tokens obtained through the
authorized Cognito flow (the script reports status codes and delta counts, not
token values):

```bash
WEB_API_URL='https://<api-id>.execute-api.<region>.amazonaws.com/prod' \
TOKEN_USER_A='<access-token-a>' \
TOKEN_USER_B='<access-token-b>' \
TOKEN_NO_SCOPE='<access-token-without-chat-send>' \
./scripts/verify_web_chat.sh
```

Expected results:

- no `Authorization` header → `401`;
- a valid token without `chat/send` → `403`;
- each valid user receives `message.started`, one or more incremental
  `message.delta` events, and `message.completed`;
- the two users map to different opaque session keys.

Every response includes an `X-Request-Id`. Use that value to find the
corresponding `/aws/lambda/hermes-agentcore-web-chat` log stream. Logs contain
request metadata and safe error details only; they must not contain raw
messages, prompts, model output, Cognito subjects, or bearer tokens.

## Rollback and teardown

To roll back only the application artifact, redeploy the previous image and
runtime environment with the normal CDK deployment flow; keep the immutable
Guardrail version and Memory ID unchanged. To remove the experiment, preview
the stack order first and then use the teardown below. The retained S3 bucket
and Cognito pool are deliberate recovery points and must be removed separately
only under explicit account change control.

Preview the complete stack order before making changes:

```bash
./scripts/teardown.sh --dry-run
```

When the demonstration is complete, run the interactive teardown (or
`--force` only under the account's change-control policy):

```bash
./scripts/teardown.sh
```

The destroyable web bucket, CloudFront distribution, API, Lambda, and Hosted UI
resources are removed with `hermes-agentcore-web`. The Cognito user pool is
retained so it can be reused by the web application. The teardown does not
manage any Knowledge Base or vector-store resources because the simplified
deployment does not create them. It does not print document contents, tokens,
or credentials. The web-only deployment does not create a dedicated KMS key or
channel secrets.
