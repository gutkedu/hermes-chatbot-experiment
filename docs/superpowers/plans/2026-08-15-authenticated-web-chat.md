# Authenticated Web Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first authenticated browser conversation through Cognito, a streaming API Gateway REST API/Lambda BFF, and Hermes on Bedrock AgentCore Runtime, with reproducible CDK, contract tests, and an AWS runbook.

**Architecture:** Add a dedicated Node.js 22 streaming BFF Lambda and a dedicated `HermesWebStack`. API Gateway is a Regional REST API defined by OpenAPI so its Lambda proxy integration uses the `2021-11-15/.../response-streaming-invocations` URI and `responseTransferMode: STREAM`. Cognito authorizes `POST /chat` with the `chat/send` scope; the BFF performs defense-in-depth claim checks and derives an opaque deterministic AgentCore session from `iss` and `sub`. CloudFront/S3 serves a framework-free browser app, whose deployment writes a non-secret API bootstrap asset.

**Tech Stack:** Python 3.10+ CDK (`aws-cdk-lib==2.265.0`), Node.js 22 Lambda with `@aws-sdk/client-bedrock-agentcore==3.1111.0`, Node built-in test runner, browser ESM/CSS/HTML, Python `pytest`, and the existing AgentCore `BedrockAgentCoreApp`.

---

## File map

Create the BFF under `lambda/web_chat/` so it is independently testable and packaged by CDK:

- `lambda/web_chat/package.json`, `package-lock.json`: pinned runtime dependency and test script.
- `lambda/web_chat/src/errors.mjs`, `auth.mjs`, `request.mjs`, `session.mjs`, `agentcore.mjs`, `sse.mjs`, `route.mjs`: pure BFF contracts.
- `lambda/web_chat/index.mjs`: Lambda streaming adapter using `awslambda.streamifyResponse()` and `HttpResponseStream.from()`.
- `lambda/web_chat/test/*.test.mjs`: authentication, authorization, request, session, AgentCore, SSE, and route contract tests.

Create the browser under `web/`:

- `web/index.html`, `styles.css`, `src/auth.mjs`, `src/sse.mjs`, `src/state.mjs`, `app.mjs`: static UI and testable browser modules.
- `web/tests/*.test.mjs`: PKCE, SSE parser, and UI state-machine tests.

Create infrastructure and its assertions:

- `stacks/web_stack.py`: Cognito resource server/client/domain, private S3 + CloudFront, streaming REST API, Lambda, IAM, CORS, outputs.
- `tests/test_web_stack.py`: CDK template assertions, including the streaming integration URI and auth scope.

Modify:

- `stacks/security_stack.py`: leave the user pool in the security stack but move the web OAuth client to `HermesWebStack` so callback URLs can use the CloudFront domain.
- `app.py`: instantiate the web stack after security and AgentCore stacks.
- `bridge/streaming.py`, `app/hermes/bridge/streaming.py`, `app/hermes/main.py`: callback-to-async-generator bridge and AgentCore payload streaming.
- `scripts/verify.sh`, `scripts/deploy.sh`, `scripts/teardown.sh`, `README.md`: dependency/test/deploy/teardown instructions.
- `package.json`: root `test:bff` and `test:web` scripts.

Before every commit, run:

```bash
rtk pwd
rtk git remote get-url origin
rtk git config --local --get user.name
rtk git config --local --get user.email
```

The expected identity is `Eduardo P Gutkoski <eduardo.pedogutkoski@gmail.com>` and the remote must be `git@github.com:gutkedu/hermes-chatbot-experiment.git`.

## Task 1: Scaffold the BFF contracts and prove authentication/session behavior

**Files:**

- Create: `lambda/web_chat/package.json`
- Create: `lambda/web_chat/src/errors.mjs`
- Create: `lambda/web_chat/src/auth.mjs`
- Create: `lambda/web_chat/src/request.mjs`
- Create: `lambda/web_chat/src/session.mjs`
- Test: `lambda/web_chat/test/auth.test.mjs`, `request.test.mjs`, `session.test.mjs`

- [ ] **Step 1: Add the pinned BFF package manifest**

Create `lambda/web_chat/package.json`:

