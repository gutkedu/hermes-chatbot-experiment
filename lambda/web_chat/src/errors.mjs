export class HttpError extends Error {
  constructor(statusCode, message, retryable = false) {
    super(message);
    this.name = 'HttpError';
    this.statusCode = statusCode;
    this.retryable = retryable;
  }
}
