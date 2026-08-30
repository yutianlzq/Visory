import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { platformTasksApi } from '../api/platformTasks';
import type { TaskDetails, TaskRecord, TaskState } from '../types/generated/platform-api';

const TABS = ['active', 'blocked', 'failed', 'history'] as const;
type Tab = typeof TABS[number];
const terminalStates = new Set<TaskState>(['SUCCEEDED', 'DEGRADED', 'FAILED', 'CANCELLED']);

function shortId(value: string) { return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value; }
function localTime(value: string | null | undefined) { return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—'; }

export default function OperationsTasksPage() {
  const { taskId } = useParams<{ taskId?: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>((searchParams.get('tab') as Tab) || 'active');
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [details, setDetails] = useState<TaskDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState<'cancel' | 'retry' | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const loadTasks = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const result = await platformTasksApi.list({ tab, limit: 50 });
      setTasks(result.items); setStale(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '任务服务不可用');
    } finally { setLoading(false); }
  }, [tab]);

  const loadDetails = useCallback(async (id: string) => {
    setDetailLoading(true);
    try { setDetails(await platformTasksApi.get(id)); setStale(false); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '任务详情不可用'); }
    finally { setDetailLoading(false); }
  }, []);

  useEffect(() => { void loadTasks(); }, [loadTasks]);
  useEffect(() => {
    if (taskId) void loadDetails(taskId); else setDetails(null);
  }, [taskId, loadDetails]);
  useEffect(() => {
    const source = new EventSource('/api/platform/v1/tasks/events', { withCredentials: true });
    eventSourceRef.current = source;
    const refresh = () => { setStale(false); void loadTasks(); if (taskId) void loadDetails(taskId); };
    source.addEventListener('task_state_changed', refresh);
    source.onerror = () => setStale(true);
    return () => { source.close(); eventSourceRef.current = null; };
  }, [loadTasks, loadDetails, taskId]);
  useEffect(() => {
    if (!stale) return;
    const timer = window.setInterval(() => { void loadTasks(); if (taskId) void loadDetails(taskId); }, 15000);
    return () => window.clearInterval(timer);
  }, [stale, loadTasks, loadDetails, taskId]);

  const selectTab = (next: Tab) => {
    setTab(next);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('tab', next); nextParams.delete('cursor'); setSearchParams(nextParams);
  };
  const selectTask = (id: string) => {
    const nextParams = new URLSearchParams(searchParams); nextParams.set('tab', tab); setSearchParams(nextParams);
    navigate(`/operations/tasks/${encodeURIComponent(id)}?${nextParams.toString()}`);
  };
  const runCommand = async (kind: 'cancel' | 'retry') => {
    if (!taskId) return;
    setBusy(kind); setError(null);
    try { if (kind === 'cancel') await platformTasksApi.cancel(taskId); else await platformTasksApi.retry(taskId); await loadDetails(taskId); await loadTasks(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败'); }
    finally { setBusy(null); }
  };

  const selectedState = details?.task.task_state;
  const canCancel = selectedState && !terminalStates.has(selectedState);
  const canRetry = selectedState === 'RETRY_WAIT';
  const summary = useMemo(() => ({ active: tasks.filter((task) => !terminalStates.has(task.task_state) && task.task_state !== 'BLOCKED').length, blocked: tasks.filter((task) => task.task_state === 'BLOCKED').length, failed: tasks.filter((task) => task.task_state === 'FAILED').length, history: tasks.filter((task) => terminalStates.has(task.task_state)).length }), [tasks]);

  return <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 p-4 md:p-6" data-testid="operations-tasks-page">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.18em] text-muted-text">P-TASKS</p><h1 className="text-2xl font-semibold text-foreground">任务运维</h1><p className="mt-1 text-sm text-secondary-text">观察任务状态、Attempt 时间线与审计事件。最终状态以查询结果为准。</p></div><div className="text-xs text-muted-text">{stale ? '实时连接断开，15 秒轮询中' : '实时事件已连接'}</div></header>
    {error ? <div role="alert" className="rounded-xl border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div> : null}
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="任务筛选">
      {TABS.map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => selectTab(item)} className={`rounded-xl px-3 py-2 text-sm ${tab === item ? 'bg-primary text-primary-foreground' : 'bg-white/5 text-secondary-text'}`}>{item === 'active' ? '活跃' : item === 'blocked' ? '阻塞' : item === 'failed' ? '失败' : '历史'} <span className="ml-1 text-xs opacity-70">{summary[item]}</span></button>)}
    </div>
    <main className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section className="min-w-0 rounded-2xl border border-subtle bg-card p-3" aria-label="任务列表">
        {loading ? <div className="space-y-2"><div className="h-12 animate-pulse rounded-xl bg-white/5"/><div className="h-12 animate-pulse rounded-xl bg-white/5"/></div> : tasks.length === 0 ? <div className="py-12 text-center text-sm text-muted-text">当前筛选下暂无任务</div> : <div className="space-y-2">{tasks.map((task) => <button key={task.task_id} type="button" onClick={() => selectTask(task.task_id)} className={`w-full rounded-xl border px-3 py-3 text-left transition ${taskId === task.task_id ? 'border-primary bg-primary/10' : 'border-subtle hover:bg-white/5'}`}><div className="flex items-center justify-between gap-3"><span className="font-medium text-foreground">{task.task_type}</span><span className="rounded-full bg-white/10 px-2 py-1 text-xs text-secondary-text">{task.task_state}</span></div><div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-text"><span>{shortId(task.task_id)}</span><span>{task.requested_by}</span><span>{localTime(task.created_at)}</span></div></button>)}</div>}
      </section>
      <section className="min-w-0 rounded-2xl border border-subtle bg-card p-4" aria-label="任务详情">
        {!taskId ? <div className="flex min-h-[320px] items-center justify-center text-sm text-muted-text">选择一个任务查看详情</div> : detailLoading || !details ? <div className="space-y-3"><div className="h-6 w-2/3 animate-pulse rounded bg-white/5"/><div className="h-24 animate-pulse rounded-xl bg-white/5"/></div> : <div className="space-y-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold text-foreground">{details.task.task_type}</h2><p className="font-mono text-xs text-muted-text">{details.task.task_id}</p></div><div className="flex gap-2">{canCancel ? <button type="button" disabled={busy !== null} onClick={() => void runCommand('cancel')} className="rounded-lg border border-red-400/30 px-3 py-2 text-sm text-red-200 disabled:opacity-50">{busy === 'cancel' ? '取消中…' : '请求取消'}</button> : null}{canRetry ? <button type="button" disabled={busy !== null} onClick={() => void runCommand('retry')} className="rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">{busy === 'retry' ? '重试中…' : '请求重试'}</button> : null}</div></div><div className="grid gap-2 text-sm sm:grid-cols-2"><div><span className="text-muted-text">状态</span><div className="font-medium text-foreground">{details.task.task_state}</div></div><div><span className="text-muted-text">创建时间</span><div className="text-foreground">{localTime(details.task.created_at)}</div></div><div><span className="text-muted-text">结果 Artifact</span><div className="font-mono text-xs text-foreground">{details.task.result_artifact_id || '—'}</div></div><div><span className="text-muted-text">失败码</span><div className="font-mono text-xs text-foreground">{details.task.failure_code || '—'}</div></div></div><div><h3 className="mb-2 font-medium text-foreground">Attempt 时间线</h3><div className="space-y-2">{details.attempts.length ? details.attempts.map((attempt) => <div key={attempt.attempt_id} className="rounded-xl border border-subtle px-3 py-3 text-sm"><div className="flex justify-between"><span>Attempt {attempt.attempt_number} · {attempt.attempt_phase}</span><span>{attempt.attempt_outcome || '进行中'}</span></div><div className="mt-1 text-xs text-muted-text">Worker {attempt.worker_id} · 进度 {Math.round(attempt.phase_progress * 100)}% · Lease 至 {localTime(attempt.lease_expires_at)}</div></div>) : <p className="text-sm text-muted-text">暂无 Attempt</p>}</div></div><div><h3 className="mb-2 font-medium text-foreground">State Event 审计</h3><div className="space-y-2">{details.state_events.map((event) => <div key={`${event.task_id}-${event.event_sequence}`} className="rounded-xl border border-subtle px-3 py-2 text-xs"><div className="flex justify-between gap-3"><span>{event.previous_task_state || '—'} → {event.next_task_state}</span><span>{localTime(event.event_at)}</span></div><div className="mt-1 text-muted-text">{event.reason_code} · {event.actor_ref}</div></div>)}</div></div><div><h3 className="mb-2 font-medium text-foreground">Checkpoint</h3>{(details.checkpoints || []).length ? (details.checkpoints || []).map((checkpoint) => <div key={checkpoint.checkpoint_id} className="rounded-xl border border-subtle px-3 py-2 text-xs text-secondary-text">{checkpoint.phase} · seq {checkpoint.sequence} · {localTime(checkpoint.created_at)}</div>) : <p className="text-sm text-muted-text">暂无 Checkpoint</p>}</div></div>}
      </section>
    </main>
  </div>;
}

