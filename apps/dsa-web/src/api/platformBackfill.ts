import apiClient from './index';
import { formatPlatformError } from './platformErrors';
import type { BackfillBatchProjection, PlatformListEnvelope, PlatformSuccessEnvelope } from '../types/generated/platform-api';

export function formatBackfillError(cause: unknown, fallback = '历史回填服务不可用'): string {
  return formatPlatformError(cause, fallback);
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
