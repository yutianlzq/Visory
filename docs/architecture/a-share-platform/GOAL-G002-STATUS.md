# Visory-G002 进度与验收记录

最后更新：2026-08-29

## 1. 当前结论

`Visory-G002: daily_stock_analysis 底座导入与可运行工程基线` 已完成。

- 项目仓库：`https://github.com/yutianlzq/Visory`
- 工作分支：`goal/g002-dsa-baseline-import`
- Visory 起始基线：`c4b108f0055fb779cfb5a030fab5d08bdcdd07ca`
- G002 核心导入提交：`23bb3d18276f991a9a18f4de41ae9bb83f94058a`
- 远端交付分支：`origin/goal/g002-dsa-baseline-import`
- DSA 固定提交：`fb4735a1055caefa2396982af3b09121feb9ff30`
- DSA 固定 Git tree：`1fa51b5f3fde0084af85d6ad4e463aed3610cd0a`
- G001：`COMPLETE`
- G002：`COMPLETE`
- DSA Baseline：`IMPORTED / VERIFIED`
- 目标架构 Work Package：`0/45` 已实现，`45/45 NOT_STARTED`
- 下一 Work Package：`WP-0001 Contract Registry 与公共 Schema`

G002 只导入并验证 DSA 迁移底座，没有把 Legacy SQLite、内存 Task Queue 或现有 DSA API/UI 声明为 Visory 目标架构已经实现，也没有开始 WP-0001、正式采集、部署或发布。

## 2. 导入与安全边界

### 已导入

- Python/FastAPI 运行底座：`main.py`、`server.py`、`webui.py`、`src/`、`api/`、`bot/`、`data_provider/`、`strategies/`、`templates/`。
- Web/Desktop 客户端：`apps/dsa-web/`、`apps/dsa-desktop/`。
- 构建、测试与容器资产：`scripts/`、`docker/`、`tests/`、依赖与项目配置。
- CI 测试支撑：`.github/requirements-ci.txt`、`.github/ci-test-durations.json`、`.github/scripts/ai_review.py`、`.github/scripts/build_release_notes.py`。
- 上游文档：重定位到 `docs/upstream/daily_stock_analysis/`。
- DSA MIT 许可证与第三方归属：`third_party/`。

### 未启用

- `.github/workflows/` 只包含 Visory 自己的 `ci.yml`。
- 上游每日分析、CI、Docker 发布等 4 个 workflow 仅以只读证据归档在 `docs/upstream/daily_stock_analysis/workflows/`，不会被 GitHub Actions 发现或执行。
- Visory CI 仅支持 `pull_request` 与 `workflow_dispatch`，顶层权限为 `contents: read`，不读取 secrets，不执行 schedule、release、publish、deploy 或正式数据采集。
- `upstream/daily_stock_analysis/` 与 `references/repos/` 保持本地只读、Git/Docker 排除且不提交。

## 3. 固定上游完整性

固定提交通过 Git Tree/Blob 重构，并按 Git blob SHA 逐文件验签：

- tree `truncated=false`
- 预期 blob：1126
- 匹配 blob：1126
- 缺失：0
- SHA 不匹配：0
- 额外文件：0

正式身份与路径清单见 `upstream-baseline/daily_stock_analysis.yaml`。

## 4. Python 验收

环境：Windows 11、Python 3.12.9；固定 DSA 与 Visory 使用相互独立的 venv。

| 检查 | 固定 DSA | Visory | 结论 |
| --- | --- | --- | --- |
| 依赖安装与 `pip check` | 通过 | 通过 | 无依赖回归 |
| `compileall` 与核心 import smoke | 通过 | 通过 | 可编译、可导入 |
| `pytest -m "not network" -ra` | 6265 passed, 83 failed, 5 skipped, 4 deselected | 6263 passed, 85 failed, 5 skipped, 4 deselected | 见失败归一化 |
| Visory 安全边界核心定向契约 | 不适用 | 78 passed | 通过 |
| 最终文档/workflow/打包契约集合 | 不适用 | 127 passed, 5 platform failures | 3 项因 Windows 无 `sh`，2 项因 WSL `E_ACCESSDENIED`；无文档或 CI 契约失败 |