```json
{
  "name": "hermes-web-chat-bff",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22" },
  "dependencies": {
    "@aws-sdk/client-bedrock-agentcore": "3.1111.0"
  },
  "scripts": {
    "test": "node --test test/*.test.mjs"
  }
}
```

Run `rtk npm install --prefix lambda/web_chat --package-lock-only` and confirm a lockfile is created without adding `node_modules` to Git.

- [ ] **Step 2: Write failing authentication and request tests**

Add tests that establish the public contract:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { requirePrincipal } from '../src/auth.mjs';
import { parseChatRequest } from '../src/request.mjs';

test('missing claims are a 401', () => {
  assert.throws(() => requirePrincipal({}), { statusCode: 401 });
});

test('valid claims without chat/send are a 403', () => {
  assert.throws(
    () => requirePrincipal({ iss: 'issuer', sub: 'u1', scope: 'openid' }),
    { statusCode: 403 },
  );
});

test('claims with chat/send produce a principal', () => {
  assert.deepEqual(
    requirePrincipal({ iss: 'issuer', sub: 'u1', scope: 'openid chat/send' }),
    { issuer: 'issuer', subject: 'u1' },
  );
});

test('chat requests accept only a non-empty bounded message', () => {
  assert.deepEqual(parseChatRequest('{"message":"hello"}'), { message: 'hello' });
  assert.throws(() => parseChatRequest('{"message":""}'), { statusCode: 400 });
  assert.throws(() => parseChatRequest('{"message":"hello","sessionId":"x"}'), { statusCode: 400 });
});
```

Run `rtk npm --prefix lambda/web_chat test`; expect module-not-found failures because the modules do not exist yet.

- [ ] **Step 3: Implement the minimal error/auth/request modules**

Implement `HttpError(statusCode, message, retryable=false)` in `errors.mjs`. Implement `requirePrincipal(claims, requiredScope='chat/send')` to require string `iss` and `sub`, return `401` when either is absent, split the space-delimited `scope` claim, and return `403` when the required scope is absent. Implement `parseChatRequest(rawBody, isBase64Encoded=false)` to decode the API Gateway base64 flag, require a JSON object with exactly the `message` key, require a trimmed string, and cap it at 8,000 UTF-16 code units.

- [ ] **Step 4: Write the failing session tests**

```js
import { deriveAgentCoreIdentity } from '../src/session.mjs';

test('same identity maps to stable opaque identifiers', () => {
  const a = deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' });
  assert.equal(a, deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' }));
  assert.match(a.runtimeSessionId, /^web-session-[a-f0-9]{64}$/);
  assert.match(a.runtimeUserId, /^web-user-[a-f0-9]{64}$/);
});

test('different identities cannot share the derived session', () => {
  assert.notEqual(
    deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' }).runtimeSessionId,
    deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u2' }).runtimeSessionId,
  );
});
```

Run the focused test and confirm the expected missing-module failure.

- [ ] **Step 5: Implement deterministic session derivation**

Use `node:crypto` SHA-256 over `${issuer}\n${subject}` and return `{ runtimeSessionId: 'web-session-' + digest, runtimeUserId: 'web-user-' + digest }`. Do not include a client-provided value in the hash or accept a `sessionId` argument.

- [ ] **Step 6: Run the green contract tests and commit**

Run `rtk npm --prefix lambda/web_chat test`. Expected: all authentication, request, and session tests pass. Verify Git identity/remote using the pre-commit commands above, then commit:

```bash
rtk git add lambda/web_chat/package.json lambda/web_chat/package-lock.json lambda/web_chat/src lambda/web_chat/test
rtk git commit -m "feat: add web chat auth and session contracts"
```

## Task 2: Add AgentCore streaming normalization and the Lambda route contract

**Files:**

- Create: `lambda/web_chat/src/agentcore.mjs`, `sse.mjs`, `route.mjs`, `index.mjs`
- Test: `lambda/web_chat/test/agentcore.test.mjs`, `sse.test.mjs`, `route.test.mjs`

- [ ] **Step 1: Write failing SSE and AgentCore tests**

Cover these exact cases:

```js
test('SSE encoder emits event and JSON data with a blank terminator', () => {
  assert.equal(encodeSse('message.delta', { text: 'hi' }),
    'event: message.delta\ndata: {"text":"hi"}\n\n');
});

test('AgentCore event-stream data lines become text deltas without buffering', async () => {
  const body = Readable.from([
    Buffer.from('data: "Hel"\n\n'),
    Buffer.from('data: "lo"\n\n'),
  ]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'text/event-stream')), ['Hel', 'lo']);
});

