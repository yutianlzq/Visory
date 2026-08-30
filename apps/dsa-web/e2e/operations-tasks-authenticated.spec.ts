import { expect, test } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;

test.skip(!smokePassword, 'Set DSA_WEB_SMOKE_PASSWORD to run the real authenticated backend journey.');

test('authenticated user can open Operations Tasks against the real FastAPI backend', async ({ page }) => {
  await page.goto('/login');
  await expect(page.locator('#password')).toBeVisible();
  await page.locator('#password').fill(smokePassword!);
  await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/v1/auth/login') && response.status() === 200),
    page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ }).click(),
  ]);
  await page.waitForURL('/');

  const createResult = await page.evaluate(async () => {
    const response = await fetch('/api/platform/v1/tasks', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `e2e-real-${Date.now()}` },
      body: JSON.stringify({
        task_type: 'artifact_orphan_dry_run',
        requested_by: 'owner:operations-e2e',
        requirements: { worker_kind: 'maintenance' },
      }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(createResult.status).toBe(200);
  const taskId = createResult.body.data.task_id as string;

  await page.goto(`/operations/tasks/${encodeURIComponent(taskId)}?tab=active`);
  await expect(page.getByTestId('operations-tasks-page')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'artifact_orphan_dry_run' })).toBeVisible();
  await expect(page.getByLabel('任务详情').getByText('QUEUED', { exact: true })).toBeVisible();
  await expect(page.getByText(taskId)).toBeVisible();
  await expect(page.getByRole('status')).toHaveText('实时事件已连接');

  const authenticatedApi = await page.context().request.get('/api/platform/v1/tasks');
  expect(authenticatedApi.status()).toBe(200);
});
