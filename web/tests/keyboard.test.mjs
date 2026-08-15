import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldSubmitOnEnter } from '../src/keyboard.mjs';

test('Enter submits the composer', () => {
  assert.equal(shouldSubmitOnEnter({ key: 'Enter', shiftKey: false }), true);
});

test('Shift Enter keeps the native textarea newline', () => {
  assert.equal(shouldSubmitOnEnter({ key: 'Enter', shiftKey: true }), false);
});

test('other keys do not submit the composer', () => {
  assert.equal(shouldSubmitOnEnter({ key: 'a', shiftKey: false }), false);
});
