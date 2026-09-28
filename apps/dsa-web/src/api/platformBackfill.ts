import apiClient from './index';
import type { BackfillBatchProjection, PlatformListEnvelope, PlatformSuccessEnvelope } from '../types/generated/platform-api';

function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null; }

const SENSITIVE_PUBLIC_TEXT = /(?:bearer\s+|authorization\s*[:=]|cookie\s*[:=]|(?:password|passwd|secret|credential|token)\s*[:=]|(?:[a-z]:\\|\\\\|file:\/\/|\/(?:home|tmp|var|data|workspace|private)\/))/i;
const PUBLIC_ERROR_CODE = /^[A-Z][A-Z0-9_]{2,79}$/;

function projectSafePublicError(code: unknown, message: unknown): string | undefined {
  if (typeof code !== 'string' || !PUBLIC_ERROR_CODE.test(code)) return undefined;
  if (typeof message !== 'string') return undefined;
  const normalized = message.trim();
  if (!normalized || normalized.length > 240 || SENSITIVE_PUBLIC_TEXT.test(normalized)) return undefined;
  return `${code}: ${normalized}`;
}

export function formatBackfillError(cause: unknown, fallback = '历史回填服务不可用'): string {
  if (isRecord(cause)) {
    const response = isRecord(cause.response) ? cause.response : undefined;
    const payload = response && isRecord(response.data) ? response.data : undefined;
    const error = payload && isRecord(payload.error) ? payload.error : undefined;
    const projected = projectSafePublicError(error?.code, error?.message);
    if (projected) return projected;
  }
  return fallback;
}

export const platformBackfillApi = {
  list: async (): Promise<{ items: BackfillBatchProjection[]; hasMore: boolean }> => {
    const response = await apiClient.get<PlatformListEnvelope>('/api/platform/v1/backfills', { params: { limit: 50 } });
    return { items: response.data.data as unknown as BackfillBatchProjection[], hasMore: response.data.page.has_more };
  },
  get: async (batchId: string): Promise<BackfillBatchProjection> => {
    const response = await apiClient.get<PlatformSuccessEnvelope>(`/api/platform/v1/backfills/${encodeURIComponent(batchId)}`);
    return response.data.data as unknown as BackfillBatchProjection;
  },
};
