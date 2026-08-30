# Visory-G009 / WP-0104 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G009`
- Work Package：`WP-0104 Operations 最小页面`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 固定基线：`main=ea4f8b1f27b79eb64079321d28951cac83a16f79`
- 工作分支：`goal/g009-wp-0104-operations-task-page`
- 已验证 Work Package：`6/45`
- 目标 Migration head：`0004_wp0103_durable_task_control_plane`（本 Goal 未新增 Migration）

## 2. 已实现

- 新增 Task 列表查询与稳定创建时间/Task ID Cursor，支持活跃、阻塞、失败、历史及状态、类型、优先级、请求者、时间和资源筛选；
- 扩展 Task 详情以返回 Checkpoints 与诊断 Artifact ID 投影；API 对外移除 Lease Token Hash；
- 新增全局和单 Task 可恢复 State Event SSE，支持 `Last-Event-ID` / `after_event_id`，SSE 仅作通知，前端收到后重新查询；
- 新增 Operations `/operations/tasks/:taskId?` 页面、侧栏入口、Tab/深链接、取消/重试交互、SSE 断线低频轮询降级；
- 新增 C-010 `TaskListQuery`、`TaskEventRecord` Schema、Registry、OpenAPI 和前端类型确定性导出。

## 3. 当前验证

- 平台测试：260 passed，5 skipped；
- Web lint：通过；
- Web build：通过；
- 真实 PostgreSQL 集成：当前环境未提供可用隔离实例，测试全部 skipped；
- 端到端 Playwright：尚未执行。

## 4. 未完成与风险

- 需要在 Linux CI 复核 Governance、Python、Web 三项阻断 Job；
- 需要补充真实 PostgreSQL 列表/SSE 集成测试和 Playwright 关键旅程；
- SSE 当前发送已存在事件后以 heartbeat 结束，生产长连接策略留待后续 Operations/部署工作；
- Legacy Task Queue 保持不变；无 Artifact 下载、任意路径访问或 `/data` 写入。

## 5. 回滚

- 回滚代码：revert 本 Goal 分支 commit；
- 回滚 Schema：本 Goal 无 Migration，不需要数据库 downgrade；
- 回滚前端：移除 `/operations/tasks` 路由、侧栏入口和页面/API 客户端即可。

