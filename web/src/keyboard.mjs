export function shouldSubmitOnEnter(event) {
  return event.key === 'Enter' && !event.shiftKey;
}
