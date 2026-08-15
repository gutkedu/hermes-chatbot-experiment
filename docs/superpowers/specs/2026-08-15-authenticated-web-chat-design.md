# Authenticated Web Chat Design

## Goal

Deliver the first complete browser journey for Hermes: a customer signs in with Amazon Cognito, sends one message at a time, and receives the response progressively from Amazon Bedrock AgentCore Runtime through an authenticated backend-for-frontend (BFF). The browser never receives AWS credentials, and the BFF never accepts a client-selected AgentCore session identifier.

RAG, conversation selection, anonymous access, account self-registration, and production rollout automation are outside this slice.

## Architecture

```text
Browser
  -> CloudFront + private S3 web assets
  -> Cognito Hosted UI (authorization code + PKCE)
  -> Regional API Gateway REST API (Cognito authorizer, STREAM transfer mode)
  -> Node.js Lambda BFF (native response streaming)
  -> Bedrock AgentCore InvokeAgentRuntime
  -> Hermes Agent async stream
```

The public API is an API Gateway REST API because its proxy integrations support streamed responses through `ResponseTransferMode: STREAM`. The BFF runs on the managed Node.js Lambda runtime and uses `awslambda.streamifyResponse()` to write Server-Sent Events (SSE) as AgentCore produces output. CloudFront serves only the static browser application; the browser calls the Regional API directly with CORS enabled.

The existing webhook router remains unchanged. The web journey gets a dedicated stack and Lambda so its Cognito, authorization, and streaming contracts do not become coupled to channel-specific webhook behavior.

## Authentication and authorization

The security stack continues to own the Cognito user pool. The web stack adds:

- a Cognito domain;
- a resource server with the `chat/send` scope;
- a public user-pool client with no secret, authorization-code grant, PKCE, and only the minimum OpenID scopes plus `chat/send`;
- CloudFront callback and logout URLs; and
- a Cognito authorizer on `POST /chat` requiring `chat/send`.

The browser redirects to the Hosted UI, creates a PKCE verifier/challenge with Web Crypto, exchanges the callback code for tokens, and keeps tokens in `sessionStorage`. It sends an access token in `Authorization: Bearer ...`; it never calls Cognito Identity Pools or receives IAM credentials.

API Gateway returns `401` for missing, malformed, expired, wrong-issuer, or wrong-client tokens. A valid Cognito token without `chat/send` returns `403`. The Lambda also checks the expected scope and required `sub` claim before invoking AgentCore so the BFF's authorization rule remains independently testable.

## Session isolation

`POST /chat` accepts exactly one product field:

```json
{"message":"How do I reset the product?"}
```

The BFF rejects an empty/non-string message, a message over 8,000 characters, and any `sessionId` field. It derives both AgentCore identifiers from authenticated claims:

```text
principal = SHA-256("<iss>\n<sub>")
runtimeSessionId = "web-session-" + principal
runtimeUserId = "web-user-" + principal
```

The hash is deterministic for repeat turns by one Cognito identity, opaque in logs and AgentCore metadata, and different for any two identities. One stable session per identity implements the issue's "one conversation at a time" constraint. The browser cannot override or continue another identity's session.

The AgentCore payload is limited to `action`, `channel`, `message`, and the derived opaque `userId`. Tokens, raw Cognito subjects, and client-provided identifiers are never forwarded.

## Streaming contract

Successful responses use `Content-Type: text/event-stream`, disable intermediary caching, and emit UTF-8 SSE records in this order:

```text
event: message.started
data: {"requestId":"<correlation-id>"}

event: message.delta
data: {"text":"partial text"}

event: message.completed
data: {"requestId":"<correlation-id>"}
```

The BFF consumes AgentCore's streaming body incrementally. AgentCore `data:` chunks become `message.delta` events without being accumulated in Lambda. If AgentCore returns its JSON fallback, the BFF emits its response as one delta followed by completion. Empty keep-alive lines are ignored.

The Hermes AgentCore entrypoint moves the synchronous `run_conversation()` call to a worker thread, bridges Hermes's `stream_callback` into an async queue, and yields each callback delta from the existing `BedrockAgentCoreApp` async generator. If Hermes produces no callback deltas, it yields the final response once as a compatibility fallback; if it streamed deltas, it does not duplicate the final response.

Failures before SSE headers are sent use JSON HTTP responses. Failures after streaming starts use:

```text
event: error
data: {"message":"A recoverable user-safe message","retryable":true,"requestId":"<correlation-id>"}
```

Logs include the correlation ID and opaque principal but exclude authorization headers, tokens, raw Cognito subjects, prompts, and response text.

## Browser behavior

The browser application is framework-free HTML, CSS, and JavaScript to keep the slice small. It loads non-secret deployment configuration from public `GET /config`, handles the Hosted UI redirect, and parses the `fetch()` response stream because native `EventSource` cannot send a POST body or bearer header.

The UI state machine has these visible states:

- signed out: sign-in action only;
- ready: message input and send action;
- sending: submitted user message shown and controls disabled;
- response in progress: assistant bubble grows with each delta;
- recoverable error: error copy, correlation ID, and retry action;
- expired session: local tokens cleared and sign-in shown again.

Retry resends the same message once the user requests it, uses the same derived session, and reuses the pending assistant bubble so the UI does not duplicate the user message.

## Infrastructure and permissions

The web stack provisions the private S3 site bucket, Origin Access Control, CloudFront distribution, Cognito web client/domain/resource server, Regional REST API, streaming BFF Lambda, log group, and outputs for the site and API URLs. The API exposes unauthenticated `GET /config`, authenticated `POST /chat`, and CORS preflight.

The Lambda role can invoke only the configured AgentCore runtime ARN and qualified runtime resources, and write its own logs. It has no permission to administer Cognito or assume customer credentials. The S3 bucket blocks public access and is readable only through CloudFront.

Deployment remains phased: the AgentCore runtime is deployed first, then the web stack receives its ARN/qualifier through CDK context. The deploy script installs the locked BFF dependencies and prints the web URL. Teardown destroys the web stack and explicitly removes retained web resources where applicable. The README documents account creation by an operator, deploy, two-user isolation verification, and teardown.

## Testing and acceptance

Node contract tests cover request validation, missing/invalid identity, `403` scope enforcement, deterministic session derivation, cross-identity isolation, AgentCore payload construction, SSE event ordering, incremental forwarding, JSON fallback, and recoverable errors. Browser tests cover PKCE/token handling, streaming UI transitions, retry without duplicate user messages, and forced sign-out on `401`.

Python tests cover Hermes callback-to-async-generator bridging, compatibility fallback, error propagation, and no duplicated final response. CDK assertions cover Cognito resources, the scoped authorizer, REST API `STREAM` transfer mode, least-privilege AgentCore permission, private site bucket, and expected outputs.

The repository verifier runs all Python, BFF Node, browser, AgentCore CDK, build, and synth checks without AWS credentials. The authorized-environment runbook demonstrates sign-in and streaming, verifies `401` and `403`, compares derived sessions for two users without exposing their subjects, and records teardown commands. Actual AWS deployment requires an authorized environment and is not performed implicitly.