test('JSON AgentCore fallback yields one response', async () => {
  const body = Readable.from([Buffer.from('{"response":"complete"}')]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'application/json')), ['complete']);
});
```

Add route tests for a valid chat event producing `message.started`, two `message.delta` events, and `message.completed`; a missing identity producing a JSON 401 before the stream; a valid request with AgentCore throwing after the first delta producing an SSE `error`; and `GET /config` returning only public deployment configuration.

Run the BFF tests and confirm they fail because the streaming modules are absent.

- [ ] **Step 2: Implement SSE and AgentCore parsing**

`encodeSse(event, data)` must JSON-stringify data and append exactly two newlines. `parseAgentCoreStream(body, contentType)` must iterate the SDK body asynchronously. For `text/event-stream`, maintain only an incomplete line buffer, ignore blank/comment lines, parse each `data:` value, unwrap JSON strings, and yield text from strings or `{text}`/`{response}` objects. For other content types, collect the bounded fallback body, parse JSON, and yield `response` or `text`; malformed data must raise an `HttpError(502, 'Agent response was invalid', true)`.

`invokeAgentCore(client, input)` must send `InvokeAgentRuntimeCommand({ agentRuntimeArn, runtimeSessionId, runtimeUserId, qualifier, payload })` with the payload encoded as UTF-8 JSON and return the SDK output. It must never read a session ID from the request body.

- [ ] **Step 3: Implement the pure route generator**

`routeRequest(event, { client, env, requestId })` must:

1. Return a JSON `GET /config` response containing `region`, `userPoolId`, `userPoolClientId`, `cognitoDomain`, `redirectUri`, and `scope`.
2. For `POST /chat`, read claims from `event.requestContext.authorizer.claims`, call `requirePrincipal`, parse the body, derive the opaque identity, and construct `{ action: 'chat', channel: 'web', message, userId: runtimeUserId }`.
3. Return an async SSE body that emits `message.started`, forwards every normalized AgentCore text chunk as `message.delta`, then emits `message.completed`.
4. Convert pre-stream `HttpError`s to JSON with CORS headers and convert post-start failures to one `error` SSE event containing only a safe message, `retryable`, and `requestId`.
5. Set `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, and `X-Request-Id` on successful chat responses.

Use the environment names `AGENTCORE_RUNTIME_ARN`, `AGENTCORE_QUALIFIER`, `AWS_REGION`, `USER_POOL_ID`, `USER_POOL_CLIENT_ID`, `COGNITO_DOMAIN`, `WEB_REDIRECT_URI`, and `ALLOWED_ORIGIN`.

- [ ] **Step 4: Implement the Lambda streaming adapter**

Export `handler = awslambda.streamifyResponse(async (event, responseStream) => { ... })`. Call `routeRequest`, wrap the writable with `awslambda.HttpResponseStream.from(responseStream, { statusCode, headers })`, write JSON bodies or each async SSE chunk, and always call `.end()`. Use a dependency factory that constructs `BedrockAgentCoreClient({})` once per warm invocation. Do not log tokens, raw claims, messages, or AgentCore payloads.

- [ ] **Step 5: Run green BFF tests and commit**

Run `rtk npm --prefix lambda/web_chat test`; expected: all auth/request/session, SSE/AgentCore, and route tests pass. Commit with:

```bash
rtk git add lambda/web_chat/src lambda/web_chat/test
rtk git commit -m "feat: stream AgentCore responses through web BFF"
```

## Task 3: Make the Hermes AgentCore entrypoint produce real deltas

**Files:**

- Create/modify: `bridge/streaming.py`, `app/hermes/bridge/streaming.py`, `app/hermes/main.py`
- Test: `tests/test_streaming.py`

- [ ] **Step 1: Write failing Python tests**

