import { HttpError } from './errors.mjs';

export function parseChatRequest(rawBody, isBase64Encoded = false) {
  let text = rawBody ?? '';
  if (isBase64Encoded) {
    try {
      text = Buffer.from(text, 'base64').toString('utf8');
    } catch {
      throw new HttpError(400, 'Request body is invalid JSON');
    }
  }

  let body;
  try {
    body = JSON.parse(text);
  } catch {
    throw new HttpError(400, 'Request body is invalid JSON');
  }

  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new HttpError(400, 'Request body must be an object');
  }
  const keys = Object.keys(body);
  if (keys.length !== 1 || keys[0] !== 'message') {
    throw new HttpError(400, 'Only message is accepted');
  }
  if (typeof body.message !== 'string' || !body.message.trim()) {
    throw new HttpError(400, 'Message must not be empty');
  }
  if (body.message.length > 8000) {
    throw new HttpError(400, 'Message is too long');
  }
  return { message: body.message.trim() };
}
