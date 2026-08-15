import { createHash } from 'node:crypto';

export function deriveAgentCoreIdentity({ issuer, subject }) {
  const digest = createHash('sha256')
    .update(`${issuer}\n${subject}`, 'utf8')
    .digest('hex');
  return {
    runtimeSessionId: `web-session-${digest}`,
    runtimeUserId: `web-user-${digest}`,
  };
}
