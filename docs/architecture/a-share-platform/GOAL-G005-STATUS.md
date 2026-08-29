# Visory-G005 / WP-0003 进度与验收记录

最后更新：2026-08-30

## 1. 当前状态

- Goal：`Visory-G005`
- Work Package：`WP-0003 API Envelope、Error 与生成类型`
- Goal 状态：`READY_TO_MERGE`
- Work Package 状态：`VERIFIED`
- 固定基线：`main=75132082544239b011682d37cd626a29bca15b49`
- 工作分支：`goal/g005-wp-0003-api-envelope-types`
- 已验证 Work Package：`3/45`
- Alembic head：`0001_wp0002_baseline`（本 Goal 不新增 Migration）

本分支已核验本地 HEAD、`origin/main` 与 GitHub `main` 均为固定基线 `7513208`，且开始时工作区干净。C-010 实现、本地定向验收和 PR #4 首轮 GitHub 三项阻断 CI 已全部通过，因此 WP-0003 标记为 `VERIFIED`，implemented work packages 更新为 `3/45`。owner 已批准在本状态提交触发的第二轮 CI 全绿后以普通 merge commit 合入。

## 2. 目标范围

本 Goal 仅实现 C-010 成功/错误 Envelope、HTTP Request ID 生成与传播、平台异常映射、OpenAPI 示例、确定性前端生成类型及 Legacy Adapter/路由边界。现有 `/api/v1` Legacy 响应、健康检查、认证、Agent Chat 业务 `request_id`、SSE 和前端消费契约不得被统一包裹或破坏。

明确不实现身份、Artifact、Task、业务数据表、业务 Migration、正式认证、Turnstile、Cloudflare、NPM、部署或任何后续 Work Package；不修改 `upstream/`、`references/`。

## 3. 实现结果

- 公共 Schema：在 `src/schemas/platform/api.py` 定义严格的成功、列表、错误 Envelope、Meta、Page 与公开错误对象，Schema 版本为 `1.0.0`；
- 平台边界：新增 `/api/platform/v1`，本 WP 不添加业务资源；Legacy `/api/v1`、健康检查、认证、validation 与 Agent Stream/SSE body 保持原语义；
- Request ID：使用 `X-Request-ID` 与 `req_<32 lowercase hex>`；只传播单个合法 ASCII 值，缺失、重复、非法或非 ASCII 输入均生成新值；Header、Envelope、Error 与结构化日志共享同一 ID；
- 错误映射：实现 400、401、403、404、409、422、429、503 与未知异常 500；公开响应和平台未知异常日志不回显堆栈、路径、SQL、DSN、Secret 或原始异常文本；
- 生成链：`scripts/export_platform_contracts.py` 从公共 Schema 确定性生成 `schemas/platform/C-010.openapi.json` 与 `apps/dsa-web/src/types/generated/platform-api.ts`，`--check` 检测 drift；生成 TypeScript 固定 LF；
- Migration：本 Goal 未新增数据库对象或 revision，Alembic head 仍为 `0001_wp0002_baseline`。

## 4. 本地验收证据

- C-010 平台 API 契约测试：`35 passed`；
- 平台契约与 Legacy/API 定向回归：`112 passed`；
- Python compileall、flake8 critical checks、生成链 `--check` 与 `git diff --check`：通过；
- Web：`npm ci`、`npm run lint`、`npm run build` 通过，Vite 构建 `3236 modules transformed`；
- 治理：clean worktree 中 `check_ai_assets.py`、`check_visory_baseline.py` 通过，`broken_relative_links=0`、`imported_secrets=0`；
- Windows clean-worktree 完整 `bash scripts/ci_gate.sh`：`6428 passed, 83 failed, 11 skipped, 4 deselected, 572 subtests passed`。失败集中于 native Windows 不支持的 POSIX 进程组/管道、环境相关 Codex CLI、SQLite 文件锁、Git Bash macOS 脚本路径及一个时序测试；固定基线同环境 524 项代表性对照为 `441 passed, 81 failed, 2 skipped`，分支对应对照为 `440 passed, 82 failed, 2 skipped`，额外的 storage 失败单独重跑通过。该结果不伪装为全绿，最终阻断裁决由 GitHub Linux CI 给出；
- 本机未配置一次性 PostgreSQL，因此 WP-0002 的 5 项 PostgreSQL 集成测试本地跳过；本 Goal 未修改数据库层或 Migration。

## 5. GitHub 验收与合入状态

PR #4 首轮 GitHub Actions Run `33265028192`：

- Governance and repository boundaries：通过；
- Python deterministic gate：通过，`6522 passed, 4 deselected, 49 warnings, 572 subtests passed`；
- Web lint and build：通过；
- Python Job 使用 Ubuntu 24.04、Python 3.11.16 与一次性 PostgreSQL `16.15` service，服务容器、临时网络和测试数据库均由 CI 清理；
- `scripts/ci_gate.sh` 完整通过，包含 deterministic export drift、Legacy 完整离线回归与 WP-0002 PostgreSQL 集成基线。

当前结论：WP-0003 已达到 `VERIFIED`，M0 三个 Work Package 全部验证完成。owner 已批准后续普通合并；本状态提交 push 后仍须等待第二轮 Governance、Python、Web 三项 CI 全绿，随后才可合并 PR #4。不得 force push、改写历史、部署或启动 WP-0101。

## 6. 回滚

- 合并前：关闭 PR #4；
- 合并后：普通 revert PR #4 的 merge commit；
- 本 Goal 无数据库 revision、业务表或数据写入，不需要 Alembic downgrade；
- 生成文件必须通过 `python scripts/export_platform_contracts.py` 恢复，不手工编辑。
