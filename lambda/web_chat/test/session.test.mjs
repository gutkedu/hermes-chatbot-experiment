import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

import { deriveAgentCoreIdentity } from '../src/session.mjs';

test('same identity maps to stable opaque identifiers', () => {
  const a = deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' });
  assert.deepEqual(a, deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' }));
  assert.match(a.runtimeSessionId, /^web-session-[a-f0-9]{64}$/);
  assert.match(a.runtimeUserId, /^web-user-[a-f0-9]{64}$/);
  assert.match(a.workspaceNamespace, /^ws-[a-f0-9]{64}$/);
});

test('workspace namespace is bound to the derived runtime session', () => {
  const identity = deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' });
  assert.equal(
    identity.workspaceNamespace,
    `ws-${createHash('sha256').update(identity.runtimeSessionId, 'utf8').digest('hex')}`,
  );
});

test('different identities cannot share the derived session', () => {
  assert.notEqual(
    deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u1' }).runtimeSessionId,
    deriveAgentCoreIdentity({ issuer: 'issuer', subject: 'u2' }).runtimeSessionId,
  );
});
