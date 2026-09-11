import { AlertTriangle, CheckCircle2, Clock3, Copy, Database, RefreshCw, ShieldAlert, Wrench } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { formatDataQualityError, platformDataQualityApi } from '../api/platformDataQuality';
import type {
  DataQualityActionRequest,
  DataQualityActionResult,
  DataQualityDataset,
  DataQualityDiff,
  DataQualityEvidence,
  DataQualityQueryResult,
  QualityStatus,
  SnapshotCapabilityStatus,
} from '../types/generated/platform-api';

const capabilityLabels: Record<string, string> = {
  identity_core: '身份主数据',
  trading_calendar: '交易日历',
  backtest_core: '回测核心',
  market_observation: '市场观察',
  sector_observation: '板块观察',
  financial_research: '财务研究',
  news_research: '新闻研究',
  global_observation: '全球观察',
};

function defaultTradeDate() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());
}

function statusTone(status: string) {
  if (status === 'CERTIFIED' || status === 'COMPLETE' || status === 'SUCCEEDED') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200';
  if (status === 'PROVISIONAL' || status === 'PARTIAL' || status === 'DEGRADED' || status === 'PENDING') return 'border-amber-400/30 bg-amber-500/10 text-amber-100';
  if (status === 'STALE') return 'border-orange-400/30 bg-orange-500/10 text-orange-100';
  return 'border-red-400/30 bg-red-500/10 text-red-100';
}

