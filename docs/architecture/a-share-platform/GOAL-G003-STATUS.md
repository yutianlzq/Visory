# Visory-G003 / WP-0001 进度与验收记录

最后更新：2026-08-29

## 1. 当前状态

- Goal：`Visory-G003`
- Work Package：`WP-0001 Contract Registry 与公共 Schema`
- 状态：`IN_PROGRESS`
- 基线：`origin/main=e20cdb384d03655320238b2ddaf001a8dfa8a18d`
- 工作分支：`goal/g003-wp-0001-contract-registry`
- 已验证 Work Package：`0/45`

`VERIFIED` 仅在公共契约实现、Golden/拒绝测试、确定性 Schema 导出、本地完整门禁、Pull Request 和 GitHub Governance/Python/Web 三个阻断 Job 全部通过后更新。

## 2. 范围

本 Goal 仅实现 WP-0001：

- `src/schemas/platform/` 公共契约包；
- C-001 的身份、时间、状态、版本、Revision 与确定性 Hash 基础语义；
- C-002 的 `<prefix>_<uuidv7>` 资源 ID 与结构化 `ResourceRef`；
- C-003 的逻辑 `StorageRef` 校验；
- 可查询的 Contract Registry；
- `schemas/platform/` 确定性 JSON Schema 与 Registry 导出；
- `tests/golden/platform/contracts/` 成功、Correction 与拒绝 Payload；
- 后端 CI 中的 Schema drift check。

明确不包含 PostgreSQL、Alembic、API 改造、前端、Artifact Publisher、真实文件写入、部署、采集或其他 Work Package。

## 3. 当前实现证据

### 代码与生成物

- `src/schemas/platform/`：严格、不可变且 `extra="forbid"` 的公共模型与 Registry；
- `scripts/export_platform_contracts.py`：生成或 `--check` 检查确定性导出；
- `schemas/platform/`：9 个公共对象 JSON Schema 与 1 个 Registry 清单；
- `tests/platform/`：公共契约、UUIDv7、Hash、StorageRef、Registry、导出和 Golden 测试；
- `tests/golden/platform/contracts/`：成功、Correction 与拒绝样例。

### 已执行验证

| 命令 | 结果 |
| --- | --- |
| `.tmp/g003-venv/Scripts/python.exe -m pytest tests/platform -q`（实现前） | Red：9 个模块因公共契约尚未实现而收集失败 |
| `C:/Users/lzq11/.codex/tmp/visory-g003-wp0001/g003-venv/Scripts/python.exe -m pytest tests/platform -q --disable-warnings` | 93 passed |
| `.../g003-venv/Scripts/python.exe -m flake8 src/schemas/platform scripts/export_platform_contracts.py tests/platform --count --statistics` | 0 issues |
| `.../g003-venv/Scripts/python.exe scripts/export_platform_contracts.py --check` | 通过，导出无漂移 |
| `python scripts/check_ai_assets.py` | 通过 |
| `python scripts/check_visory_baseline.py` | 通过：574 个相对链接、0 个断链、0 个 Secret 命中 |
| `bash scripts/ci_gate.sh syntax` | 通过 |
| `bash scripts/ci_gate.sh deterministic` | 通过 |
| `pytest -m "not network" ...` | Windows：6357 passed、79 failed、5 skipped；失败集中于 POSIX process-group、Windows SQLite/文件锁和既有时序路径，待 GitHub Linux CI 裁决 |
| `npm ci && npm run lint && npm run build`（`apps/dsa-web`） | 通过 |
| Legacy API 定向回归 | 32 passed（Pydantic API Schema、health、CI workflow contract） |

## 4. 待完成验收

- 完整 diff、边界和生成物审计；
- commit、普通 push、Pull Request；
- 在干净 Linux checkout 中执行原始 `scripts/ci_gate.sh`；本地 Windows 已完成其 syntax/deterministic 阶段和实际仓库范围 flake8，完整离线套件的 79 个平台无关失败交由 Linux CI 对照；
- GitHub Governance、Python、Web 三个阻断 Job 全绿；
- 全绿后将本文件和 `IMPLEMENTATION-STATUS.md` 更新为 `VERIFIED` / `1/45`。

## 5. 风险与回滚

- 风险：公共模型尚未接入现有 API，因此本 WP 不改变 Legacy API 行为；后续 WP 接入时仍需显式兼容投影。
- 风险：Registry 目前只登记 WP-0001 的 C-001 至 C-003 公共对象，不代表 C-004 至 C-013 已实现。
- 回滚：在未合并前关闭 PR 或删除目标分支；合并后使用普通 revert 撤销本 WP 提交。导出文件由脚本生成，不应手工修补。
