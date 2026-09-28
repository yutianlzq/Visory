import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import BackfillPage from '../BackfillPage';
import type { BackfillBatchProjection } from '../../types/generated/platform-api';

const { list } = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock('../../api/platformBackfill', () => ({
  formatBackfillError: vi.fn(() => '历史回填服务不可用'),
  platformBackfillApi: { list },
}));

const batch: BackfillBatchProjection = {
  batch_id: 'backfill_01j9m8x2v4q7p6n5r3t1s0u9w8',
  batch_state: 'PARTIAL',
  batch_type: 'YEAR',
  checkpoint_phase: 'PRICE_MONTH',
  completed_range: ['2026-01-01', '2026-01-31'],
  dataset: 'a_stock_data',
  date_from: '2026-01-01',
  date_to: '2026-12-31',
  differences_summary: '2 partitions differ; 1 requires review',
  dry_run: false,
  failed_ranges: [
    ['2026-04-01', '2026-04-30'],
    ['2026-07-01', '2026-07-31'],
  ],
  plan_only: false,
  priority: 2,
  provider_fallback: true,
  provider_policy_id: 'policy-a-stock-v1',
  provider_run_refs: ['provider_run_01'],
  quality_events: ['UNAVAILABLE', 'QUARANTINED'],
  raw_object_refs: ['raw_object_01'],
  resource_usage: { bytes_read: 4096, partitions: 12 },
  skipped_ranges: [
    ['2026-02-01', '2026-02-28'],
    ['2026-03-01', '2026-03-31'],
  ],
  snapshot_refs: ['snapshot_01'],
  canonical_partition_refs: ['canonical_partition_01', 'canonical_partition_02'],
  stage: 'PRICE_MONTH',
  task_id: 'task_01j9m8x2v4q7p6n5r3t1s0u9w8',
  failure_code: null,
  blocked_reason_code: null,
  unblock_condition: null,
  supersedes_id: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  list.mockResolvedValue({ items: [batch], hasMore: false });
});

describe('BackfillPage', () => {
  it('renders cumulative ranges, diff, fallback, resource usage, and publication references', async () => {
    render(
      <MemoryRouter>
        <BackfillPage />
      </MemoryRouter>,
    );

    const page = await screen.findByTestId('backfill-page');
    expect(page.textContent).toContain('skipped 2026-02-01 → 2026-02-28; 2026-03-01 → 2026-03-31');
    expect(page.textContent).toContain('failed 2026-04-01 → 2026-04-30; 2026-07-01 → 2026-07-31');
    expect(page.textContent).toContain('diff 2 partitions differ; 1 requires review');
    expect(page.textContent).toContain('provider fallback · bytes_read=4096, partitions=12');
    expect(page.textContent).toContain('canonical 2');
    expect(page.textContent).toContain('snapshot 1');
    expect(page.textContent).toContain('UNAVAILABLE, QUARANTINED');
  });

  it('does not expose undeclared internal fields from a projection payload', async () => {
    const untrustedProjection = {
      ...batch,
      internal_exception: 'database password=fixture-secret',
      absolute_path: 'C:\\private\\raw_payload.json',
      raw_payload: { secret: 'fixture-secret' },
    } as BackfillBatchProjection & Record<string, unknown>;
    list.mockResolvedValueOnce({ items: [untrustedProjection], hasMore: false });

    render(
      <MemoryRouter>
        <BackfillPage />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('backfill-page')).toBeInTheDocument();
    expect(screen.queryByText('database password=fixture-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('C:\\private\\raw_payload.json')).not.toBeInTheDocument();
    expect(screen.queryByText('fixture-secret')).not.toBeInTheDocument();
  });
});\n