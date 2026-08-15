import test from 'node:test';
import assert from 'node:assert/strict';

import { buildAuthorizeUrl, createPkcePair, loadTokens, storeTokens } from '../src/auth.mjs';

test('PKCE pair contains a verifier and a base64url SHA-256 challenge', async () => {
  const pair = await createPkcePair();
  assert.match(pair.verifier, /^[A-Za-z0-9_-]+$/);
  assert.match(pair.challenge, /^[A-Za-z0-9_-]+$/);
  assert.ok(pair.verifier.length >= 43);
  assert.equal(pair.challenge.length, 43);
});

test('authorize URL contains the Cognito code-flow parameters', () => {
  const url = new URL(buildAuthorizeUrl({
    cognitoDomain: 'https://hermes.auth.us-east-1.amazoncognito.com',
    userPoolClientId: 'client',
    redirectUri: 'https://example.cloudfront.net/',
    scope: 'openid email chat/send',
  }, 'state', 'challenge'));
  assert.equal(url.searchParams.get('response_type'), 'code');
  assert.equal(url.searchParams.get('client_id'), 'client');
  assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
  assert.equal(url.searchParams.get('code_challenge'), 'challenge');
  assert.equal(url.searchParams.get('scope'), 'openid email chat/send');
});

test('tokens round-trip through session storage', () => {
  const storage = new Map();
  storage.set = storage.set.bind(storage);
  storage.getItem = (key) => storage.get(key) ?? null;
  storage.setItem = (key, value) => storage.set(key, value);
  storage.removeItem = (key) => storage.delete(key);
  storeTokens(storage, { access_token: 'token', expires_in: 3600 });
  assert.deepEqual(loadTokens(storage), { access_token: 'token', expires_in: 3600 });
});
