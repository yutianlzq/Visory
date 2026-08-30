import { chromium, expect, test, type Browser, type Page } from '@playwright/test';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import fs from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import type { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';
import { build as viteBuild } from 'vite';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(currentDir, '..');
const sourceRoot = path.join(webRoot, 'src');
const taskId = 'task_019a7f6d-5c00-7000-8000-000000000001';
const artifactId = 'artifact_019a7f6d-5c00-7000-8000-000000000002';
const task = {
  task_id: taskId,
  task_type: 'artifact_orphan_dry_run',
  task_schema_version: '1.0.0',
  task_state: 'RUNNING',
  priority_class: 'P5_PREVIEW_AND_MAINTENANCE',
  priority_value: 10,
  idempotency_key: 'ops-e2e-1',
  task_key: 'artifact_orphan_dry_run:ops-e2e-1',
  canonical_request_hash: 'a'.repeat(64),
  requested_by: 'owner:ops',
  request_source: 'operations-e2e',
  input_refs: [],
  requirements: {},
  active_attempt_id: 'attempt_019a7f6d-5c00-7000-8000-000000000003',
  max_attempts: 3,
  queued_at: '2026-08-30T08:00:00Z',
  created_at: '2026-08-30T08:00:00Z',
  result_artifact_id: null,
  failure_code: null,
};
const details = {
  task,
  attempts: [{
    attempt_id: task.active_attempt_id,
    task_id: taskId,
    attempt_number: 1,
    attempt_phase: 'SCANNING',
    phase_progress: 0.42,
    worker_id: 'worker-e2e',
    worker_capabilities: ['filesystem'],
    lease_token_hash: 'secret-hash-not-rendered',
    leased_at: '2026-08-30T08:00:01Z',
    lease_expires_at: '2026-08-30T08:10:01Z',
    heartbeat_at: '2026-08-30T08:05:01Z',
    started_at: '2026-08-30T08:00:02Z',
    finished_at: null,
    checkpoint_ref: null,
    resource_usage: { cpu_seconds: 4, memory_mb: 64, disk_bytes: 1024 },
    attempt_outcome: null,
    failure_code: null,
    retryable: true,
    diagnostic_artifact_refs: [artifactId],
  }],
  state_events: [{
    task_id: taskId,
    event_sequence: 1,
    previous_task_state: 'QUEUED',
    next_task_state: 'LEASED',
    reason_code: 'TASK_LEASED',
    actor_ref: 'worker-e2e',
    event_at: '2026-08-30T08:00:01Z',
    attempt_id: task.active_attempt_id,
  }],
  checkpoints: [{
    checkpoint_id: 'checkpoint_019a7f6d-5c00-7000-8000-000000000004',
    task_id: taskId,
    attempt_id: task.active_attempt_id,
    phase: 'SCANNING',
    sequence: 1,
    resume_token_hash: 'b'.repeat(64),
    input_hash: 'c'.repeat(64),
    handler_version: 'g009-e2e',
    storage_ref: { storage_backend: 'local_fs', storage_namespace: 'app', relative_path: 'staging/checkpoint.json', content_hash: 'd'.repeat(64), media_type: 'application/json', size_bytes: 42 },
    checkpoint_hash: 'e'.repeat(64),
    created_at: '2026-08-30T08:04:00Z',
    expires_at: '2026-08-30T09:04:00Z',
  }],
  diagnostic_artifact_refs: [artifactId],
};

function writeFile(filePath: string, content: string) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

async function buildFixture() {
  const fixtureDir = path.join(webRoot, 'test-results', 'operations-tasks-e2e');
  const distDir = path.join(fixtureDir, 'dist');
  const entryPath = path.join(fixtureDir, 'OperationsTasksApp.tsx');
  const htmlPath = path.join(fixtureDir, 'index.html');
  const rel = (target: string) => { const value = path.relative(fixtureDir, target).split(path.sep).join('/'); return value.startsWith('.') ? value : `./${value}`; };
  writeFile(entryPath, `
    import React from 'react';
    import { createRoot } from 'react-dom/client';
    import { BrowserRouter, Route, Routes } from 'react-router-dom';
    import '${rel(path.join(sourceRoot, 'index.css'))}';
    import OperationsTasksPage from '${rel(path.join(sourceRoot, 'pages/OperationsTasksPage.tsx'))}';
    createRoot(document.getElementById('root')!).render(
      <BrowserRouter>
        <Routes><Route path="/operations/tasks/:taskId?" element={<OperationsTasksPage />} /></Routes>
      </BrowserRouter>,
    );
  `);
  writeFile(htmlPath, '<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /></head><body><div id="root"></div><script type="module" src="/OperationsTasksApp.tsx"></script></body></html>');
  await viteBuild({ root: fixtureDir, base: '/', configFile: false, publicDir: false, logLevel: 'warn', plugins: [tailwindcss(), react()], define: { __APP_PACKAGE_VERSION__: JSON.stringify('e2e'), __APP_BUILD_TIME__: JSON.stringify('2026-08-30T00:00:00.000Z') }, build: { outDir: distDir, emptyOutDir: true, sourcemap: false } });
  return distDir;
}

async function serve(rootDir: string) {
  const server = createServer((request, response) => {
    const requestPath = decodeURIComponent((request.url || '/').split('?', 1)[0]);
    const relative = requestPath === '/' ? 'index.html' : requestPath.replace(/^\/+/, '');
    const filePath = path.resolve(rootDir, relative);
    const relativeToRoot = path.relative(rootDir, filePath);
    if (relativeToRoot.startsWith('..') || path.isAbsolute(relativeToRoot)) return response.writeHead(403).end();
    fs.readFile(filePath, (error, data) => {
      if (error) {
        if (!path.extname(filePath)) {
          return fs.readFile(path.join(rootDir, 'index.html'), (indexError, indexData) => {
            if (indexError) return response.writeHead(404).end();
            return response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end(indexData);
          });
        }
        return response.writeHead(404).end();
      }
      const types: Record<string, string> = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
      response.writeHead(200, { 'Content-Type': types[path.extname(filePath)] || 'application/octet-stream' }).end(data);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address() as AddressInfo;
  return { url: `http://127.0.0.1:${address.port}/`, close: () => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())) };
}

type MockApiOptions = { taskState?: string; commandDelayMs?: number };
type MockApiState = { commands: string[]; listRequests: number };

type E2EWindow = Window & {
  __emitTaskEventSourceError: () => void;
  __emitTaskStateChanged: () => void;
};

async function installControlledEventSource(page: Page) {
  await page.addInitScript(() => {
    class ControlledEventSource extends EventTarget {
      static instances: ControlledEventSource[] = [];
      readonly url: string;
      readyState = 1;
      onerror: ((event: Event) => void) | null = null;

      constructor(url: string) {
        super();
        this.url = url;
        ControlledEventSource.instances.push(this);
      }

      close() {
        this.readyState = 2;
      }
    }

    Object.defineProperty(window, 'EventSource', { configurable: true, writable: true, value: ControlledEventSource });
    (window as Window & { __emitTaskEventSourceError: () => void }).__emitTaskEventSourceError = () => {
      const source = ControlledEventSource.instances.at(-1);
      source?.onerror?.(new Event('error'));
    };
    (window as Window & { __emitTaskStateChanged: () => void }).__emitTaskStateChanged = () => {
      ControlledEventSource.instances.at(-1)?.dispatchEvent(new Event('task_state_changed'));
    };
  });
}

async function mockApis(page: Page, options: MockApiOptions = {}): Promise<MockApiState> {
  const state: MockApiState = { commands: [], listRequests: 0 };
  const taskPayload = options.taskState ? { ...task, task_state: options.taskState } : task;
  const detailsPayload = options.taskState ? { ...details, task: taskPayload } : details;
  await page.route('**/api/platform/v1/tasks**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === 'GET' && url.pathname.endsWith('/events')) return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': heartbeat\n\n' });
    if (request.method() === 'GET' && url.pathname.endsWith(`/tasks/${taskId}`)) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: detailsPayload, meta: { generated_at: task.created_at, request_id: 'req-e2e', schema_version: '1.0.0', data_snapshot_id: null, warnings: [] } }) });
    if (request.method() === 'POST') {
      state.commands.push(url.pathname);
      if (options.commandDelayMs) await new Promise((resolve) => setTimeout(resolve, options.commandDelayMs));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: taskPayload, meta: { generated_at: task.created_at, request_id: 'req-e2e', schema_version: '1.0.0', data_snapshot_id: null, warnings: [] } }) });
    }
    state.listRequests += 1;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [taskPayload], page: { cursor: null, next_cursor: null, has_more: false, limit: 50 }, meta: { generated_at: task.created_at, request_id: 'req-e2e', schema_version: '1.0.0', data_snapshot_id: null, warnings: [] } }) });
  });
  return state;
}