Add a fake synchronous agent whose `run_conversation(..., stream_callback=callback)` calls `callback('Hel')`, `callback('lo')`, and returns `{'final_response': 'Hello'}`. Test that `stream_conversation()` yields `['Hel', 'lo']` and does not duplicate `Hello`. Add a second fake that never calls the callback and returns `{'final_response': 'fallback'}`; assert one fallback yield. Add a third fake that raises and assert the async generator raises the original exception.

Run `rtk python3 -m pytest tests/test_streaming.py -q`; expected: import/function failures.

- [ ] **Step 2: Implement the callback bridge**

Implement `async def stream_conversation(agent, **kwargs)` using an `asyncio.Queue`, `asyncio.to_thread`, and a sentinel. The worker calls `agent.run_conversation(**kwargs, stream_callback=emit)`, where `emit` schedules queue writes on the event loop. Track whether any non-empty delta was emitted; after the worker completes, yield `final_response` only when no deltas were emitted. Propagate worker exceptions after draining the sentinel. Keep the helper free of AWS imports.

- [ ] **Step 3: Use the bridge in AgentCore**

In `app/hermes/main.py`, replace the synchronous `run_conversation()` call in `invoke()` with:

```python
async for delta in stream_conversation(
    agent,
    user_message=message,
    system_message=system_extra,
    conversation_history=history,
):
    yield delta
```

Copy the helper into `app/hermes/bridge/streaming.py` because `scripts/deploy.sh` synchronizes `bridge/` into the AgentCore build context; keep both copies byte-identical and add a test that compares their text.

- [ ] **Step 4: Run tests and commit**

Run `rtk python3 -m pytest tests/test_streaming.py tests/test_contract.py -q`. Expected: all pass. Commit:

```bash
rtk git add bridge/streaming.py app/hermes/bridge/streaming.py app/hermes/main.py tests/test_streaming.py
rtk git commit -m "feat: stream Hermes callback deltas from AgentCore"
```

## Task 4: Build the browser auth, stream parser, and UI state machine

**Files:**

- Create: `web/index.html`, `web/styles.css`, `web/src/auth.mjs`, `web/src/sse.mjs`, `web/src/state.mjs`, `web/app.mjs`
- Test: `web/tests/auth.test.mjs`, `sse.test.mjs`, `state.test.mjs`

- [ ] **Step 1: Write failing browser-module tests**

Test that `createPkcePair()` returns a verifier and base64url SHA-256 challenge; `buildAuthorizeUrl()` includes `response_type=code`, `code_challenge_method=S256`, `client_id`, `redirect_uri`, and `scope=openid%20email%20chat%2Fsend`; `parseSse()` handles records split across arbitrary chunks; and the reducer transitions `ready -> sending -> streaming -> ready`, appending deltas without duplicating the user message. Test `401` as `signed_out` and `retry` as `sending` with the original message retained.

Run `rtk npm run test:web`; expect missing-module failures.

- [ ] **Step 2: Implement PKCE and token handling**

`auth.mjs` must use `crypto.subtle.digest('SHA-256', ...)`, base64url without padding, `sessionStorage` keys `hermes.pkce.verifier` and `hermes.tokens`, and `fetch()` to Cognito’s `/oauth2/token` endpoint with `grant_type=authorization_code`. Never persist a client secret. Clear storage on token errors or API 401.

- [ ] **Step 3: Implement the SSE parser and reducer**

`parseSse(chunks)` must buffer until `\n\n`, parse `event:` and `data:` lines, JSON-decode data, and yield `{ event, data }`. `state.mjs` must expose pure `initialState`, `reduce`, and action names `SIGNED_IN`, `SEND_STARTED`, `DELTA`, `COMPLETED`, `FAILED`, `RETRY`, `SIGNED_OUT`.

- [ ] **Step 4: Implement the static chat screen**

`index.html` must contain a sign-in button, sign-out button, status region with `aria-live="polite"`, message list, textarea, send button, retry button, and an error region. `app.mjs` must load `runtime-config.js`, exchange the callback code, call `POST ${apiBaseUrl}/chat` with the access token, consume `response.body.getReader()`, dispatch SSE events, and show a recoverable retry action. It must disable send while a request is active, preserve one assistant bubble during deltas, and redirect to sign-in when the token expires.

- [ ] **Step 5: Run browser tests and commit**

Run `rtk npm run test:web`; expected: all pure browser tests pass. Commit:

