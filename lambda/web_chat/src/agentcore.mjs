import { InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore';

import { HttpError } from './errors.mjs';

const MAX_FALLBACK_BYTES = 10 * 1024 * 1024;

async function* byteChunks(body) {
  if (body && typeof body[Symbol.asyncIterator] === 'function') {
    for await (const chunk of body) yield chunk;
    return;
  }
  if (body && typeof body.getReader === 'function') {
    const reader = body.getReader();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) return;
        yield value;
      }
    } finally {
      reader.releaseLock?.();
    }
  }
}

function decodeData(value) {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function textFromData(value) {
  if (typeof value === 'string') return value;
  if (value && typeof value.text === 'string') return value.text;
  if (value && typeof value.response === 'string') return value.response;
  return '';
}

export async function* parseAgentCoreStream(body, contentType = '') {
  if (!body) throw new HttpError(502, 'Agent response was empty', true);

  if (contentType.toLowerCase().includes('text/event-stream')) {
    const decoder = new TextDecoder();
    let pending = '';
    for await (const chunk of byteChunks(body)) {
      pending += decoder.decode(chunk, { stream: true });
      const lines = pending.split(/\r?\n/);
      pending = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const text = textFromData(decodeData(line.slice(5).trim()));
        if (text) yield text;
      }
    }
    pending += decoder.decode();
    if (pending.startsWith('data:')) {
      const text = textFromData(decodeData(pending.slice(5).trim()));
      if (text) yield text;
    }
    return;
  }

  const chunks = [];
  let total = 0;
  for await (const chunk of byteChunks(body)) {
    const buffer = Buffer.from(chunk);
    total += buffer.length;
    if (total > MAX_FALLBACK_BYTES) {
      throw new HttpError(502, 'Agent response was too large', true);
    }
    chunks.push(buffer);
  }
  try {
    const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const text = textFromData(parsed?.response ?? parsed?.text ?? parsed);
    if (text) yield text;
  } catch {
    throw new HttpError(502, 'Agent response was invalid', true);
  }
}

export async function invokeAgentCore(client, input) {
  const commandInput = {
    agentRuntimeArn: input.agentRuntimeArn,
    runtimeSessionId: input.runtimeSessionId,
    runtimeUserId: input.runtimeUserId,
    payload: Buffer.from(JSON.stringify(input.payload), 'utf8'),
  };
  if (input.qualifier) commandInput.qualifier = input.qualifier;
  return client.send(new InvokeAgentRuntimeCommand(commandInput));
}
