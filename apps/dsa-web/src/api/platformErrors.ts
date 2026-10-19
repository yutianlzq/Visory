function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

const PRIVATE_TEXT = /(?:bearer\s+|(?:api[_ +-]?key|authorization|cookie|password|passwd|secret|credentials?|token|lease)["']?\s*[:=]|https?:\/\/[^\s/@]+:[^\s/@]+@|(?:postgres(?:ql)?|mysql|redis|mongodb)(?:\+[a-z0-9]+)?:\/\/|(?<![a-z0-9])[a-z]:[\\/]|\\\\[a-z0-9_.-]+[\\/]|file:\/\/|(?<![a-z0-9_./-])\/(?!api(?:\/|(?=$|[\s"'?#)\]}])))[a-z0-9_.-]+|traceback|stack\s*trace|(?:response[_ ]?(?:body|text)|raw[_ ]?(?:body|payload|text))["']?\s*[:=]|\beyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+|\b(?:sk-[a-z0-9_-]{16,}|xox[baprs]-[a-z0-9-]{16,}|gh[pousr]_[a-z0-9_]{20,})\b)/i;
const JSON_ESCAPE = /\\(?:u([0-9a-fA-F]{4})|(["\\/bfnrt]))/g;
const PERCENT_ESCAPE = /%([0-9a-fA-F]{2})/g;
const JSON_CHARACTERS: Record<string, string> = {
  '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t',
};

function isPrivateText(text: string): boolean {
  // 与 Python 公共边界共享语料；只检查解码视图，原消息保持不变。
  for (let depth = 0; depth < 8; depth += 1) {
    if (PRIVATE_TEXT.test(text)) return true;
    let decoded = text.replace(JSON_ESCAPE, (_match, hex: string | undefined, character: string) => (
      hex ? String.fromCharCode(parseInt(hex, 16)) : JSON_CHARACTERS[character]
    ));
    decoded = decoded.replace(PERCENT_ESCAPE, (_match, hex: string) => String.fromCharCode(parseInt(hex, 16)));
    if (decoded === text) return false;
    text = decoded;
  }
  return true;
}

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
    message: message && message.length <= 240 && !isPrivateText(message) ? message : undefined,
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