function StatusBadge({ status }: { status: string }) {
  const Icon = status === 'CERTIFIED' || status === 'COMPLETE' || status === 'SUCCEEDED'
    ? CheckCircle2
    : status === 'PENDING'
      ? Clock3
      : AlertTriangle;
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs ${statusTone(status)}`}><Icon className="h-3.5 w-3.5" />{status}</span>;
}

function localTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—';
}

function pct(value: number) { return `${(value * 100).toFixed(value === 1 ? 0 : 1)}%`; }

function CopyId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return <span className="inline-flex max-w-full items-center gap-1"><code className="break-all text-xs text-secondary-text">{value}</code><button type="button" aria-label={`复制 ${value}`} onClick={() => { if (navigator.clipboard) void navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1200); }} className="shrink-0 rounded border border-subtle p-1 text-muted-text"><Copy className="h-3.5 w-3.5" /></button>{copied ? <span className="text-[11px] text-emerald-300">已复制</span> : null}</span>;
}

function EvidenceGroup({ title, items }: { title: string; items: ReadonlyArray<DataQualityEvidence> | undefined }) {
  return <div><h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-text">{title}</h4>{items?.length ? <div className="space-y-2">{items.map((item) => <div key={item.resource_id} className="rounded-xl border border-subtle bg-white/[0.025] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><CopyId value={item.resource_id} />{item.quality_status ? <StatusBadge status={item.quality_status} /> : null}</div><div className="mt-2 grid gap-1 text-xs text-muted-text sm:grid-cols-2">{Object.entries(item.details || {}).map(([key, value]) => <div key={key}><span>{key}: </span><span className="text-secondary-text">{Array.isArray(value) ? value.join(', ') : String(value)}</span></div>)}</div></div>)}</div> : <p className="text-sm text-muted-text">无已登记证据</p>}</div>;
}

function DiffList({ label, items }: { label: string; items: ReadonlyArray<Readonly<Record<string, unknown>>> | undefined }) {
  return <div className="rounded-xl border border-subtle p-3"><div className="text-xs text-muted-text">{label}</div><div className="mt-1 text-2xl font-semibold text-foreground">{items?.length || 0}</div></div>;
}

export default function DataQualityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tradeDate = searchParams.get('trade_date') || defaultTradeDate();
  const [projection, setProjection] = useState<DataQualityQueryResult | null>(null);
  const [selectedDatasetKey, setSelectedDatasetKey] = useState<string | null>(null);
  const [diff, setDiff] = useState<DataQualityDiff | null>(null);
  const [actionResult, setActionResult] = useState<DataQualityActionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [compareLoading, setCompareLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<DataQualityActionRequest['action'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null); setDiff(null); setActionResult(null);
    try {
      const result = await platformDataQualityApi.get({ trade_date: tradeDate });
      setProjection(result);
      setSelectedDatasetId((current) => result.datasets?.some((item) => `${item.dataset_id}:${item.partition_key}` === current) ? current : result.datasets?.[0] ? `${result.datasets[0].dataset_id}:${result.datasets[0].partition_key}` : null);
    } catch (cause) {
      setProjection(null);
      setError(formatDataQualityError(cause));
    } finally { setLoading(false); }
  }, [tradeDate]);

  useEffect(() => { void load(); }, [load]);

  const selectedDataset = useMemo<DataQualityDataset | null>(() => projection?.datasets?.find((item) => `${item.dataset_id}:${item.partition_key}` === selectedDatasetKey) || null, [projection, selectedDatasetKey]);

  const changeDate = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set('trade_date', value); else next.delete('trade_date');
    setSearchParams(next);
  };

  const comparePrevious = async () => {
    if (!projection) return;
    setCompareLoading(true); setError(null);
    try { setDiff(await platformDataQualityApi.compare(projection.snapshot_id, projection.supersedes_id || undefined)); }
    catch (cause) { setError(formatDataQualityError(cause, 'Snapshot 对比失败')); }
    finally { setCompareLoading(false); }
  };

  const runAction = async (action: DataQualityActionRequest['action']) => {
    if (!projection || actionLoading) return;
    const label = action === 'recheck' ? '重新检查' : action === 'rebuild' ? '创建 Rebuild' : '创建 Correction';
    if (!window.confirm(`${label}只会创建受控 data_snapshot_build Task，不会直接修改 Canonical。继续吗？`)) return;
    setActionLoading(action); setError(null); setActionResult(null);
    const idempotencyKey = `data-quality-${action}-${projection.snapshot_id}-${Date.now()}`;
    try {
      setActionResult(await platformDataQualityApi.createAction({
        action,
        snapshot_id: projection.snapshot_id,
        trade_date: projection.trade_date,
        reason_code: action === 'correction' ? 'QUALITY_CORRECTION_REQUESTED' : 'QUALITY_RECHECK_REQUESTED',
        requested_by: 'owner:data-quality',
      }, idempotencyKey));
    } catch (cause) { setError(formatDataQualityError(cause, '受控任务创建失败')); }
    finally { setActionLoading(null); }
  };

  return <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 p-4 md:p-6" data-testid="data-quality-page">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.18em] text-muted-text">P-DATA</p><h1 className="text-2xl font-semibold text-foreground">数据质量</h1><p className="mt-1 text-sm text-secondary-text">只读查看 Snapshot、Capability 与完整数据血缘；Canonical 纠正必须走版本化 Task。</p></div><div className="flex items-end gap-2"><label className="text-xs text-muted-text">交易日<input aria-label="交易日" type="date" value={tradeDate} onChange={(event) => changeDate(event.target.value)} className="mt-1 block rounded-lg border border-subtle bg-white/5 px-3 py-2 text-sm text-foreground" /></label><button type="button" onClick={() => void load()} className="rounded-lg border border-subtle p-2.5 text-secondary-text" aria-label="刷新数据质量"><RefreshCw className="h-4 w-4" /></button></div></header>

    {error ? <div role="alert" className="rounded-xl border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-100"><span className="font-mono">{error}</span></div> : null}
    {loading ? <div role="status" className="grid gap-3 md:grid-cols-3"><div className="h-32 animate-pulse rounded-2xl bg-white/5" /><div className="h-32 animate-pulse rounded-2xl bg-white/5" /><div className="h-32 animate-pulse rounded-2xl bg-white/5" /></div> : !projection ? <section className="rounded-2xl border border-subtle bg-card py-16 text-center"><ShieldAlert className="mx-auto h-8 w-8 text-muted-text" /><h2 className="mt-3 font-medium text-foreground">数据质量不可用</h2><p className="mt-1 text-sm text-muted-text">当前交易日没有可展示的 Snapshot，或数据平台尚未接入。</p></section> : <>
      <section className="grid gap-3 lg:grid-cols-[1.5fr_1fr_1fr]">
        <div className="rounded-2xl border border-subtle bg-card p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-xs text-muted-text">Current Snapshot</p><CopyId value={projection.snapshot_id} /></div><div className="flex gap-2"><StatusBadge status={projection.publication_status} /><StatusBadge status={projection.quality_status} /></div></div><div className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><span className="text-muted-text">data_as_of</span><div className="text-foreground">{localTime(projection.data_as_of)}</div></div><div><span className="text-muted-text">cutoff</span><div className="text-foreground">{localTime(projection.cutoff_at)}</div></div><div><span className="text-muted-text">Revision</span><div className="text-foreground">#{projection.revision} · {projection.revision_kind}</div></div><div><span className="text-muted-text">Supersedes</span><div>{projection.supersedes_id ? <CopyId value={projection.supersedes_id} /> : '—'}</div></div></div></div>
        <div className="rounded-2xl border border-subtle bg-card p-4"><p className="text-xs text-muted-text">数据集 / 缺失能力</p><div className="mt-2 text-3xl font-semibold text-foreground">{projection.datasets?.length || 0}<span className="ml-2 text-sm font-normal text-muted-text">datasets</span></div><div className="mt-3 flex flex-wrap gap-1">{projection.missing_capabilities?.length ? projection.missing_capabilities.map((item) => <span key={item} className="rounded bg-red-500/10 px-2 py-1 text-xs text-red-100">{item}</span>) : <span className="text-xs text-emerald-200">无缺失能力</span>}</div></div>
        <div className="rounded-2xl border border-subtle bg-card p-4"><p className="text-xs text-muted-text">受控操作</p><div className="mt-3 grid gap-2">{(['recheck', 'rebuild', 'correction'] as const).map((action) => <button key={action} type="button" disabled={actionLoading !== null} onClick={() => void runAction(action)} className="inline-flex items-center justify-center gap-2 rounded-lg border border-subtle px-3 py-2 text-sm text-secondary-text disabled:opacity-50"><Wrench className="h-4 w-4" />{actionLoading === action ? '创建中…' : action === 'recheck' ? '重新检查' : action === 'rebuild' ? '创建 Rebuild' : '创建 Correction'}</button>)}</div></div>
      </section>

      {actionResult ? <section role="status" className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-4 text-sm text-emerald-100"><p>{actionResult.message || '受控任务已创建。'}</p><Link to={`/operations/tasks/${encodeURIComponent(actionResult.task_id)}`} className="mt-2 inline-flex underline">查看 Task {actionResult.task_id}</Link></section> : null}

      <section className="rounded-2xl border border-subtle bg-card p-4"><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-foreground">Capability Gate</h2><span className="text-xs text-muted-text">固定八项能力</span></div><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{projection.capabilities?.map((item) => <div key={item.capability_id} className="rounded-xl border border-subtle p-3"><div className="flex items-start justify-between gap-2"><div><div className="text-sm font-medium text-foreground">{capabilityLabels[item.capability_id] || item.capability_id}</div><div className="mt-1 font-mono text-[11px] text-muted-text">{item.capability_id}</div></div><StatusBadge status={item.capability_status as SnapshotCapabilityStatus} /></div>{item.reason_code ? <div className="mt-2 font-mono text-xs text-amber-100">{item.reason_code}</div> : null}<div className="mt-2 text-xs text-muted-text">{item.dataset_ids?.join(', ') || '无绑定 Dataset'}</div></div>)}</div></section>

      <section className="overflow-hidden rounded-2xl border border-subtle bg-card"><div className="flex items-center gap-2 border-b border-subtle px-4 py-3"><Database className="h-4 w-4 text-muted-text" /><h2 className="font-semibold text-foreground">Dataset / Partition</h2></div>{projection.datasets?.length ? <div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-white/[0.03] text-xs text-muted-text"><tr><th className="px-3 py-2">Dataset</th><th className="px-3 py-2">Provider</th><th className="px-3 py-2">分区</th><th className="px-3 py-2">覆盖</th><th className="px-3 py-2">新鲜度</th><th className="px-3 py-2">冲突</th><th className="px-3 py-2">质量</th><th className="px-3 py-2">Revision</th></tr></thead><tbody>{projection.datasets.map((item) => <tr key={`${item.dataset_id}:${item.partition_key}`} onClick={() => setSelectedDatasetKey(`${item.dataset_id}:${item.partition_key}`)} className={`cursor-pointer border-t border-subtle ${selectedDatasetKey === `${item.dataset_id}:${item.partition_key}` ? 'bg-primary/10' : 'hover:bg-white/[0.03]'}`}><td className="px-3 py-3 font-medium text-foreground">{item.dataset_id}</td><td className="px-3 py-3 text-secondary-text">{item.provider_ids?.join(', ') || '—'}</td><td className="px-3 py-3 font-mono text-xs text-secondary-text">{item.partition_key}</td><td className="px-3 py-3 text-secondary-text">{pct(item.coverage_ratio)}</td><td className="px-3 py-3 text-xs text-secondary-text">{localTime(item.freshness_at)}</td><td className="px-3 py-3 text-secondary-text">{item.conflict_count}</td><td className="px-3 py-3"><StatusBadge status={item.quality_status as QualityStatus} /></td><td className="px-3 py-3 text-secondary-text">#{item.revision} · {item.revision_kind}</td></tr>)}</tbody></table></div> : <div className="py-12 text-center text-sm text-muted-text">Snapshot 尚未登记 Dataset / Partition</div>}</section>

      {selectedDataset ? <section className="rounded-2xl border border-subtle bg-card p-4"><div className="mb-4 flex flex-wrap items-center justify-between gap-2"><div><p className="text-xs text-muted-text">证据下钻</p><h2 className="font-semibold text-foreground">{selectedDataset.dataset_id} · {selectedDataset.partition_key}</h2></div>{selectedDataset.correction_snapshot_id ? <div className="text-xs text-amber-100">Correction of <CopyId value={selectedDataset.correction_snapshot_id} /></div> : null}</div><div className="grid gap-5 lg:grid-cols-2"><EvidenceGroup title="ProviderRun" items={selectedDataset.provider_runs} /><EvidenceGroup title="RawObject" items={selectedDataset.raw_objects} /><EvidenceGroup title="CanonicalPartition" items={selectedDataset.canonical_partitions} /><EvidenceGroup title="QualityReport" items={selectedDataset.quality_reports} /><EvidenceGroup title="Quarantine" items={selectedDataset.quarantines} /></div></section> : null}

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]"><div className="rounded-2xl border border-subtle bg-card p-4"><h2 className="font-semibold text-foreground">15:50–20:30 数据时间线</h2><div className="mt-4 space-y-3">{projection.timeline?.map((item) => <div key={item.stage_id} className="flex items-start gap-3"><div className="mt-1 h-2.5 w-2.5 rounded-full bg-primary" /><div className="min-w-0 flex-1 border-b border-subtle pb-3"><div className="flex flex-wrap justify-between gap-2"><span className="font-medium text-foreground">{item.local_time.slice(0, 5)} · {item.stage_id}</span><StatusBadge status={item.stage_status} /></div>{item.reason_code ? <div className="mt-1 font-mono text-xs text-amber-100">{item.reason_code}</div> : null}{item.task_ids?.map((id) => <Link key={id} to={`/operations/tasks/${encodeURIComponent(id)}`} className="mr-2 mt-1 inline-block font-mono text-xs text-primary underline">{id}</Link>)}</div></div>)}</div></div>
        <div className="rounded-2xl border border-subtle bg-card p-4"><div className="flex items-center justify-between gap-2"><h2 className="font-semibold text-foreground">Snapshot Compare</h2><button type="button" disabled={compareLoading} onClick={() => void comparePrevious()} className="rounded-lg border border-subtle px-3 py-2 text-xs text-secondary-text disabled:opacity-50">{compareLoading ? '比较中…' : '与上一 Revision 比较'}</button></div>{diff ? <div className="mt-4 grid grid-cols-2 gap-2"><DiffList label="新增分区" items={diff.added_partitions} /><DiffList label="移除分区" items={diff.removed_partitions} /><DiffList label="修订分区" items={diff.revised_partitions} /><DiffList label="质量变化" items={diff.quality_changes} /><DiffList label="能力变化" items={diff.capability_changes} /><DiffList label="Provider 切换" items={diff.provider_switches} /><div className="col-span-2 rounded-xl border border-subtle p-3"><div className="text-xs text-muted-text">影响 Task</div>{diff.affected_tasks?.length ? diff.affected_tasks.map((id) => <Link key={id} to={`/operations/tasks/${encodeURIComponent(id)}`} className="mt-1 block break-all font-mono text-xs text-primary underline">{id}</Link>) : <p className="mt-1 text-sm text-muted-text">无已登记影响</p>}</div></div> : <p className="mt-4 text-sm text-muted-text">比较 Correction / Revision，查看分区、质量、能力、Provider 和消费者影响。</p>}</div></section>
      <section className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100"><strong>只读边界：</strong>本页不编辑 Canonical 值、不切换生产 Provider、不写真实 /data。Recheck / Rebuild / Correction 仅创建受控 Task。</section>
    </>}
  </div>;
}
