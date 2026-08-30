import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { platformTasksApi } from '../api/platformTasks';
import type {
  PriorityClass,
  TaskDetails,
  TaskListQuery,
  TaskRecord,
  TaskState,
} from '../types/generated/platform-api';

const TABS = ['active', 'blocked', 'failed', 'history'] as const;
type Tab = typeof TABS[number];
const terminalStates = new Set<TaskState>(['SUCCEEDED', 'DEGRADED', 'FAILED', 'CANCELLED']);
const taskStates: TaskState[] = ['ACCEPTED', 'QUEUED', 'BLOCKED', 'LEASED', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'DEGRADED', 'FAILED', 'CANCELLED'];
const priorityClasses: PriorityClass[] = ['P0_DATA_CERTIFICATION', 'P1_FORMAL_SIGNAL', 'P2_MARKET_REVIEW', 'P3_USER_INTERACTIVE', 'P4_RESEARCH', 'P5_PREVIEW_AND_MAINTENANCE'];

type FilterState = {
  taskType: string;
  taskState: TaskState | '';
  priorityClass: PriorityClass | '';
  requestedBy: string;
  createdFrom: string;
  createdTo: string;
  resourceId: string;
};


function shortId(value: string) { return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value; }
function localTime(value: string | null | undefined) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—'; }
function dateFilterToIso(value: string, endOfDay = false) {
  if (!value) return undefined;
  return new Date(`${value}T${endOfDay ? '23:59:59.999' : '00:00:00.000'}+08:00`).toISOString();
}
function readFilters(params: URLSearchParams): FilterState {
  const state = params.get('task_state');
  const priority = params.get('priority_class');
  return {
    taskType: params.get('task_type') || '',
    taskState: state && taskStates.includes(state as TaskState) ? state as TaskState : '',
    priorityClass: priority && priorityClasses.includes(priority as PriorityClass) ? priority as PriorityClass : '',
    requestedBy: params.get('requested_by') || '',
    createdFrom: params.get('created_from') || '',
    createdTo: params.get('created_to') || '',
    resourceId: params.get('resource_id') || '',
  };
}
function TimeValue({ value }: { value: string | null | undefined }) {
  if (!value) return <span>—</span>;
  return <time dateTime={value} className="block"><span>{localTime(value)}</span><span className="block text-[11px] text-muted-text">{value}</span></time>;
}

