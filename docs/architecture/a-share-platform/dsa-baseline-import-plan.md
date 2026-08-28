# Daily Stock Analysis 底座导入计划与完成记录

最后更新：2026-08-28

## 1. 目标与固定基线

- 上游仓库：`https://github.com/ZhuLinsen/daily_stock_analysis`
- 正式导入提交：`fb4735a1055caefa2396982af3b09121feb9ff30`
- 固定提交时间：`2026-08-25T14:54:01Z`
- 固定 Git tree：`1fa51b5f3fde0084af85d6ad4e463aed3610cd0a`
- 历史本地只读快照：`96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee`
- Visory 起始基线：`c4b108f0055fb779cfb5a030fab5d08bdcdd07ca`
- 交付分支：`goal/g002-dsa-baseline-import`
- 完成状态：`IMPORTED / VERIFIED`

本目标只建立可安装、可构建、可执行确定性验证的 DSA 工程底座，不实现 WP-0001，不启动正式数据采集，不部署服务器，也不改变 45 个 Work Package 的实现状态。

## 2. 固定提交取得与完整性证据

由于直接浅层 `git fetch` 和 codeload ZIP 在执行时的网络环境下无法可靠完成，采用可审计的 Git Tree/Blob 重构法：

1. 通过 GitHub API 获取两个提交的 commit metadata 和递归 Git tree；两棵 tree 均为 `truncated=false`。
2. 验证 `upstream/daily_stock_analysis/` 历史只读快照：1113 个 blob 中 1112 个内容 SHA 完全匹配，唯一差异为 Windows 下物化成普通文件的 `CLAUDE.md` 符号链接。
3. 将历史快照复制到系统临时目录，不修改仓库内只读快照。
4. 根据 Git tree 差异下载 13 个新增 blob、78 个变更 blob，并按 mode `120000` 的链接目标内容修正 `CLAUDE.md`。
5. 使用 Git blob 算法对固定基线逐文件验签。

最终固定基线：1126/1126 blob 匹配，缺失 0、SHA 不匹配 0、额外文件 0。

## 3. 为什么选择 `fb4735` 而不是 `96bc532`

`96bc532` 只作为 Visory 已保存的历史审计快照，不能代替本 Goal 明确指定的正式导入提交。`fb4735` 相对历史快照包含 13 个新增文件和 78 个更新文件，覆盖 Futu 数据源、指数路由、新闻证据、Web 意图解析、报告展示及相应回归测试等修复。

G002 固定后不继续追踪浮动 HEAD；后续同步必须新建独立 Goal，显式选择 commit 并重新执行 tree/blob 验签和双基线验证。

## 4. 最终导入清单

### 4.1 原路径导入

- 入口与依赖：`main.py`、`server.py`、`webui.py`、`requirements.txt`、`pyproject.toml`、`setup.cfg`
- 安全配置模板：`.env.example`、`.gitattributes`
- 后端与运行模块：`src/`、`api/`、`bot/`、`data_provider/`、`strategies/`、`templates/`
- 客户端：`apps/dsa-web/`、`apps/dsa-desktop/`
- 工程与构建辅助：`docker/`、`scripts/`
- 回归测试：`tests/`
- CI 测试支撑：`.github/requirements-ci.txt`、`.github/ci-test-durations.json`、`.github/scripts/ai_review.py`、`.github/scripts/build_release_notes.py`

桌面端源码随运行底座保留，以保持上游打包资产和确定性测试完整；G002 不执行桌面发布，也不启用任何上游发布 workflow。

### 4.2 重定位导入

- 上游 `LICENSE` → `third_party/licenses/daily_stock_analysis-MIT.txt`
- 上游 `README.md` → `docs/upstream/daily_stock_analysis/README.md`
- 上游 `docs/**` → `docs/upstream/daily_stock_analysis/**`
- 上游 `SKILL.md` → `docs/upstream/daily_stock_analysis/SKILL.md`
- 上游 `THIRD_PARTY_NOTICES.md` 归属信息 → `third_party/NOTICE.md`

### 4.3 非激活 workflow 证据

以下固定上游 workflow 复制到 `docs/upstream/daily_stock_analysis/workflows/`，仅供契约测试和迁移审计：

- `00-daily-analysis.yml`
- `ci.yml`
- `docker-publish.yml`
- `ghcr-dockerhub.yml`

它们不在 `.github/workflows/` 下，不会被 GitHub Actions 启用。

### 4.4 Visory 第一方新增

- `upstream-baseline/daily_stock_analysis.yaml`
- `third_party/NOTICE.md`
- `.github/workflows/ci.yml`
- `scripts/check_visory_baseline.py`
- `docs/architecture/a-share-platform/GOAL-G002-STATUS.md`

