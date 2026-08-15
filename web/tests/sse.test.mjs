import test from 'node:test';
import assert from 'node:assert/strict';

import { parseSse } from '../src/sse.mjs';

async function* chunks(values) {
  for (const value of values) yield value;
}

test('SSE parser handles records split across arbitrary chunks', async () => {
  const events = [];
  for await (const event of parseSse(chunks([
    'event: message.del',
    'ta\ndata: {"text":"Hel"}\n\n',
    'event: message.completed\ndata: {"requestId":"r1"}\n\n',
  ]))) events.push(event);
  assert.deepEqual(events, [
    { event: 'message.delta', data: { text: 'Hel' } },
    { event: 'message.completed', data: { requestId: 'r1' } },
  ]);
});
