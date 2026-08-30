import apiClient from './index';
import type { PlatformListEnvelope, PlatformSuccessEnvelope, TaskDetails, TaskListQuery, TaskRecord } from '../types/generated/platform-api';

type ListParams = Partial<Omit<TaskListQuery, 'tab'>> & { tab?: TaskListQuery['tab'] };


function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** Format C-010 task errors without exposing server diagnostics or secrets. */
export function formatPlatformTaskError(cause: unknown, fallback: string): string {
  if (isRecord(cause)) {
    const response = isRecord(cause.response) ? cause.response : undefined;
    const payload = response && isRecord(response.data) ? response.data : undefined;
    const error = payload && isRecord(payload.error) ? payload.error : undefined;
    const code = error && typeof error.code === 'string' ? error.code : undefined;
    const message = error && typeof error.message === 'string' ? error.message : undefined;
    const requestId = error && typeof error.request_id === 'string' ? error.request_id : undefined;
    if (code && message && requestId) {
      return `${code}: ${message} (Request ID: ${requestId})`;
    }
  }
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
const unwrap = <T>(value: PlatformSuccessEnvelope): T => value.data as T;

export const platformTasksApi = {
  list: async (params: ListParams = {}): Promise<{ items: TaskRecord[]; nextCursor: string | null; hasMore: boolean }> => {
    const response = await apiClient.get<PlatformListEnvelope>('/api/platform/v1/tasks', { params });
    return {
      items: response.data.data as unknown as TaskRecord[],
      nextCursor: response.data.page.next_cursor,
      hasMore: response.data.page.has_more,
    };
  },
  get: async (taskId: string): Promise<TaskDetails> => {
    const response = await apiClient.get<PlatformSuccessEnvelope>(`/api/platform/v1/tasks/${encodeURIComponent(taskId)}`);
    return unwrap<TaskDetails>(response.data);
  },
  cancel: async (taskId: string): Promise<TaskRecord> => {
    const response = await apiClient.post<PlatformSuccessEnvelope>(`/api/platform/v1/tasks/${encodeURIComponent(taskId)}/cancellations`, {});
    return unwrap<TaskRecord>(response.data);
  },
  retry: async (taskId: string): Promise<TaskRecord> => {
    const response = await apiClient.post<PlatformSuccessEnvelope>(`/api/platform/v1/tasks/${encodeURIComponent(taskId)}/retries`, {});
    return unwrap<TaskRecord>(response.data);
  },
};
