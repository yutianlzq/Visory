function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

const PRIVATE_TEXT = /(?:bearer\s+|(?:authorization|cookie|password|passwd|secret|credential|token|lease)["']?\s*[:=]|https?:\/\/[^\s/@]+:[^\s/@]+@|(?:postgres(?:ql)?|mysql|redis|mongodb)(?:\+[a-z0-9]+)?:\/\/|[a-z]:[\\/]|\\\\|file:\/\/|(?:^|\s)\/(?!api(?:\/|$))[a-z0-9_.-]+\/|traceback|stack\s*trace|response[_ ]?(?:body|text)\s*[:=]|\beyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+)/i;

export function projectPlatformError(cause: unknown) {
  if (!isRecord(cause)) return undefined;
  const response = isRecord(cause.response) ? cause.response : undefined;
  const data = response && isRecord(response.data) ? response.data : undefined;
  const error = data && isRecord(data.error) ? data.error : undefined;
  if (!error || typeof error.code !== 'string' || !/^[A-Z][A-Z0-9_]{2,79}$/.test(error.code)) {
    return undefined;
  }
  const message = typeof error.message === 'string' ? error.message.trim() : '';
  return {
    code: error.code,
    message: message && message.length <= 240 && !PRIVATE_TEXT.test(message) ? message : undefined,
    retryable: error.retryable === true,
    requestId: typeof error.request_id === 'string' && /^req_[0-9a-f]{32}$/.test(error.request_id)
      ? error.request_id : undefined,
  };
}

export function formatPlatformError(cause: unknown, fallback: string): string {
  const error = projectPlatformError(cause);
  if (!error) return fallback;
  return `${error.code}: ${error.message ?? fallback}${error.requestId ? ` (Request ID: ${error.requestId})` : ''}`;
}
