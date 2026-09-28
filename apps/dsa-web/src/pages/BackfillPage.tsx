import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatBackfillError, platformBackfillApi } from '../api/platformBackfill';
import type { BackfillBatchProjection } from '../types/generated/platform-api';

function range(value: ReadonlyArray<unknown> | null | undefined): string { return value?.length === 2 ? `${String(value[0])} → ${String(value[1])}` : '—'; }
function rangeList(values: ReadonlyArray<ReadonlyArray<unknown>> | null | undefined, legacy: ReadonlyArray<unknown> | null | undefined): string {
  const ranges = values?.length ? values : legacy?.length === 2 ? [legacy] : [];
  return ranges.length ? ranges.map(item => range(item)).join('; ') : '—';
}
function statusClass(status: BackfillBatchProjection['batch_state']): string {
  if (status === 'COMPLETED') return 'text-emerald-300';
  if (status === 'FAILED' || status === 'CANCELLED' || status === 'UNAVAILABLE') return 'text-rose-300';
  if (status === 'QUARANTINED' || status === 'PARTIAL') return 'text-amber-300';
  return 'text-sky-300';
}

export default function BackfillPage() {
  const [batches, setBatches] = useState<BackfillBatchProjection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void platformBackfillApi.list().then(result => { if (active) setBatches(result.items); }).catch(cause => { if (active) setError(formatBackfillError(cause)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  return <main className="mx-auto flex w-full max-w-[1500px] flex-col gap-5 p-4 md:p-6" data-testid="backfill-page">
    <header className="rounded-2xl border border-subtle bg-card p-5"><p className="text-xs uppercase tracking-[0.22em] text-muted-text">WP-0207 · CONTROL PLANE</p><h1 className="mt-2 text-2xl font-semibold text-foreground">历史数据回填</h1><p className="mt-2 max-w-3xl text-sm text-secondary-text">查看受控批次的范围、checkpoint、质量事件与 Provider 血缘。页面只观察 Durable Task 投影，不直接连接生产 Provider。</p></header>
    {loading ? <p className="text-sm text-muted-text">加载回填批次…</p> : null}
    {error ? <div role="alert" className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-200">{error}</div> : null}
    {!loading && !error && batches.length === 0 ? <div className="rounded-xl border border-subtle bg-card p-6 text-sm text-muted-text">暂无回填批次。创建批次后，它会通过 Operations Task Control Plane 出现在这里。</div> : null}
    {batches.length ? <section className="overflow-x-auto rounded-2xl border border-subtle bg-card"><table className="w-full min-w-[1250px] text-left text-sm"><thead className="border-b border-subtle text-xs uppercase tracking-wide text-muted-text"><tr><th className="px-4 py-3">批次</th><th className="px-4 py-3">状态</th><th className="px-4 py-3">阶段 / 数据集</th><th className="px-4 py-3">范围</th><th className="px-4 py-3">Checkpoint</th><th className="px-4 py-3">质量 / 资源</th><th className="px-4 py-3">发布血缘</th><th className="px-4 py-3">Task</th></tr></thead><tbody>{batches.map(batch => <tr key={batch.batch_id} className="border-b border-subtle/70 align-top last:border-0"><td className="px-4 py-4"><div className="font-mono text-xs text-foreground">{batch.batch_id}</div><div className="mt-1 text-xs text-muted-text">{batch.batch_type}{batch.dry_run || batch.plan_only ? ' · dry-run' : ''}</div></td><td className={`px-4 py-4 font-semibold ${statusClass(batch.batch_state)}`}><div>{batch.batch_state}</div>{batch.blocked_reason_code ? <div className="mt-1 text-xs font-normal text-amber-200">{batch.blocked_reason_code}</div> : null}{batch.failure_code ? <div className="mt-1 text-xs font-normal text-rose-200">{batch.failure_code}</div> : null}{batch.unblock_condition ? <div className="mt-1 max-w-56 truncate text-xs font-normal text-muted-text" aria-label={batch.unblock_condition}>{batch.unblock_condition}</div> : null}</td><td className="px-4 py-4"><div className="text-foreground">{batch.stage}</div><div className="mt-1 text-xs text-muted-text">{batch.dataset}</div><div className="mt-1 text-xs text-muted-text">policy {batch.provider_policy_id} · priority {batch.priority}</div></td><td className="px-4 py-4 font-mono text-xs text-secondary-text">{batch.date_from} → {batch.date_to}<div className="mt-1">done {range(batch.completed_range)}</div></td><td className="px-4 py-4"><div className="text-foreground">{batch.checkpoint_phase}</div><div className="mt-1 text-xs text-muted-text">skipped {rangeList(batch.skipped_ranges, batch.skipped_range)}</div><div className="mt-1 text-xs text-muted-text">failed {rangeList(batch.failed_ranges, batch.failed_range)}</div></td><td className="px-4 py-4 text-xs text-secondary-text"><div>{batch.quality_events?.length ? batch.quality_events.join(', ') : 'no quality events'}</div>{batch.differences_summary ? <div className="mt-1 max-w-72 break-words text-muted-text">diff {batch.differences_summary}</div> : null}<div className="mt-1">{batch.provider_fallback ? 'provider fallback · ' : ''}{Object.entries(batch.resource_usage || {}).map(([key, value]) => `${key}=${value}`).join(', ') || 'resource usage —'}</div></td><td className="px-4 py-4 text-xs text-secondary-text"><div>canonical {batch.canonical_partition_refs?.length || 0}</div><div className="mt-1">snapshot {batch.snapshot_refs?.length || 0}</div>{batch.supersedes_id ? <div className="mt-1 max-w-56 truncate font-mono" aria-label={batch.supersedes_id}>supersedes {batch.supersedes_id}</div> : null}</td><td className="px-4 py-4"><Link className="font-mono text-xs text-primary underline" to={`/operations/tasks/${encodeURIComponent(batch.task_id)}`}>{batch.task_id}</Link></td></tr>)}</tbody></table></section> : null}
  </main>;
}
