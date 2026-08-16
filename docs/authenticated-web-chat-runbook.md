# Authenticated web chat runbook

This runbook is for an AWS account where the operator is authorized to create
and remove Cognito, CloudFront, S3, API Gateway, Lambda, AgentCore, and the
private Knowledge Base resources.
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

   Phase 2 creates the private document bucket, S3 Vectors index, Knowledge
   Base, and AgentCore runtime. It does not ingest documents automatically.
   Phase 3 deploys only the `hermes-agentcore-web` stack. It prints the
   CloudFront site URL, streaming API URL, Cognito domain, and public web
   client ID.
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

## Verify authentication and streaming

## Ingest and verify product evidence

The seed document is `knowledge-base/lumen-desk-lamp.md`. To upload a revised
version, copy it under the `knowledge-base/` prefix in the `DocumentsBucketName`
output, then deliberately start ingestion:

```bash
./scripts/ingest_knowledge_base.sh
```

After the command reports `COMPLETE`, verify retrieval without exposing the
private source object:

```bash
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id "$(aws cloudformation describe-stacks --stack-name hermes-agentcore-knowledge-base --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' --output text)" \
  --retrieval-query 'text=Qual é o prazo de devolução da luminária Lumen?' \
  --retrieval-configuration 'vectorSearchConfiguration={numberOfResults=3,overrideSearchType=SEMANTIC}'
```

The retrieved text must state “30 dias corridos após a entrega”. Then send the
same question through the authenticated chat. The assistant should state that
answer and render one citation with the document title and excerpt; it must not
expose a bucket URL or download link.

The BFF derives opaque AgentCore session and user IDs from the Cognito `iss`
and `sub` claims. It never accepts a browser-provided session identifier.

## Workspace persistence and skills

When `S3_BUCKET` is configured, the BFF/router sends an internal
`workspaceNamespace` in the form `ws-<64 lowercase hex characters>`. It is
derived from the AgentCore `runtimeSessionId`; the runtime validates the
binding against `context.session_id`. The browser may send only `message` and
cannot select a session, namespace, S3 key, or skill path.

The runtime restores the namespace before retrieval or agent creation, starts
periodic saves using `WORKSPACE_SYNC_INTERVAL` (300 seconds by default), saves
after each invocation, and attempts one final synchronous save during
shutdown. Individual S3 download/upload failures are logged as safe error
types and do not stop the remaining files or the conversation. Logs never
include file contents, prompts, model output, tokens, or credentials.

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
- The Knowledge Base stores authoritative product documents and supplies the
  evidence used to answer product questions. It is not a user profile store.

Long-term extraction is asynchronous. A successful turn is written once as a
`USER` plus `ASSISTANT` event after the response stream completes, but a later
read in the same request is intentionally not attempted. A preference may
become searchable only after the extraction delay and is normally demonstrated
in a subsequent conversation or session.

Memory failures, a missing `AGENTCORE_MEMORY_ID`, a resource still being
created, and a failed or timed-out readiness check are silent to the user. The
runtime continues with the Knowledge Base and normal chat response, and a
later invocation may retry Memory readiness.

To demonstrate the path in an authorized environment:

1. In one authenticated session, say a durable preference explicitly, for
   example: “Prefiro respostas curtas e em português.”
2. Wait for asynchronous extraction; do not expect the preference immediately
   in the same response.
3. Start a new session for the same user and ask a related question. The
   runtime should retrieve a bounded preference record while continuing to
   ground product facts in the Knowledge Base.
4. Repeat with the second test user. Their actor-scoped namespace must not
   retrieve the first user's preference.

The Memory API uses the control-plane `bedrock-agentcore-control` client for
readiness checks and the data-plane `bedrock-agentcore` client for events and
records. See the [official Memory SDK guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-sdk-memory.html)
and [namespace guidance](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/specify-long-term-memory-organization.html)
for the service-level contracts.

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

## Teardown

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
retained so it can be reused by the web application. The teardown script then
deletes the retained S3 Vectors index and vector bucket in that order; it does
not print document contents, tokens, or credentials. The web-only deployment
does not create a dedicated KMS key or channel secrets.
