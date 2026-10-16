import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import OperationsTasksPage from '../OperationsTasksPage';
import type { TaskDetails } from '../../types/generated/platform-api';

const { list, get } = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn() }));

vi.mock('../../api/platformTasks', async () => {
  const actual = await vi.importActual<typeof import('../../api/platformTasks')>('../../api/platformTasks');
  return { ...actual, platformTasksApi: { list, get, cancel: vi.fn(), retry: vi.fn() } };
});

const requestId = 'req_0123456789abcdef0123456789abcdef';
const failure = { response: { data: { error: {
  code: 'BACKFILL_SOURCE_UNAVAILABLE', message: 'token=fixture-secret', retryable: true, request_id: requestId,
} } } };

function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => { resolve = onResolve; reject = onReject; });
  return { promise, resolve, reject };
}

const sources: QuietEventSource[] = [];
class QuietEventSource {
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  private listeners = new Map<string, () => void>();
  constructor() { sources.push(this); }
  addEventListener(event: string, handler: () => void) { this.listeners.set(event, handler); }
  emit() { this.listeners.get('task_state_changed')?.(); }
  close() {}
}

const emptyList = { items: [], nextCursor: null, hasMore: false };
const olderFailure = { response: { data: { error: {
  code: 'BACKFILL_OLD_TASK_UNAVAILABLE', message: 'lease=fixture-secret', request_id: `req_${'a'.repeat(32)}`,
} } } };