```bash
rtk git add web
rtk git commit -m "feat: add Cognito chat browser experience"
```

## Task 5: Provision Cognito, API Gateway streaming, Lambda permissions, and static hosting

**Files:**

- Create: `stacks/web_stack.py`, `tests/test_web_stack.py`
- Modify: `stacks/security_stack.py`, `app.py`

- [ ] **Step 1: Write failing CDK assertions**

Instantiate the new stack with a test user pool and a non-empty runtime ARN. Assert:

```python
template.has_resource_properties(
    "AWS::Cognito::UserPoolResourceServer",
    Match.object_like({"Scopes": Match.array_with([Match.object_like({"ScopeName": "send"})])}),
)
assert any(
    "response-streaming-invocations" in json.dumps(resource)
    and '"responseTransferMode": "STREAM"' in json.dumps(resource)
    for resource in template.find_resources("AWS::ApiGateway::RestApi").values()
)
template.has_resource_properties(
    "AWS::IAM::Policy",
    Match.serialized_json(Match.string_like_regexp(".*bedrock-agentcore:InvokeAgentRuntime.*")),
)
```

Also assert a Cognito authorizer with the user-pool ARN, `chat/send` in the OpenAPI security requirement, a private S3 bucket, a CloudFront distribution, and the `SiteUrl`, `ApiUrl`, and `UserPoolClientId` outputs. Run the focused test and confirm it fails because the stack is absent.

- [ ] **Step 2: Implement `HermesWebStack` static hosting**

Create a destroyable, versioned S3 site bucket with `BLOCK_ALL` public access and CloudFront Origin Access Control using `S3BucketOrigin.with_origin_access_control`. Create a CloudFront distribution with `web/` as its default root object, HTTPS redirect, compression disabled for the streaming API (the API is a separate origin), and a short cache policy for static assets. Add `BucketDeployment` for `index.html`, `styles.css`, `app.mjs`, `src/*`, and a generated `runtime-config.js` containing only the API base URL.

- [ ] **Step 3: Implement Cognito web resources**

Create `CfnUserPoolDomain` with a deterministic prefix `hermes-agentcore-${account}-${region}`; create `CfnUserPoolResourceServer` with identifier `chat` and scope name `send`; create a public `CfnUserPoolClient` with code grant, PKCE-compatible no-secret settings, callback/logout URL `https://${distribution.domain_name}/`, supported provider `COGNITO`, and allowed scopes `openid`, `email`, and `chat/send`. Keep the user pool itself in `HermesSecurityStack`; remove its unused default client and client output.

- [ ] **Step 4: Implement the streaming REST API definition**

Define an OpenAPI 3 body in `CfnRestApi` with Regional endpoint configuration and paths `/chat` and `/config`. Both proxy integrations point to:

```text
arn:${AWS::Partition}:apigateway:${AWS::Region}:lambda:path/2021-11-15/functions/${WebChatFnArn}/response-streaming-invocations
```

Set `responseTransferMode: STREAM`, `timeoutInMillis: 900000`, and `type: aws_proxy`. `/chat` uses the Cognito authorizer and security scope `chat/send`; `/config` is public. Add an unauthenticated OPTIONS mock for `/chat` returning `Access-Control-Allow-Origin: https://${distribution.domain_name}`, allowed headers `Authorization,Content-Type`, and allowed method `POST`. Add `AWS::ApiGateway::GatewayResponse` resources for `DEFAULT_4XX` and `UNAUTHORIZED` so API Gateway’s 401/403 responses include the same CORS headers.

- [ ] **Step 5: Implement the Node Lambda and least-privilege IAM**

Create a Node.js 22 Lambda from `lambda/web_chat`, timeout 900 seconds, memory 512 MiB, environment variables from the design, and a one-month log retention group. Grant the function only `bedrock-agentcore:InvokeAgentRuntime` and `bedrock-agentcore:InvokeAgentRuntimeForUser` on `${runtimeArn}` and `${runtimeArn}/*`. Add a Lambda resource permission for `apigateway.amazonaws.com` to invoke the function. Make the API depend on the permission and deployment.

- [ ] **Step 6: Wire the stack into the CDK app and run assertions**

