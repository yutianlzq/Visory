import { describe, expect, it } from 'vitest';
import { formatBackfillError } from '../platformBackfill';
import { formatDataQualityError } from '../platformDataQuality';
import { formatPlatformTaskError } from '../platformTasks';
import { projectPlatformError } from '../platformErrors';

const requestId = 'req_0123456789abcdef0123456789abcdef';
const privateTexts = [
  'token=fixture-secret',
  'lease=fixture-secret',
  'postgresql+psycopg://user:fixture-secret@localhost/database',
  'response_body: {"token":"fixture-secret"}',
  'C:\\private\\fixture-secret.json',
  '/mnt/private/fixture-secret.json',
  'Traceback (most recent call last): fixture-secret',
  'https://user:fixture-secret@example.invalid/',
  'eyJfixture.payload.signature',
  'api_key=fixture-secret',
  'api-key: fixture-secret',
  'apiKey = fixture-secret',
  '{"api_key":"fixture-secret"}',
  "{'api-key': 'fixture-secret'}",
  '{"apiKey" : "fixture-secret"}',
  'API Key: fixture-secret',
];

describe.each([
  ['Backfill', formatBackfillError],
  ['P-DATA', formatDataQualityError],
  ['Operations', (cause: unknown) => formatPlatformTaskError(cause, '任务服务不可用')],
] as const)('%s public errors', (_name, format) => {
  it.each(privateTexts)('redacts private envelope text and keeps diagnostic association: %s', (message) => {
    const cause = { response: { data: { error: {
      code: 'BACKFILL_SOURCE_UNAVAILABLE', message, request_id: requestId, retryable: true,
    } } } };
    const result = format(cause);
    expect(result).not.toContain('fixture-secret');
    expect(result).not.toContain(message);
    expect(result).toContain('BACKFILL_SOURCE_UNAVAILABLE');
    expect(result).toContain(requestId);
    expect(projectPlatformError(cause)?.retryable).toBe(true);
  });

  it('never renders a generic exception message', () => {
    expect(format(new Error('token=fixture-secret'))).not.toContain('fixture-secret');
  });

  it('rejects a forged request identifier', () => {
    const cause = { response: { data: { error: {
      code: 'BACKFILL_SOURCE_UNAVAILABLE', message: 'Service unavailable.',
      request_id: 'token=fixture-secret',
    } } } };
    expect(format(cause)).not.toContain('fixture-secret');
  });
});
