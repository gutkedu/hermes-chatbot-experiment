import test from 'node:test';
import assert from 'node:assert/strict';

import { parseChatRequest } from '../src/request.mjs';

test('chat requests accept only a non-empty bounded message', () => {
  assert.deepEqual(parseChatRequest('{"message":"hello"}'), { message: 'hello' });
  assert.throws(() => parseChatRequest('{"message":""}'), { statusCode: 400 });
  assert.throws(
    () => parseChatRequest('{"message":"hello","sessionId":"x"}'),
    { statusCode: 400 },
  );
});

test('base64 encoded chat request is decoded before validation', () => {
  const encoded = Buffer.from('{"message":"hello"}').toString('base64');
  assert.deepEqual(parseChatRequest(encoded, true), { message: 'hello' });
});

test('oversized messages are rejected', () => {
  assert.throws(() => parseChatRequest(JSON.stringify({ message: 'x'.repeat(8001) })), {
    statusCode: 400,
  });
});
