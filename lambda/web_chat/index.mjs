import { BedrockAgentCoreClient } from '@aws-sdk/client-bedrock-agentcore';

import { routeRequest } from './src/route.mjs';

const client = new BedrockAgentCoreClient({});

export const handler = awslambda.streamifyResponse(async (event, responseStream) => {
  const requestId = event?.headers?.['x-request-id'] ?? crypto.randomUUID();
  const result = await routeRequest({ ...event, path: event.path ?? event.rawPath }, {
    client,
    env: process.env,
    requestId,
  });
  const stream = awslambda.HttpResponseStream.from(responseStream, {
    statusCode: result.statusCode,
    headers: result.headers,
  });
  if (typeof result.body === 'string') {
    stream.write(result.body);
  } else {
    for await (const chunk of result.body) stream.write(chunk);
  }
  stream.end();
});
