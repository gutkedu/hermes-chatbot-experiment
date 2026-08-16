export const initialState = {
  status: 'signed_out',
  accessToken: null,
  messages: [],
  pendingMessage: null,
  error: null,
};

export function reduce(state, action) {
  switch (action.type) {
    case 'SIGNED_IN':
      return { ...state, status: 'ready', accessToken: action.token, error: null };
    case 'SIGNED_OUT':
      return { ...initialState };
    case 'SEND_STARTED':
      return {
        ...state,
        status: 'sending',
        pendingMessage: action.message,
        error: null,
        messages: [
          ...state.messages,
          { role: 'user', text: action.message },
          { role: 'assistant', text: '' },
        ],
      };
    case 'DELTA': {
      const messages = state.messages.slice();
      const last = messages[messages.length - 1];
      if (!last || last.role !== 'assistant') return state;
      messages[messages.length - 1] = { ...last, text: last.text + action.text };
      return { ...state, status: 'streaming', messages };
    }
    case 'SOURCES': {
      const messages = state.messages.slice();
      const last = messages[messages.length - 1];
      if (!last || last.role !== 'assistant') return state;
      messages[messages.length - 1] = { ...last, sources: action.sources.slice(0, 3) };
      return { ...state, messages };
    }
    case 'COMPLETED':
      return { ...state, status: 'ready', pendingMessage: null };
    case 'FAILED':
      if (action.statusCode === 401) return { ...state, ...initialState };
      return { ...state, status: 'error', error: action.message };
    case 'RETRY': {
      if (!state.pendingMessage) return state;
      const messages = state.messages.slice();
      const last = messages[messages.length - 1];
      if (last?.role === 'assistant') messages[messages.length - 1] = { ...last, text: '' };
      return { ...state, status: 'sending', error: null, messages };
    }
    default:
      return state;
  }
}
