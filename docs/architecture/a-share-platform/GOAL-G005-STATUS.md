# Visory-G005 / WP-0003 进度与验收记录

最后更新：2026-08-29

## 1. 当前状态

- Goal：`Visory-G005`
- Work Package：`WP-0003 API Envelope、Error 与生成类型`
- Goal 状态：`IN_PROGRESS`
- Work Package 状态：`IN_PROGRESS`
- 固定基线：`main=75132082544239b011682d37cd626a29bca15b49`
- 工作分支：`goal/g005-wp-0003-api-envelope-types`
- 已验证 Work Package：`2/45`
- Alembic head：`0001_wp0002_baseline`（本 Goal 不新增 Migration）

本分支已核验本地 HEAD、`origin/main` 与 GitHub `main` 均为固定基线 `7513208`，且开始时工作区干净。WP-0003 的实现、完整回归和 GitHub 阻断 CI 尚未完成，因此不得标记为 `VERIFIED`，implemented work packages 继续保持 `2/45`。

## 2. 目标范围

本 Goal 仅实现 C-010 成功/错误 Envelope、HTTP Request ID 生成与传播、平台异常映射、OpenAPI 示例、确定性前端生成类型及 Legacy Adapter/路由边界。现有 `/api/v1` Legacy 响应、健康检查、认证、Agent Chat 业务 `request_id`、SSE 和前端消费契约不得被统一包裹或破坏。

明确不实现身份、Artifact、Task、业务数据表、业务 Migration、正式认证、Turnstile、Cloudflare、NPM、部署或任何后续 Work Package；不修改 `upstream/`、`references/`。

## 3. 验收状态

- C-010 Golden / rejected payload：待实现与验证；
- 指定 HTTP 状态和未知异常：待实现与验证；
- Request ID Header / Envelope / Error / structured log 一致性：待实现与验证；
- OpenAPI 示例与前端类型确定性生成：待实现与验证；
- Legacy Smoke、完整回归和 GitHub 三项阻断 Job：待验证；
- PR：待创建，未经 owner 明确批准不得合并。
