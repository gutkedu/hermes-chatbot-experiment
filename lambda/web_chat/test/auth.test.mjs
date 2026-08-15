import test from 'node:test';
import assert from 'node:assert/strict';

import { requirePrincipal } from '../src/auth.mjs';

test('missing claims are a 401', () => {
  assert.throws(() => requirePrincipal({}), { statusCode: 401 });
});

test('valid claims without chat/send are a 403', () => {
  assert.throws(
    () => requirePrincipal({ iss: 'issuer', sub: 'u1', scope: 'openid' }),
    { statusCode: 403 },
  );
});

test('claims with chat/send produce a principal', () => {
  assert.deepEqual(
    requirePrincipal({ iss: 'issuer', sub: 'u1', scope: 'openid chat/send' }),
    { issuer: 'issuer', subject: 'u1' },
  );
});