export default function OperationsTasksPage() {
  const { taskId } = useParams<{ taskId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab');
  const [tab, setTab] = useState<Tab>(TABS.includes(initialTab as Tab) ? initialTab as Tab : 'active');
  const [filters, setFilters] = useState<FilterState>(() => readFilters(searchParams));
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [details, setDetails] = useState<TaskDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState<'cancel' | 'retry' | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const nextTab = searchParams.get('tab');
    setTab(TABS.includes(nextTab as Tab) ? nextTab as Tab : 'active');
    setFilters(readFilters(searchParams));
  }, [searchParams]);

  const listQuery = useMemo<TaskListQuery>(() => ({
    tab,
    task_type: filters.taskType || undefined,
    task_state: filters.taskState || undefined,
    priority_class: filters.priorityClass || undefined,
    requested_by: filters.requestedBy || undefined,
    created_from: dateFilterToIso(filters.createdFrom),
    created_to: dateFilterToIso(filters.createdTo, true),
    resource_id: filters.resourceId || undefined,
    limit: 50,
  }), [filters, tab]);

  const loadTasks = useCallback(async () => {
    setLoading(true); setError(null);
    try { const result = await platformTasksApi.list(listQuery); setTasks(result.items); setStale(false); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '任务服务不可用'); }
    finally { setLoading(false); }
  }, [listQuery]);

  const loadDetails = useCallback(async (id: string) => {
    setDetailLoading(true);
    try { setDetails(await platformTasksApi.get(id)); setStale(false); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '任务详情不可用'); }
    finally { setDetailLoading(false); }
  }, []);

  useEffect(() => { void loadTasks(); }, [loadTasks]);
  useEffect(() => { if (taskId) void loadDetails(taskId); else setDetails(null); }, [taskId, loadDetails]);
  useEffect(() => {
    const source = new EventSource('/api/platform/v1/tasks/events', { withCredentials: true });
    const refresh = () => { setStale(false); void loadTasks(); if (taskId) void loadDetails(taskId); };
    source.addEventListener('task_state_changed', refresh);
    source.onerror = () => setStale(true);
    return () => source.close();
  }, [loadTasks, loadDetails, taskId]);
  useEffect(() => {
    if (!stale) return undefined;
    const timer = window.setInterval(() => { void loadTasks(); if (taskId) void loadDetails(taskId); }, 15000);
    return () => window.clearInterval(timer);
  }, [stale, loadTasks, loadDetails, taskId]);

  const updateQuery = (key: string, value: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (value) nextParams.set(key, value); else nextParams.delete(key);
    nextParams.delete('cursor');
    setSearchParams(nextParams);
  };
  const selectTab = (next: Tab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('tab', next); nextParams.delete('cursor'); setSearchParams(nextParams);
  };
  const selectTask = (id: string) => {
    const nextParams = new URLSearchParams(searchParams); nextParams.set('tab', tab);
    navigate(`/operations/tasks/${encodeURIComponent(id)}?${nextParams.toString()}`);
  };
  const runCommand = async (kind: 'cancel' | 'retry') => {
    if (!taskId || busy) return;
    if (!window.confirm(kind === 'cancel' ? '确认请求取消此任务吗？' : '确认请求重试此任务吗？')) return;
    setBusy(kind); setError(null);
    try { if (kind === 'cancel') await platformTasksApi.cancel(taskId); else await platformTasksApi.retry(taskId); await loadDetails(taskId); await loadTasks(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败'); }
    finally { setBusy(null); }
  };
  const copyTaskId = async () => {
    if (!taskId || !navigator.clipboard) return;
    await navigator.clipboard.writeText(taskId); setCopied(true); window.setTimeout(() => setCopied(false), 1500);
  };

  const selectedState = details?.task.task_state;
  const canCancel = Boolean(selectedState && !terminalStates.has(selectedState));
  const canRetry = selectedState === 'RETRY_WAIT';
  const summary = useMemo(() => ({
    active: tasks.filter((task) => !terminalStates.has(task.task_state) && task.task_state !== 'BLOCKED').length,
    blocked: tasks.filter((task) => task.task_state === 'BLOCKED').length,
    failed: tasks.filter((task) => task.task_state === 'FAILED').length,
    history: tasks.filter((task) => terminalStates.has(task.task_state)).length,
  }), [tasks]);

  return <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 p-4 md:p-6" data-testid="operations-tasks-page">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.18em] text-muted-text">P-TASKS</p><h1 className="text-2xl font-semibold text-foreground">任务运维</h1><p className="mt-1 text-sm text-secondary-text">观察任务状态、Attempt 时间线与审计事件。最终状态以查询结果为准。</p></div><div className="text-xs text-muted-text" role="status">{stale ? '实时连接断开，15 秒轮询中' : '实时事件已连接'}</div></header>
    {error ? <div role="alert" className="rounded-xl border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div> : null}
    <section className="rounded-2xl border border-subtle bg-card p-3" aria-label="任务筛选"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label className="text-xs text-muted-text">任务类型<input aria-label="任务类型" value={filters.taskType} onChange={(event) => updateQuery('task_type', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground" placeholder="artifact_orphan_dry_run" /></label>
      <label className="text-xs text-muted-text">状态<select aria-label="任务状态" value={filters.taskState} onChange={(event) => updateQuery('task_state', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground"><option value="">全部状态</option>{taskStates.map((state) => <option key={state} value={state}>{state}</option>)}</select></label>
      <label className="text-xs text-muted-text">优先级<select aria-label="优先级" value={filters.priorityClass} onChange={(event) => updateQuery('priority_class', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground"><option value="">全部优先级</option>{priorityClasses.map((priority) => <option key={priority} value={priority}>{priority}</option>)}</select></label>
      <label className="text-xs text-muted-text">请求者<input aria-label="请求者" value={filters.requestedBy} onChange={(event) => updateQuery('requested_by', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground" placeholder="owner:ops" /></label>
      <label className="text-xs text-muted-text">开始日期<input aria-label="开始日期" type="date" value={filters.createdFrom} onChange={(event) => updateQuery('created_from', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground" /></label>
      <label className="text-xs text-muted-text">结束日期<input aria-label="结束日期" type="date" value={filters.createdTo} onChange={(event) => updateQuery('created_to', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground" /></label>
      <label className="text-xs text-muted-text sm:col-span-2">关联资源<input aria-label="关联资源" value={filters.resourceId} onChange={(event) => updateQuery('resource_id', event.target.value)} className="mt-1 w-full rounded-lg border border-subtle bg-white/5 px-2 py-2 text-sm text-foreground" placeholder="task_… / artifact_…" /></label>
    </div></section>
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="任务筛选标签">{TABS.map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => selectTab(item)} className={`rounded-xl px-3 py-2 text-sm ${tab === item ? 'bg-primary text-primary-foreground' : 'bg-white/5 text-secondary-text'}`}>{item === 'active' ? '活跃' : item === 'blocked' ? '阻塞' : item === 'failed' ? '失败' : '历史'} <span className="ml-1 text-xs opacity-70">{summary[item]}</span></button>)}</div>
    <main className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section className="min-w-0 rounded-2xl border border-subtle bg-card p-3" aria-label="任务列表">{loading ? <div className="space-y-2"><div className="h-12 animate-pulse rounded-xl bg-white/5" /><div className="h-12 animate-pulse rounded-xl bg-white/5" /></div> : tasks.length === 0 ? <div className="py-12 text-center text-sm text-muted-text">当前筛选下暂无任务</div> : <div className="space-y-2">{tasks.map((task) => <button key={task.task_id} type="button" onClick={() => selectTask(task.task_id)} className={`w-full rounded-xl border px-3 py-3 text-left transition ${taskId === task.task_id ? 'border-primary bg-primary/10' : 'border-subtle hover:bg-white/5'}`}><div className="flex items-center justify-between gap-3"><span className="font-medium text-foreground">{task.task_type}</span><span className="rounded-full bg-white/10 px-2 py-1 text-xs text-secondary-text">{task.task_state}</span></div><div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-text"><span>{shortId(task.task_id)}</span><span>{task.requested_by}</span><TimeValue value={task.created_at} /></div></button>)}</div>}</section>
      <section className="min-w-0 rounded-2xl border border-subtle bg-card p-4" aria-label="任务详情">{!taskId ? <div className="flex min-h-[320px] items-center justify-center text-sm text-muted-text">选择一个任务查看详情</div> : detailLoading || !details ? <div className="space-y-3"><div className="h-6 w-2/3 animate-pulse rounded bg-white/5" /><div className="h-24 animate-pulse rounded-xl bg-white/5" /></div> : <div className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold text-foreground">{details.task.task_type}</h2><div className="flex items-center gap-2"><p className="font-mono text-xs text-muted-text">{details.task.task_id}</p><button type="button" onClick={() => void copyTaskId()} className="rounded border border-subtle px-2 py-1 text-xs text-secondary-text">{copied ? '已复制' : '复制 ID'}</button></div></div><div className="flex gap-2">{canCancel ? <button type="button" disabled={busy !== null} onClick={() => void runCommand('cancel')} className="rounded-lg border border-red-400/30 px-3 py-2 text-sm text-red-200 disabled:opacity-50">{busy === 'cancel' ? '取消中…' : '请求取消'}</button> : null}{canRetry ? <button type="button" disabled={busy !== null} onClick={() => void runCommand('retry')} className="rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">{busy === 'retry' ? '重试中…' : '请求重试'}</button> : null}</div></div>
        <div className="grid gap-3 text-sm sm:grid-cols-2"><div><span className="text-muted-text">状态</span><div className="font-medium text-foreground">{details.task.task_state}</div></div><div><span className="text-muted-text">创建时间</span><div className="text-foreground"><TimeValue value={details.task.created_at} /></div></div><div><span className="text-muted-text">结果 Artifact</span><div className="font-mono text-xs text-foreground">{details.task.result_artifact_id || '—'}</div></div><div><span className="text-muted-text">失败码</span><div className="font-mono text-xs text-foreground">{details.task.failure_code || '—'}</div></div></div>
        <div><h3 className="mb-2 font-medium text-foreground">Attempt 时间线</h3><div className="space-y-2">{details.attempts.length ? details.attempts.map((attempt) => <div key={attempt.attempt_id} className="rounded-xl border border-subtle px-3 py-3 text-sm"><div className="flex justify-between gap-3"><span>Attempt {attempt.attempt_number} · {attempt.attempt_phase}</span><span>{attempt.attempt_outcome || '进行中'}</span></div><div className="mt-1 text-xs text-muted-text">Worker {attempt.worker_id} · 进度 {Math.round(attempt.phase_progress * 100)}% · Lease 至 <TimeValue value={attempt.lease_expires_at} /></div>{Object.keys(attempt.resource_usage).length ? <div className="mt-2 flex flex-wrap gap-2 text-xs text-secondary-text">{Object.entries(attempt.resource_usage).map(([key, value]) => <span key={key} className="rounded bg-white/5 px-2 py-1">{key}: {value}</span>)}</div> : null}</div>) : <p className="text-sm text-muted-text">暂无 Attempt</p>}</div></div>
        <div><h3 className="mb-2 font-medium text-foreground">State Event 审计</h3><div className="space-y-2">{details.state_events.map((event) => <div key={`${event.task_id}-${event.event_sequence}`} className="rounded-xl border border-subtle px-3 py-2 text-xs"><div className="flex justify-between gap-3"><span>{event.previous_task_state || '—'} → {event.next_task_state}</span><TimeValue value={event.event_at} /></div><div className="mt-1 text-muted-text">{event.reason_code} · {event.actor_ref}</div></div>)}</div></div>
        <div><h3 className="mb-2 font-medium text-foreground">Checkpoint</h3>{(details.checkpoints || []).length ? (details.checkpoints || []).map((checkpoint) => <div key={checkpoint.checkpoint_id} className="rounded-xl border border-subtle px-3 py-2 text-xs text-secondary-text">{checkpoint.phase} · seq {checkpoint.sequence} · <TimeValue value={checkpoint.created_at} /></div>) : <p className="text-sm text-muted-text">暂无 Checkpoint</p>}</div><div><h3 className="mb-2 font-medium text-foreground">诊断 Artifact</h3>{(details.diagnostic_artifact_refs || []).length ? <div className="flex flex-wrap gap-2">{(details.diagnostic_artifact_refs || []).map((ref) => <span key={ref} className="rounded bg-white/5 px-2 py-1 font-mono text-xs text-secondary-text">{ref}</span>)}</div> : <p className="text-sm text-muted-text">暂无诊断 Artifact</p>}</div>
      </div>}</section>
    </main>
  </div>;
}