Instantiate `HermesWebStack` after `HermesSecurityStack` and `HermesAgentCoreStack`, pass the runtime ARN/qualifier from context, and add dependencies on those stacks. Run `rtk python3 -m pytest tests/test_web_stack.py -q`; expected: all assertions pass. Commit:

```bash
rtk git add stacks/web_stack.py stacks/security_stack.py app.py tests/test_web_stack.py
rtk git commit -m "feat: provision authenticated streaming web API"
```

## Task 6: Integrate verification, deployment, teardown, and runbook

**Files:**

- Modify: root `package.json`, `scripts/verify.sh`, `scripts/deploy.sh`, `scripts/teardown.sh`, `README.md`
- Create: `docs/authenticated-web-chat-runbook.md`, `scripts/verify_web_chat.sh`

- [ ] **Step 1: Add repeatable local commands**

Add root scripts:

```json
"test:bff": "npm --prefix lambda/web_chat test",
"test:web": "node --test web/tests/*.test.mjs"
```

Update `scripts/verify.sh` to run `npm ci --prefix lambda/web_chat`, `npm run test:bff`, `npm run test:web`, Python tests, AgentCore CDK tests/build, and `cdk synth`. Keep all checks local and credential-free.

- [ ] **Step 2: Extend deployment**

Add `hermes-agentcore-web` to the existing phase-3 CDK deploy command alongside the router, cron, and token-monitoring stacks. Ensure `npm ci --omit=dev --prefix lambda/web_chat` runs before CDK asset staging. Print the CloudFormation `SiteUrl`, `ApiUrl`, Cognito domain, and client ID. Never generate or commit tokens, account IDs, `aws-targets.json`, or local runtime state.

- [ ] **Step 3: Extend teardown safely**

Destroy `hermes-agentcore-web` before security resources. The web bucket is destroyable by CDK; the retained Cognito user pool remains listed for explicit operator deletion. Add the web stack to the dry-run inventory and to the force teardown order without broad recursive deletion.

- [ ] **Step 4: Add the authorized-environment runbook and smoke script**

Document operator steps to create two Cognito users, deploy Phase 1/AgentCore/web, open the CloudFront URL, sign in, send a message, observe incremental `message.delta` records, and inspect CloudWatch by `X-Request-Id`. Document checks for missing token (`401`), valid token without `chat/send` (`403`), two users producing distinct opaque session keys in logs, and `scripts/teardown.sh --dry-run`/`--force`.

`scripts/verify_web_chat.sh` must accept `WEB_API_URL`, `TOKEN_USER_A`, `TOKEN_USER_B`, and `TOKEN_NO_SCOPE`; perform the 401/403 checks and two authenticated `curl --no-buffer` calls, but never print token values. It must state that AgentCore deployment and credentials are prerequisites.

- [ ] **Step 5: Run the complete local verification and commit**

Run:

```bash
rtk bash scripts/verify.sh
rtk bash scripts/verify_web_chat.sh --help
rtk bash scripts/teardown.sh --dry-run
```

Expected: all local tests, TypeScript tests/build, CDK synth, smoke-script help, and teardown dry-run pass without AWS resource mutation. Commit:

```bash
rtk git add package.json scripts README.md docs/authenticated-web-chat-runbook.md scripts/verify_web_chat.sh
rtk git commit -m "docs: document authenticated web chat deployment"
```

## Final self-review checklist

- [ ] Every issue acceptance criterion maps to a test, CDK assertion, browser behavior, or runbook step.
- [ ] `POST /chat` accepts no client session identifier and derives both AgentCore identifiers from authenticated claims.
- [ ] Missing/invalid identity is 401; valid identity without `chat/send` is 403; API Gateway authorizer and BFF checks agree.
- [ ] API Gateway uses the streaming Lambda URI and `responseTransferMode: STREAM`; Lambda emits the required metadata delimiter through `HttpResponseStream.from()`.
- [ ] AgentCore streams callback deltas and does not duplicate a final response.
- [ ] The browser visibly handles signed-out, sending, streaming, recoverable-error, retry, and expired-session states.
- [ ] No AWS credentials, tokens, raw Cognito subjects, prompts, or response text are logged or committed.
- [ ] The verifier does not deploy; the runbook and optional smoke script cover the authorized AWS demonstration and teardown.
