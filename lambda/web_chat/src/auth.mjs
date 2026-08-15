import { HttpError } from './errors.mjs';

export function requirePrincipal(claims, requiredScope = 'chat/send') {
  const issuer = claims?.iss;
  const subject = claims?.sub;
  if (typeof issuer !== 'string' || !issuer || typeof subject !== 'string' || !subject) {
    throw new HttpError(401, 'Authentication is required');
  }

  const scopes = new Set(String(claims.scope ?? '').split(/\s+/).filter(Boolean));
  if (!scopes.has(requiredScope)) {
    throw new HttpError(403, 'The account is not authorized for chat');
  }

  return { issuer, subject };
}
