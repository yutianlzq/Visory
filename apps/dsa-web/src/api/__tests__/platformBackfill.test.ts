import { describe, expect, it } from 'vitest';
import { formatBackfillError } from '../platformBackfill';

describe('formatBackfillError', () => {
  it('uses the stable fallback for an untrusted generic exception', () => {
    const cause = new Error('database password=fixture-secret at C:\\private\raw_payload.json');

    expect(formatBackfillError(cause)).toBe('历史回填服务不可用');
  });

  it('projects only the safe API envelope code and public message', () => {
    const cause = {
      response: {
        data: {
          error: {
            code: 'BACKFILL_CHECKPOINT_INVALID',
            message: 'Backfill checkpoint cannot be resumed.',
            details: { absolute_path: 'C:\\private\raw_payload.json', credential: 'fixture-secret' },
          },
        },
      },
    };

    expect(formatBackfillError(cause)).toBe(
      'BACKFILL_CHECKPOINT_INVALID: Backfill checkpoint cannot be resumed.',
    );
  });


  it.each([
    'checkpoint stored at C:\\private\raw_payload.json',
    'Authorization: Bearer fixture-secret',
    'provider failed with token=fixture-secret',
    'payload: /var/lib/visory/raw.json',
  ])('falls back instead of rendering sensitive public text: %s', (message) => {
    const cause = {
      response: { data: { error: { code: 'BACKFILL_WORKER_ERROR', message } } },
    };

    expect(formatBackfillError(cause)).toBe('历史回填服务不可用');
  });

  it('rejects malformed or oversized public error fields', () => {
    expect(formatBackfillError({ response: { data: { error: { code: 'internal.error', message: 'raw' } } } })).toBe(
      '历史回填服务不可用',
    );
    expect(formatBackfillError({ response: { data: { error: { code: 'BACKFILL_ERROR', message: 'x'.repeat(241) } } } })).toBe(
      '历史回填服务不可用',
    );
  });
});
