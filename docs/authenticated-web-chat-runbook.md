# Authenticated web chat runbook

This runbook is for an AWS account where the operator is authorized to create
and remove Cognito, CloudFront, S3, API Gateway, Lambda, and AgentCore
resources. The local verifier is credential-free; the smoke test below is the
authorized-environment check.

## Deploy

1. Install the prerequisites from `README.md`, configure AWS credentials, and
   choose a region. Set `project_name`, `agentcore_runtime_arn`, and
   `agentcore_qualifier` in `cdk.json` (the normal path is
   `./scripts/deploy.sh`, which obtains the runtime values during Phase 2).
2. Deploy the foundation and runtime:

   ```bash
   ./scripts/deploy.sh phase1
   ./scripts/deploy.sh phase2
   ./scripts/deploy.sh phase3
   ```

   Phase 3 deploys the `hermes-agentcore-web` stack alongside the existing
   channel stacks. It prints the CloudFront site URL, streaming API URL,
   Cognito domain, and public web client ID.
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
resources are removed with `hermes-agentcore-web`. The Cognito user pool and
foundation KMS resources use `RETAIN`; delete those explicitly only after
confirming that no other environment uses them.
