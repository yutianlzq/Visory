# Visory-G009 / WP-0104 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G009`
- Work Package：`WP-0104 Operations 最小页面`
- Goal 状态：`COMPLETE / MERGED`
- Work Package 状态：`VERIFIED`
- 固定基线：`main=cc55b1e9624c64247e1005d95dfb008108d4bb6d`
- 工作分支：`goal/g009-wp-0104-real-backend-journey`
- 合并提交：PR #9 merge `6b90bb1dba8aaf1925ef32c0c73bf1bc03dae856`；PR #13 merge `148f8d903c5e052203ce670951e3e5509287af6e`；PR #15 merge `9c03666740a1e7a90a616a2d774efc57ca5a0e6b`；最终 CI Run `33329710242` 的 Governance、Python、Web 三项阻断 Job 全部成功
- 已验证 Work Package：`7/45`
- 目标 Migration head：`0004_wp0103_durable_task_control_plane`（本 Goal 未新增 Migration）

## 2. 已实现

- 新增 Task 列表查询与稳定创建时间/Task ID Cursor，支持活跃、阻塞、失败、历史及状态、类型、优先级、请求者、时间和资源筛选；
- 扩展 Task 详情以返回 Checkpoints 与诊断 Artifact ID 投影；API 对外移除 Lease Token Hash；
- 新增全局和单 Task 可恢复 State Event SSE，支持 `Last-Event-ID` / `after_event_id`，SSE 仅作通知，前端收到后重新查询；
- 新增 Operations `/operations/tasks/:taskId?` 页面、侧栏入口、Tab/深链接、取消/重试交互、SSE 断线低频轮询降级；
- 新增 C-010 `TaskListQuery`、`TaskEventRecord` Schema、Registry、OpenAPI 和前端类型确定性导出；
- 补充 URL 持久化筛选、时区双显时间、Task ID 复制、Cancel/Retry 确认、resource usage 与诊断 Artifact 投影；
- 新增本地临时 fixture 驱动的 Playwright 页面旅程测试，覆盖列表、筛选、深链接、详情、取消确认、移动端和刷新保持上下文。

## 3. 当前验证

- 平台测试：260 passed，5 skipped；
- Web lint：通过；
- Web build：通过（`npm run build`，2026-08-30）；
- Playwright：`npx playwright test e2e/operations-tasks.spec.ts --project=chromium --reporter=line`，`6 passed`；覆盖 SSE 断线/恢复、Retry 确认/重复提交保护、C-010 错误码/Request ID 展示和 Tab/筛选键盘操作；
- 平台测试：`.venv\Scripts\python.exe -m pytest tests/platform -q`，`260 passed, 5 skipped`；
- 真实 PostgreSQL 集成：本地临时 PostgreSQL 16 Docker 实例上目标测试 `1 passed`、集成目录 `31 passed`；清理临时实例后默认集成命令为 `31 skipped`。
- 页面 E2E 使用本地临时 fixture 与 route mock，不写真实 `/data`；新增真实认证后端 Playwright 旅程，使用临时 PostgreSQL 与临时凭据文件。

## 4. 未完成与风险

- PR #9、PR #12、PR #13、PR #14、PR #15 已合并；最终 Run `33329710242` 的 Governance、Python、Web 三项阻断 Job 全部成功；
- 真实认证后端 HTTP/ASGI 与浏览器 Playwright 旅程已覆盖登录 Cookie、平台 API 保护和 Operations 页面访问；真实服务端 SSE replay 已覆盖首次连接、取消后增量事件、`Last-Event-ID` / `after_event_id` 补读、无重复无丢失和连接池清理；错误展示仍以受控 C-010 Envelope 为主；
- 真实 PostgreSQL 列表/SSE 集成已在本地临时 PostgreSQL 16 容器执行；GitHub Actions Run `33329710242` 已重复通过 Python 确定性门禁。
- SSE 当前发送已存在事件后以 heartbeat 结束，生产长连接策略留待后续 Operations/部署工作；
- Legacy Task Queue 保持不变；无 Artifact 下载、任意路径访问或 `/data` 写入。

## 5. 回滚

- 回滚代码：revert 本 Goal 分支 commit；
- 回滚 Schema：本 Goal 无 Migration，不需要数据库 downgrade；
- 回滚前端：移除 `/operations/tasks` 路由、侧栏入口和页面/API 客户端即可。
