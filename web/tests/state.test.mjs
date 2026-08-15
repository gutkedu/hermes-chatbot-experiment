import test from 'node:test';
import assert from 'node:assert/strict';

import { initialState, reduce } from '../src/state.mjs';

test('chat state transitions from signed out to ready after sign-in', () => {
  const state = reduce(initialState, { type: 'SIGNED_IN', token: 'token' });
  assert.equal(state.status, 'ready');
  assert.equal(state.accessToken, 'token');
});

test('deltas append to one assistant message without duplicating the user message', () => {
  let state = reduce({ ...initialState, status: 'ready', accessToken: 'token' }, {
    type: 'SEND_STARTED', message: 'hello',
  });
  state = reduce(state, { type: 'DELTA', text: 'Hel' });
  state = reduce(state, { type: 'DELTA', text: 'lo' });
  state = reduce(state, { type: 'COMPLETED' });
  assert.equal(state.status, 'ready');
  assert.deepEqual(state.messages, [
    { role: 'user', text: 'hello' },
    { role: 'assistant', text: 'Hello' },
  ]);
});

test('sources attach to the active assistant message', () => {
  let state = reduce({ ...initialState, status: 'ready', accessToken: 'token' }, {
    type: 'SEND_STARTED', message: 'return policy',
  });
  state = reduce(state, { type: 'SOURCES', sources: [{ title: 'Lumen', identifier: 'lumen.md', excerpt: '30 dias' }] });
  assert.deepEqual(state.messages[1].sources, [{ title: 'Lumen', identifier: 'lumen.md', excerpt: '30 dias' }]);
});

test('401 signs out and retry reuses the pending message', () => {
  let state = reduce({ ...initialState, status: 'ready', accessToken: 'token' }, {
    type: 'SEND_STARTED', message: 'retry me',
  });
  state = reduce(state, { type: 'FAILED', statusCode: 401, message: 'expired' });
  assert.equal(state.status, 'signed_out');
  state = reduce({ ...state, accessToken: 'token', status: 'ready', messages: [
    { role: 'user', text: 'retry me' }, { role: 'assistant', text: '' },
  ], pendingMessage: 'retry me' }, { type: 'RETRY' });
  assert.equal(state.status, 'sending');
  assert.equal(state.messages.length, 2);
  assert.equal(state.pendingMessage, 'retry me');
});
