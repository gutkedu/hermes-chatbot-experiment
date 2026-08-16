import { requirePrincipal } from './auth.mjs';
import { invokeAgentCore, parseAgentCoreStream } from './agentcore.mjs';
import { HttpError } from './errors.mjs';
import { parseChatRequest } from './request.mjs';
import { deriveAgentCoreIdentity } from './session.mjs';
import { encodeSse } from './sse.mjs';

function corsHeaders(env) {
  return {
    'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN,
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  };
}

function jsonResponse(statusCode, value, env, requestId) {
  return {
    statusCode,
    headers: {
      ...corsHeaders(env),
      'Content-Type': 'application/json; charset=utf-8',
      'X-Request-Id': requestId,
    },
    body: JSON.stringify(value),
  };
}

function errorResponse(error, env, requestId) {
  const statusCode = error instanceof HttpError ? error.statusCode : 500;
  const message = error instanceof HttpError && statusCode < 500
    ? error.message
    : 'The chat service is temporarily unavailable';
  return jsonResponse(statusCode, { error: message, requestId }, env, requestId);
}

function claimsFromEvent(event) {
  return event?.requestContext?.authorizer?.claims
    ?? event?.requestContext?.authorizer
    ?? {};
}

function methodFromEvent(event) {
  return event.httpMethod ?? event.requestContext?.http?.method ?? 'GET';
}

async function* chatBody({ client, env, requestId, message, principal }) {
  yield encodeSse('message.started', { requestId });
  try {
    const identity = deriveAgentCoreIdentity(principal);
    const output = await invokeAgentCore(client, {
      agentRuntimeArn: env.AGENTCORE_RUNTIME_ARN,
      qualifier: env.AGENTCORE_QUALIFIER,
      runtimeSessionId: identity.runtimeSessionId,
      runtimeUserId: identity.runtimeUserId,
      payload: {
        action: 'chat',
        channel: 'web',
        message,
        userId: identity.runtimeUserId,
      },
    });
    for await (const event of parseAgentCoreStream(
      output.response ?? output.body,
      output.contentType ?? '',
    )) {
      if (typeof event === 'string' && event) yield encodeSse('message.delta', { text: event });
      if (event.type === 'delta' && event.text) yield encodeSse('message.delta', { text: event.text });
      if (event.type === 'sources' && Array.isArray(event.sources)) {
        const sources = event.sources.slice(0, 3).map((source) => ({
          title: String(source.title ?? ''), identifier: String(source.identifier ?? ''), excerpt: String(source.excerpt ?? ''),
        }));
        yield encodeSse('message.sources', { sources });
      }
    }
    yield encodeSse('message.completed', { requestId });
  } catch (error) {
    yield encodeSse('error', {
      message: 'The agent could not finish this response. Please try again.',
      retryable: true,
      requestId,
    });
  }
}

export async function routeRequest(event, { client, env, requestId }) {
  const path = event.path ?? event.resource ?? event.rawPath ?? '';
  const method = methodFromEvent(event).toUpperCase();

  if (path === '/config' && method === 'GET') {
    return jsonResponse(200, {
      region: env.AWS_REGION,
      userPoolId: env.USER_POOL_ID,
      userPoolClientId: env.USER_POOL_CLIENT_ID,
      cognitoDomain: env.COGNITO_DOMAIN,
      redirectUri: env.WEB_REDIRECT_URI,
      scope: 'openid email chat/send',
    }, env, requestId);
  }

  if (path !== '/chat') return jsonResponse(404, { error: 'Not found', requestId }, env, requestId);
  if (method === 'OPTIONS') {
    return { statusCode: 204, headers: corsHeaders(env), body: '' };
  }
  if (method !== 'POST') return jsonResponse(405, { error: 'Method not allowed', requestId }, env, requestId);

  try {
    const principal = requirePrincipal(claimsFromEvent(event));
    const { message } = parseChatRequest(event.body, event.isBase64Encoded);
    return {
      statusCode: 200,
      headers: {
        ...corsHeaders(env),
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Request-Id': requestId,
      },
      body: chatBody({ client, env, requestId, message, principal }),
    };
  } catch (error) {
    return errorResponse(error, env, requestId);
  }
}
