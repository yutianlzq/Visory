import apiClient from './index';
import { formatPlatformError } from './platformErrors';
import type {
  DataQualityActionRequest,
  DataQualityActionResult,
  DataQualityDiff,
  DataQualityQueryResult,
  PlatformSuccessEnvelope,
  QualityStatus,
} from '../types/generated/platform-api';

export type DataQualityParams = {
  trade_date?: string;
  snapshot_id?: string;
  capability?: string;
  dataset?: string;
  provider?: string;
  status?: QualityStatus;
};

export function formatDataQualityError(cause: unknown, fallback = '数据质量服务不可用'): string {
  return formatPlatformError(cause, fallback);
}

const unwrap = <T>(value: PlatformSuccessEnvelope): T => value.data as T;

export const platformDataQualityApi = {
  get: async (params: DataQualityParams): Promise<DataQualityQueryResult> => {
    const response = await apiClient.get<PlatformSuccessEnvelope>('/api/platform/v1/data-quality', { params });
    return unwrap<DataQualityQueryResult>(response.data);
  },
  compare: async (snapshotId: string, baseSnapshotId?: string): Promise<DataQualityDiff> => {
    const response = await apiClient.get<PlatformSuccessEnvelope>('/api/platform/v1/data-quality/compare', {
      params: { snapshot_id: snapshotId, base_snapshot_id: baseSnapshotId },
    });
    return unwrap<DataQualityDiff>(response.data);
  },
  createAction: async (
    request: DataQualityActionRequest,
    idempotencyKey: string,
  ): Promise<DataQualityActionResult> => {
    const response = await apiClient.post<PlatformSuccessEnvelope>(
      '/api/platform/v1/data-quality/actions',
      request,
      { headers: { 'Idempotency-Key': idempotencyKey } },
    );
    return unwrap<DataQualityActionResult>(response.data);
  },
};
