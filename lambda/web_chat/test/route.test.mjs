import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';

import { routeRequest } from '../src/route.mjs';

const env = {
  AGENTCORE_RUNTIME_ARN: 'arn:aws:bedrock:us-east-1:1:agent-runtime/x',
  AGENTCORE_QUALIFIER: 'live',
  AWS_REGION: 'us-east-1',
  USER_POOL_ID: 'us-east-1_pool',
  USER_POOL_CLIENT_ID: 'client',
  COGNITO_DOMAIN: 'https://hermes.auth.us-east-1.amazoncognito.com',
  WEB_REDIRECT_URI: 'https://example.cloudfront.net/',
  ALLOWED_ORIGIN: 'https://example.cloudfront.net',
};

function event(overrides = {}) {
  return {
    path: '/chat',
    httpMethod: 'POST',
    body: JSON.stringify({ message: 'hello' }),
    isBase64Encoded: false,
    requestContext: {
      authorizer: { claims: { iss: 'issuer', sub: 'u1', scope: 'openid chat/send' } },
    },
    ...overrides,
  };
}

async function readBody(body) {
  if (typeof body === 'string') return body;
  let value = '';
  for await (const chunk of body) value += chunk;
  return value;
}

test('valid chat emits started, deltas, and completed events', async () => {
  const calls = [];
  const client = {
    send: async (command) => {
      calls.push(command);
      return {
        contentType: 'text/event-stream',
        response: Readable.from([Buffer.from('data: "Hel"\n\n'), Buffer.from('data: "lo"\n\n')]),
      };
    },
  };
  const response = await routeRequest(event(), { client, env, requestId: 'req-1' });
  const body = await readBody(response.body);
  assert.equal(response.statusCode, 200);
  assert.equal(response.headers['Content-Type'], 'text/event-stream');
  assert.match(body, /event: message.started/);
  assert.match(body, /event: message.delta\ndata: \{"text":"Hel"\}/);
  assert.match(body, /event: message.delta\ndata: \{"text":"lo"\}/);
  assert.match(body, /event: message.completed/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].input.runtimeSessionId.startsWith('web-session-'), true);
  const sentPayload = JSON.parse(Buffer.from(calls[0].input.payload).toString('utf8'));
  assert.match(sentPayload.workspaceNamespace, /^ws-[a-f0-9]{64}$/);
  assert.equal('runtimeSessionId' in sentPayload, false);
});

test('knowledge-base source envelopes become a bounded message.sources event', async () => {
  const client = { send: async () => ({
    contentType: 'text/event-stream',
    response: Readable.from([Buffer.from('data: {"type":"sources","sources":[{"title":"Lumen","identifier":"lumen.md","excerpt":"30 dias"}]}\n\n')]),
  }) };
  const response = await routeRequest(event(), { client, env, requestId: 'req-sources' });
  const body = await readBody(response.body);
  assert.match(body, /event: message.sources/);
  assert.match(body, /"title":"Lumen"/);
});

test('missing identity returns JSON 401 before streaming', async () => {
  const response = await routeRequest(event({ requestContext: {} }), {
    client: { send: async () => { throw new Error('must not invoke'); } },
    env,
    requestId: 'req-2',
  });
  assert.equal(response.statusCode, 401);
  assert.equal(JSON.parse(response.body).error, 'Authentication is required');
});

test('agent failure after a delta emits a recoverable SSE error', async () => {
  async function* broken() {
    yield Buffer.from('data: "partial"\n\n');
    throw new Error('upstream unavailable');
  }
  const response = await routeRequest(event(), {
    client: { send: async () => ({ contentType: 'text/event-stream', response: broken() }) },
    env,
    requestId: 'req-3',
  });
  const body = await readBody(response.body);
  assert.match(body, /event: message.delta/);
  assert.match(body, /event: error/);
  assert.match(body, /"retryable":true/);
  assert.doesNotMatch(body, /upstream unavailable/);
});

test('config response contains public deployment values only', async () => {
  const response = await routeRequest({ path: '/config', httpMethod: 'GET' }, {
    client: { send: async () => { throw new Error('must not invoke'); } },
    env,
    requestId: 'req-4',
  });
  assert.equal(response.statusCode, 200);
  assert.deepEqual(Object.keys(JSON.parse(response.body)).sort(), [
    'cognitoDomain', 'redirectUri', 'region', 'scope', 'userPoolClientId', 'userPoolId',
  ]);
});