function mount(initialPath = '/operations/tasks/task_browser_counterexample') {
  render(<MemoryRouter initialEntries={[initialPath]}>
    <Link to="/operations/tasks">退出详情</Link>
    <Link to="/operations/tasks/task_current">切换详情</Link>
    <Routes><Route path="/operations/tasks/:taskId?" element={<OperationsTasksPage />} /></Routes>
  </MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  sources.length = 0;
  vi.stubGlobal('EventSource', QuietEventSource);
  list.mockResolvedValue(emptyList);
  get.mockRejectedValue(failure);
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('Operations task error ownership', () => {
  it('keeps the newest diagnostic when SSE refreshes the same task before an older request fails', async () => {
    const older = deferred();
    get.mockReturnValueOnce(older.promise).mockRejectedValue(failure);
    mount();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    act(() => sources.at(-1)?.emit());
    expect(await screen.findByRole('alert')).toHaveTextContent(requestId);
    await act(async () => { older.reject(olderFailure); await older.promise.catch(() => undefined); });
    expect(screen.getByRole('alert')).toHaveTextContent(requestId);
    expect(screen.getByRole('alert')).not.toHaveTextContent('BACKFILL_OLD_TASK_UNAVAILABLE');
  });

  it('keeps the newest list result when SSE refreshes the same filters before an older request fails', async () => {
    const older = deferred();
    list.mockReturnValueOnce(older.promise).mockResolvedValue(emptyList);
    mount('/operations/tasks');
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    act(() => sources.at(-1)?.emit());
    await screen.findByText('当前筛选下暂无任务');
    await act(async () => { older.reject(olderFailure); await older.promise.catch(() => undefined); });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('clears a current detail diagnostic after a successful refresh using the existing Golden contract', async () => {
    mount();
    await screen.findByRole('alert');
    // 通过 Vitest 的 Node 环境读取权威 Golden，避免向浏览器源码注入全局 Node 类型。
    const { readFileSync } = await vi.importActual<{ readFileSync(path: URL, encoding: 'utf8'): string }>('node:fs');
    const { URL: NodeURL } = await vi.importActual<{ URL: new (path: string, base: string) => URL }>('node:url');
    const goldenDetailsText = readFileSync(new NodeURL('../../../../../tests/golden/platform/contracts/success/task-details.json', import.meta.url), 'utf8');
    const payload = (JSON.parse(goldenDetailsText) as { payload: TaskDetails }).payload;
    get.mockResolvedValue({ ...payload, task: { ...payload.task, task_id: 'task_browser_counterexample' } });
    act(() => sources.at(-1)?.emit());
    await screen.findByRole('heading', { name: payload.task.task_type });
    expect(screen.getByText('状态', { selector: 'span' }).nextElementSibling).toHaveTextContent(payload.task.task_state);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('ignores an old task failure after a newer task has returned its diagnostic', async () => {
    const older = deferred();
    get.mockImplementation((id: string) => id === 'task_current' ? Promise.reject(failure) : older.promise);
    mount();
    await waitFor(() => expect(get).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('link', { name: '切换详情' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(requestId);
    await act(async () => { older.reject(olderFailure); await older.promise.catch(() => undefined); });
    expect(screen.getByRole('alert')).toHaveTextContent(requestId);
    expect(screen.getByRole('alert')).not.toHaveTextContent('BACKFILL_OLD_TASK_UNAVAILABLE');
  });

  it('ignores a pending detail failure after leaving the detail route', async () => {
    const older = deferred();
    get.mockReturnValue(older.promise);
    mount();
    await waitFor(() => expect(get).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('link', { name: '退出详情' }));
    await screen.findByText('选择一个任务查看详情');
    await act(async () => { older.reject(olderFailure); await older.promise.catch(() => undefined); });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('ignores an older filter response after the current list query succeeds', async () => {
    const older = deferred();
    list.mockImplementation((query: { task_type?: string }) => query.task_type ? Promise.resolve(emptyList) : older.promise);
    mount('/operations/tasks');
    await waitFor(() => expect(list).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox', { name: '任务类型' }), { target: { value: 'raw_fetch' } });
    await screen.findByText('当前筛选下暂无任务');
    await act(async () => { older.reject(olderFailure); await older.promise.catch(() => undefined); });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('当前筛选下暂无任务')).toBeInTheDocument();
  });

  it('does not mark a disconnected SSE connection healthy after a successful list read', async () => {
    const pending = deferred<typeof emptyList>();
    list.mockReturnValue(pending.promise);
    mount('/operations/tasks');
    await waitFor(() => expect(sources.length).toBeGreaterThan(0));
    act(() => sources.at(-1)?.onerror?.());
    expect(screen.getByRole('status')).toHaveTextContent('实时连接断开');
    await act(async () => { pending.resolve(emptyList); await pending.promise; });
    expect(screen.getByRole('status')).toHaveTextContent('实时连接断开');
  });

  it('keeps a replacement event stream disconnected until its own open event', async () => {
    mount('/operations/tasks');
    await waitFor(() => expect(sources.length).toBeGreaterThan(0));
    act(() => sources.at(-1)?.onopen?.());
    expect(screen.getByRole('status')).toHaveTextContent('实时事件已连接');
    const streamCount = sources.length;
    fireEvent.change(screen.getByRole('textbox', { name: '任务类型' }), { target: { value: 'raw_fetch' } });
    await waitFor(() => expect(sources.length).toBeGreaterThan(streamCount));
    expect(screen.getByRole('status')).toHaveTextContent('实时连接断开');
    act(() => sources.at(-1)?.onopen?.());
    expect(screen.getByRole('status')).toHaveTextContent('实时事件已连接');
  });

  it('shows an unavailable detail state rather than a permanent loading skeleton after failure', async () => {
    mount();
    await screen.findByRole('alert');
    expect(screen.getByText('任务详情不可用，请依据公开错误和 Request ID 核验后重试。')).toBeInTheDocument();
  });

  it.each(['filter', 'tab'] as const)('retains a redacted detail error after a successful list %s refresh', async (trigger) => {
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent(requestId);
    const callsBefore = list.mock.calls.length;
    if (trigger === 'filter') fireEvent.change(screen.getByRole('textbox', { name: '任务类型' }), { target: { value: 'raw_fetch' } });
    else fireEvent.click(screen.getByRole('tab', { name: /历史/ }));
    await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(callsBefore));
    await waitFor(() => expect(screen.queryByText('当前筛选下暂无任务')).toBeInTheDocument());
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('BACKFILL_SOURCE_UNAVAILABLE');
    expect(alert).toHaveTextContent(requestId);
    expect(alert).not.toHaveTextContent('fixture-secret');
  });

  it('clears the old detail error when navigating back to the task list', async () => {
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent(requestId);
    fireEvent.click(screen.getByRole('link', { name: '退出详情' }));
    await screen.findByText('选择一个任务查看详情');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