test.describe('Operations task page', () => {
  let browser: Browser;
  let baseURL: string;
  let closeServer: () => Promise<void>;

  test.beforeAll(async () => { browser = await chromium.launch(); const distDir = await buildFixture(); const server = await serve(distDir); baseURL = server.url; closeServer = server.close; });
  test.afterAll(async () => { await browser.close(); await closeServer(); });

  test('lists, filters, deep-links, renders details, and confirms cancel', async () => {
    const page = await browser.newPage({ baseURL, viewport: { width: 1280, height: 900 }, locale: 'zh-CN' });
    await mockApis(page);
    page.on('dialog', (dialog) => void dialog.accept());
    await page.goto('/operations/tasks?tab=active');
    await expect(page.getByTestId('operations-tasks-page')).toBeVisible();
    await expect(page.getByText('artifact_orphan_dry_run')).toBeVisible();
    await page.getByRole('tab', { name: /历史/ }).click();
    await expect(page).toHaveURL(/tab=history/);
    await page.getByLabel('任务类型').fill('artifact_orphan_dry_run');
    await expect(page).toHaveURL(/task_type=artifact_orphan_dry_run/);
    await page.getByRole('button', { name: /artifact_orphan_dry_run/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`/operations/tasks/${taskId}`));
    await expect(page.getByText('Attempt 1 · SCANNING')).toBeVisible();
    await expect(page.getByText('cpu_seconds: 4')).toBeVisible();
    await expect(page.getByText(artifactId)).toBeVisible();
    await expect(page.getByText('secret-hash-not-rendered')).toHaveCount(0);
    await page.getByRole('button', { name: '请求取消' }).click();
    await expect(page.getByRole('button', { name: '取消中…' })).toHaveCount(0);
    await page.screenshot({ path: test.info().outputPath('operations-tasks-desktop.png'), fullPage: true });
    await page.close();
  });

  test('recovers from an SSE disconnect and refreshes the query result', async () => {
    const page = await browser.newPage({ baseURL, viewport: { width: 1280, height: 900 }, locale: 'zh-CN' });
    const state = await mockApis(page);
    await installControlledEventSource(page);
    await page.goto('/operations/tasks?tab=active');
    await expect(page.getByRole('status')).toHaveText('实时事件已连接');
    await page.evaluate(() => (window as E2EWindow).__emitTaskEventSourceError());
    await expect(page.getByRole('status')).toHaveText('实时连接断开，15 秒轮询中');
    await page.evaluate(() => (window as E2EWindow).__emitTaskStateChanged());
    await expect(page.getByRole('status')).toHaveText('实时事件已连接');
    await expect.poll(() => state.listRequests).toBeGreaterThan(1);
    await page.close();
  });

  test('confirms retry and suppresses duplicate command submission', async () => {
    const page = await browser.newPage({ baseURL, viewport: { width: 1280, height: 900 }, locale: 'zh-CN' });
    const state = await mockApis(page, { taskState: 'RETRY_WAIT', commandDelayMs: 150 });
    await page.goto(`/operations/tasks/${taskId}?tab=failed`);
    await expect(page.getByRole('button', { name: '请求重试' })).toBeVisible();
    page.on('dialog', (dialog) => void dialog.accept());
    await page.getByRole('button', { name: '请求重试' }).click();
    await expect(page.getByRole('button', { name: '重试中…' })).toBeDisabled();
    await expect.poll(() => state.commands.filter((path) => path.endsWith('/retries')).length).toBe(1);
    await expect(page.getByRole('button', { name: '请求重试' })).toBeVisible();
    await page.close();
  });

  test('renders responsive mobile task view and keeps task context after reload', async () => {
    const page = await browser.newPage({ baseURL, viewport: { width: 390, height: 844 }, locale: 'zh-CN' });
    await mockApis(page);
    await page.goto(`/operations/tasks/${taskId}?tab=active&task_state=RUNNING`);
    await expect(page.getByText('任务运维')).toBeVisible();
    await expect(page.getByText('Attempt 1 · SCANNING')).toBeVisible();
    await page.reload();
    await expect(page).toHaveURL(/task_state=RUNNING/);
    await expect(page.getByText('Checkpoint')).toBeVisible();
    await page.screenshot({ path: test.info().outputPath('operations-tasks-mobile.png'), fullPage: true });
    await page.close();
  });
});


