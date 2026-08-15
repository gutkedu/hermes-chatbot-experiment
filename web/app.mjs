import {
  buildAuthorizeUrl,
  clearTokens,
  createPkcePair,
  exchangeCode,
  loadPkceVerifier,
  loadTokens,
  storePkceVerifier,
  storeTokens,
} from './src/auth.mjs';
import { shouldSubmitOnEnter } from './src/keyboard.mjs';
import { parseSse } from './src/sse.mjs';
import { initialState, reduce } from './src/state.mjs';

const storage = window.sessionStorage;
const apiBaseUrl = window.HERMES_API_BASE;
const elements = {
  signIn: document.querySelector('#sign-in'),
  signOut: document.querySelector('#sign-out'),
  status: document.querySelector('#status'),
  messages: document.querySelector('#messages'),
  form: document.querySelector('#chat-form'),
  input: document.querySelector('#message'),
  send: document.querySelector('#send'),
  retry: document.querySelector('#retry'),
  error: document.querySelector('#error'),
};

let config;
let state = initialState;

function dispatch(action) {
  state = reduce(state, action);
  render();
}

function render() {
  const signedIn = state.status !== 'signed_out';
  const active = state.status === 'sending' || state.status === 'streaming';
  elements.signIn.hidden = signedIn;
  elements.signOut.hidden = !signedIn;
  elements.form.hidden = !signedIn;
  elements.send.disabled = active;
  elements.input.disabled = active;
  elements.retry.hidden = state.status !== 'error' || !state.pendingMessage;
  elements.status.textContent = state.status === 'signed_out'
    ? 'Sign in to start a conversation.'
    : state.status === 'sending'
      ? 'Sending…'
      : state.status === 'streaming'
        ? 'Hermes is responding…'
        : 'You are signed in.';
  elements.error.textContent = state.error ?? '';
  elements.messages.replaceChildren(...state.messages.map((message) => {
    const node = document.createElement('div');
    node.className = `message message-${message.role}`;
    const text = document.createElement('div');
    text.textContent = message.text;
    node.append(text);
    if (message.role === 'assistant' && message.sources?.length) {
      const sources = document.createElement('ul');
      sources.className = 'sources';
      for (const source of message.sources) {
        const item = document.createElement('li');
        item.textContent = `${source.title}: ${source.excerpt}`;
        sources.append(item);
      }
      node.append(sources);
    }
    return node;
  }));
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function randomState() {
  return crypto.randomUUID();
}

async function signIn() {
  const pair = await createPkcePair();
  storePkceVerifier(storage, pair.verifier);
  storage.setItem('hermes.pkce.state', randomState());
  const stateValue = storage.getItem('hermes.pkce.state');
  window.location.assign(buildAuthorizeUrl(config, stateValue, pair.challenge));
}

async function completeSignIn() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  if (!code) return false;
  if (params.get('state') !== storage.getItem('hermes.pkce.state')) throw new Error('Invalid sign-in state');
  const verifier = loadPkceVerifier(storage);
  if (!verifier) throw new Error('Missing sign-in verifier');
  storeTokens(storage, await exchangeCode(config, code, verifier));
  window.history.replaceState({}, '', window.location.pathname);
  return true;
}

async function* responseChunks(reader) {
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    yield decoder.decode(value, { stream: true });
  }
}

async function sendMessage(message, retry = false) {
  if (retry) dispatch({ type: 'RETRY' });
  else dispatch({ type: 'SEND_STARTED', message });
  const tokens = loadTokens(storage);
  try {
    const response = await fetch(`${apiBaseUrl}/chat`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    });
    if (response.status === 401) {
      clearTokens(storage);
      dispatch({ type: 'FAILED', statusCode: 401, message: 'Your sign-in expired.' });
      return;
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      dispatch({ type: 'FAILED', statusCode: response.status, message: payload.error ?? 'Try again.' });
      return;
    }
    for await (const event of parseSse(responseChunks(response.body.getReader()))) {
      if (event.event === 'message.delta') dispatch({ type: 'DELTA', text: event.data.text ?? '' });
      if (event.event === 'message.sources') dispatch({ type: 'SOURCES', sources: event.data.sources ?? [] });
      if (event.event === 'message.completed') dispatch({ type: 'COMPLETED' });
      if (event.event === 'error') dispatch({ type: 'FAILED', message: event.data.message ?? 'Try again.' });
    }
  } catch {
    dispatch({ type: 'FAILED', message: 'The service could not be reached. Try again.' });
  }
}

elements.signIn.addEventListener('click', () => signIn().catch((error) => dispatch({ type: 'FAILED', message: error.message })));
elements.signOut.addEventListener('click', () => { clearTokens(storage); dispatch({ type: 'SIGNED_OUT' }); });
elements.form.addEventListener('submit', (event) => {
  event.preventDefault();
  const message = elements.input.value.trim();
  if (!message || state.status === 'sending' || state.status === 'streaming') return;
  elements.input.value = '';
  sendMessage(message);
});
elements.input.addEventListener('keydown', (event) => {
  if (!shouldSubmitOnEnter(event)) return;
  event.preventDefault();
  elements.form.requestSubmit();
});
elements.retry.addEventListener('click', () => sendMessage(state.pendingMessage, true));

async function start() {
  if (!apiBaseUrl) throw new Error('Missing API configuration');
  const configResponse = await fetch(`${apiBaseUrl}/config`);
  if (!configResponse.ok) throw new Error('Could not load deployment configuration');
  config = await configResponse.json();
  const exchanged = await completeSignIn();
  const tokens = loadTokens(storage);
  if (exchanged || tokens?.access_token) dispatch({ type: 'SIGNED_IN', token: tokens.access_token });
  else dispatch({ type: 'SIGNED_OUT' });
}

start().catch((error) => dispatch({ type: 'FAILED', message: error.message }));
