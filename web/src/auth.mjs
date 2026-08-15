const TOKEN_KEY = 'hermes.tokens';
const PKCE_VERIFIER_KEY = 'hermes.pkce.verifier';

function base64url(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function createPkcePair() {
  const verifierBytes = new Uint8Array(32);
  crypto.getRandomValues(verifierBytes);
  const verifier = base64url(verifierBytes);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

export function buildAuthorizeUrl(config, state, challenge) {
  const url = new URL(`${config.cognitoDomain.replace(/\/$/, '')}/oauth2/authorize`);
  url.search = new URLSearchParams({
    response_type: 'code',
    client_id: config.userPoolClientId,
    redirect_uri: config.redirectUri,
    scope: config.scope,
    state,
    code_challenge_method: 'S256',
    code_challenge: challenge,
  });
  return url.toString();
}

export function storePkceVerifier(storage, verifier) {
  storage.setItem(PKCE_VERIFIER_KEY, verifier);
}

export function loadPkceVerifier(storage) {
  return storage.getItem(PKCE_VERIFIER_KEY);
}

export function storeTokens(storage, tokens) {
  storage.setItem(TOKEN_KEY, JSON.stringify(tokens));
}

export function loadTokens(storage) {
  const raw = storage.getItem(TOKEN_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    storage.removeItem(TOKEN_KEY);
    return null;
  }
}

export function clearTokens(storage) {
  storage.removeItem(TOKEN_KEY);
  storage.removeItem(PKCE_VERIFIER_KEY);
}

export async function exchangeCode(config, code, verifier, fetchImpl = fetch) {
  const response = await fetchImpl(`${config.cognitoDomain.replace(/\/$/, '')}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.userPoolClientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    }),
  });
  if (!response.ok) throw new Error('Cognito token exchange failed');
  return response.json();
}