## 5. 排除与冲突边界

以下上游资产不直接覆盖或启用：

- `.claude/**`、上游 `AGENTS.md`、`CLAUDE.md`：不覆盖 Visory AI 协作单一真源。
- 上游 `.github/workflows/**`：不复制到活动 workflow 目录；只有上述 4 个文件在 docs 下归档。
- 上游仓库模板、CODEOWNERS、FUNDING、release 配置和其余自动化脚本：不导入。
- 上游 `.gitignore`、`.dockerignore`：不覆盖，只把必要运行产物忽略项并入 Visory 规则。
- 上游 `README.md`、`LICENSE`、`docs/CHANGELOG.md`：分别重定位，避免覆盖 Visory 首页、根许可证和第一方 CHANGELOG。

无 `.env`、Token、Cookie、数据库、缓存、报告、日志、node_modules、构建产物或运行数据进入提交。

## 6. LICENSE / NOTICE

Visory 根 `LICENSE` 保持不变。DSA 代码保留 MIT 归属，完整许可证文本在 `third_party/licenses/daily_stock_analysis-MIT.txt`；`third_party/NOTICE.md` 记录来源、固定提交、导入范围、许可证和 AlphaSift 衍生声明。任何后续同步都必须保留该归属链。

## 7. Workflow 安全策略

活动 `.github/workflows/` 只有 Visory `ci.yml`：

- 触发器：`pull_request`、`workflow_dispatch`
- 顶层权限：`contents: read`
- Job：`governance`、`backend`、`web`
- checkout：`persist-credentials: false`
- 不读 secrets
- 不包含 `push`、`schedule`、`release`、镜像发布、桌面发布、数据采集或服务器部署

归档 workflow 只是文件证据，不是可执行配置。

## 8. 验证结果

### 8.1 Python 双基线

| 检查 | 固定 DSA | Visory |
| --- | --- | --- |
| 依赖安装与 `pip check` | 通过 | 通过 |
| `compileall` 与核心 import smoke | 通过 | 通过 |
| `pytest -m "not network" -ra` | 6265 passed, 83 failed, 5 skipped, 4 deselected | 6263 passed, 85 failed, 5 skipped, 4 deselected |

原始失败节点差集为 Visory-only 3、baseline-only 1。对 3 个 Visory-only 节点做同命令、同环境对称重跑后：

- 进程组输出上限测试两边均通过，属于完整套件时序波动；
- 两个 macOS 签名测试两边均因当前 Windows/WSL bash `E_ACCESSDENIED` 失败；
- baseline-only 的 prompt cache 测试在 Visory 通过。

归一化结论：

```text
baseline_regression_delta=0
```

Visory 安全边界相关 78 项定向契约测试全部通过。

### 8.2 Web 双基线

固定 DSA 与 Visory 均完成：

```text
npm ci
npm run lint
npm run build
```

两边 lint/build 均通过，Vite 均转换 3236 个模块：

```text
web_lint_build_regression_delta=0
```

### 8.3 仓库与治理

最终门禁包括：

- 文档相对链接 broken=0
- `references/manifest.yaml` 项目计数 10/10
- `git ls-files references/repos upstream` 跟踪数 0
- 高置信 secret 命中 0
- 活动 workflow 数 1，unsafe trigger/secret/publish/deploy 0
- `python scripts/check_ai_assets.py`
- `python scripts/check_visory_baseline.py`

完整证据与环境限制见 [Visory-G002 进度与验收记录](GOAL-G002-STATUS.md)。

## 9. 完成后的真实状态

- Visory-G001：`COMPLETE`
- Visory-G002：`COMPLETE`
- DSA Baseline：`IMPORTED / VERIFIED`
- Implemented Work Packages：`0/45`
- WP-0001：`NOT_STARTED`
- 其余 44 个 WP：`NOT_STARTED`
- 下一 WP：`WP-0001 Contract Registry 与公共 Schema`

## 10. 回滚与后续同步

G002 以独立目标分支交付。提交后优先通过 revert 或删除未合入分支回滚，不使用 force-push，不 reset/stash 覆盖用户工作，不修改 `upstream/daily_stock_analysis/`。

后续同步流程：

1. 显式选择新目标 commit，禁止浮动追踪 HEAD。
2. 在新的干净临时目录取得 Git tree 并逐 blob 验签。
3. 生成当前 imported commit → 新 commit 的 path/SHA/mode 差异与冲突报告。
4. 继续保护 Visory 根治理、架构文档、许可证、参考边界和安全 workflow。
5. 重跑 Python/Web 双基线并更新 manifest、NOTICE、CHANGELOG 和 Goal 状态。
6. 不把上游同步与 WP-0001 或其他目标架构实现混入同一 Work Package。