### 失败归一化

原始完整日志的节点差集为：Visory-only 3 项、baseline-only 1 项。

- `test_output_too_large_kills_process_group`：对称重跑时固定 DSA 与 Visory 均通过，判定为完整套件时序波动，不构成导入回归。
- 两个 `test_macos_signature_audit_*`：对称重跑时固定 DSA 与 Visory 均因当前 `C:\Windows\system32\bash.exe`/WSL 返回 `E_ACCESSDENIED` 失败，属于相同 Windows/WSL 环境限制。
- `test_litellm_openai_prompt_cache_key_is_not_passed_through_without_verified_capture`：固定 DSA 完整日志失败，Visory 通过，不是新增失败。

因此在相同源码测试和相同环境限制归一化后：

```text
baseline_regression_delta=0
```

完整 Visory 日志中的统计与节点差集已提取到本记录；验收完成后已删除 `.tmp/` 临时目录及日志，不作为提交内容。

## 5. Web 验收

固定 DSA 与 Visory 均从同一 lockfile 执行：

```text
npm ci
npm run lint
npm run build
```

结果：两边均通过；Vite 均转换 3236 个模块并生成 production build。

```text
web_lint_build_regression_delta=0
```

首次运行因受限环境无法写系统 npm cache 且网络请求返回 `EACCES`；改用可写临时 cache 并在获批联网后完成安装。固定 DSA build 另因沙箱拒绝临时目录读取而以获批提升权限对称重跑通过。

## 6. 治理与仓库验收

- `python scripts/check_ai_assets.py`：通过，输出 `[ai-assets] OK`。
- `python scripts/check_visory_baseline.py`：通过；runtime paths 8、reference projects 10、tracked external sources 0、license/notice 2、active workflows 1、secret findings 0、relative links 571、broken links 0。
- `python -m py_compile scripts/check_ai_assets.py scripts/check_visory_baseline.py`：通过。
- `bash scripts/ci_gate.sh`：本地未启动；`C:\Windows\system32\bash.exe` 在创建 WSL 实例时返回 `Bash/Service/CreateInstance/E_ACCESSDENIED`。Linux CI 仍将该脚本作为阻断门禁。
- `git fetch --all --prune`：通过，远端 refs 无新增或删除。
- 全量 `git diff --cached --check`：因固定 DSA 上游原始文件包含既有 trailing whitespace 与 EOF 空行而返回非零；为保持与固定 Git blob 的审计关系，不对上游快照做无关格式化。Visory 第一方与本轮适配文件的范围化 `git diff --cached --check -- <paths>` 已通过。
- 远端交付核验：`goal/g002-dsa-baseline-import` 已推送；本地跟踪分支 ahead/behind 为 `0/0`，GitHub 已确认核心导入提交 `23bb3d18276f991a9a18f4de41ae9bb83f94058a` 可访问。

本地 Windows 的 WSL/bash、文件锁和 POSIX 进程组限制已与固定 DSA 双基线证据分开记录，没有伪装为全部通过。

## 7. 状态与后续边界

- G001 保持 `COMPLETE`。
- G002 完成后，DSA 仅成为可运行、可验证的迁移底座。
- 45 个目标 Work Package 全部保持 `NOT_STARTED`，implemented work packages 为 `0/45`。
- 下一项只能是 `WP-0001 Contract Registry 与公共 Schema`，需要新的明确目标后才能开始。
- 本 Goal 不提交 `upstream/` 或 `references/repos/`，不直接推送 `main`，不部署、不采集、不发布。

## 8. 回滚

G002 以独立目标分支交付。回滚时优先 revert 本 Goal 的提交或删除该未合入分支；不得用 force-push 覆盖 `main`，不得修改本地只读参考快照。运行数据、node_modules、构建产物、日志与临时验收目录均不属于提交内容。
