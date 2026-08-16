import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';

import { invokeAgentCore, parseAgentCoreStream } from '../src/agentcore.mjs';

async function collect(iterable) {
  const values = [];
  for await (const value of iterable) values.push(value);
  return values;
}

test('AgentCore event-stream data lines become text deltas without buffering', async () => {
  const body = Readable.from([
    Buffer.from('data: "Hel"\n\n'),
    Buffer.from('data: "lo"\n\n'),
  ]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'text/event-stream')), ['Hel', 'lo']);
});

test('AgentCore event-stream lines split across chunks are reassembled', async () => {
  const body = Readable.from([
    Buffer.from('data: "Hel'),
    Buffer.from('lo"\n\n'),
  ]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'text/event-stream')), ['Hello']);
});

test('AgentCore JSON envelopes preserve delta and source events', async () => {
  const body = Readable.from([
    Buffer.from('data: {"type":"delta","text":"30 dias"}\n\n'),
    Buffer.from('data: {"type":"sources","sources":[{"title":"Lumen","identifier":"lumen.md","excerpt":"30 dias"}]}\n\n'),
  ]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'text/event-stream')), [
    { type: 'delta', text: '30 dias' },
    { type: 'sources', sources: [{ title: 'Lumen', identifier: 'lumen.md', excerpt: '30 dias' }] },
  ]);
});

test('quoted AgentCore JSON envelopes are decoded before routing', async () => {
  const body = Readable.from([
    Buffer.from('data: "{\\"type\\":\\"delta\\",\\"text\\":\\"30 dias\\"}"\n\n'),
    Buffer.from('data: "{\\"type\\":\\"sources\\",\\"sources\\":[{\\"title\\":\\"Lumen\\",\\"identifier\\":\\"lumen.md\\",\\"excerpt\\":\\"30 dias\\"}]}"\n\n'),
  ]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'text/event-stream')), [
    { type: 'delta', text: '30 dias' },
    { type: 'sources', sources: [{ title: 'Lumen', identifier: 'lumen.md', excerpt: '30 dias' }] },
  ]);
});

test('JSON AgentCore fallback yields one response', async () => {
  const body = Readable.from([Buffer.from('{"response":"complete"}')]);
  assert.deepEqual(await collect(parseAgentCoreStream(body, 'application/json')), ['complete']);
});

test('AgentCore invocation uses derived identifiers and encoded payload', async () => {
  let command;
  const client = { send: async (value) => { command = value; return { ok: true }; } };
  const output = await invokeAgentCore(client, {
    agentRuntimeArn: 'arn:aws:bedrock:us-east-1:1:agent-runtime/x',
    qualifier: 'live',
    runtimeSessionId: 'web-session-abc',
    runtimeUserId: 'web-user-abc',
    payload: { action: 'chat', message: 'hello' },
  });
  assert.deepEqual(output, { ok: true });
  assert.equal(command.input.runtimeSessionId, 'web-session-abc');
  assert.equal(command.input.runtimeUserId, 'web-user-abc');
  assert.equal(command.input.qualifier, 'live');
  assert.deepEqual(JSON.parse(Buffer.from(command.input.payload).toString()), {
    action: 'chat',
    message: 'hello',
  });
});
