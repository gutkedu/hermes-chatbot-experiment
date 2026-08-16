import { createHash } from 'node:crypto';

export function deriveAgentCoreIdentity({ issuer, subject }) {
  const digest = createHash('sha256')
    .update(`${issuer}\n${subject}`, 'utf8')
    .digest('hex');
  const runtimeSessionId = `web-session-${digest}`;
  return {
    runtimeSessionId,
    runtimeUserId: `web-user-${digest}`,
    workspaceNamespace: `ws-${createHash('sha256').update(runtimeSessionId, 'utf8').digest('hex')}`,
  };
}
