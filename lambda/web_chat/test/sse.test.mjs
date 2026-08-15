import test from 'node:test';
import assert from 'node:assert/strict';

import { encodeSse } from '../src/sse.mjs';

test('SSE encoder emits event and JSON data with a blank terminator', () => {
  assert.equal(
    encodeSse('message.delta', { text: 'hi' }),
    'event: message.delta\ndata: {"text":"hi"}\n\n',
  );
});
