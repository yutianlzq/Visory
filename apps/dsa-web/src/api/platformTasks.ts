import apiClient from './index';
import { formatPlatformError } from './platformErrors';
import type { PlatformListEnvelope, PlatformSuccessEnvelope, PublicTaskDetails, PublicTaskDetailsResponse, TaskListQuery, TaskRecord } from '../types/generated/platform-api';

type ListParams = Partial<Omit<TaskListQuery, 'tab'>> & { tab?: TaskListQuery['tab'] };


/** Format C-010 task errors without exposing server diagnostics or secrets. */
export function formatPlatformTaskError(cause: unknown, fallback: string): string {
  return formatPlatformError(cause, fallback);
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
  get: async (taskId: string): Promise<PublicTaskDetails> => {
    const response = await apiClient.get<PublicTaskDetailsResponse>(`/api/platform/v1/tasks/${encodeURIComponent(taskId)}`);
    return response.data.data;
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
