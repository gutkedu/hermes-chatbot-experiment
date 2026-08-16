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
