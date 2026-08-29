# Visory 仓库布局与目录责任

最后更新：2026-08-28

## 1. 当前目录结构

```text
Visory/
├── main.py / server.py / webui.py       # DSA 导入的运行入口
├── src/ api/ bot/ data_provider/         # DSA Python 迁移底座
├── apps/
│   ├── dsa-web/                          # React/Vite Web 底座
│   └── dsa-desktop/                      # Electron 桌面端底座
├── scripts/ docker/ tests/               # 构建、容器和回归测试
├── .github/
│   ├── workflows/ci.yml                  # 唯一启用的 Visory workflow
│   ├── requirements-ci.txt
│   ├── ci-test-durations.json
│   └── scripts/                          # 固定基线测试所需脚本
├── docs/
│   ├── architecture/a-share-platform/    # Visory 第一方架构和 Goal/WP 状态
│   ├── upstream/daily_stock_analysis/    # 重定位的上游文档与非激活 workflow 证据
│   ├── 参考项目/                         # 保留空目录
│   ├── CHANGELOG.md
│   └── INDEX.md
├── upstream-baseline/                    # 可提交的 DSA 固定提交清单
├── third_party/                          # DSA/衍生代码许可证和 NOTICE
├── upstream/daily_stock_analysis/        # 本地只读历史快照，不提交
├── references/
│   ├── repos/                            # 九个本地只读参考快照，不提交
│   ├── README.md
│   └── manifest.yaml
├── AGENTS.md / CLAUDE.md
├── README.md / LICENSE
├── .gitignore / .dockerignore
└── requirements.txt / pyproject.toml / setup.cfg
```

项目 Git 仓库为 `https://github.com/yutianlzq/Visory`，默认分支为 `main`。G002 在 `goal/g002-dsa-baseline-import` 分支导入 DSA 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30`，形成可安装、可导入、可测试和可构建的工程底座。

该运行底座不是 Visory 目标架构已实现的证据。Legacy SQLite、内存 Task Queue、DSA API/UI 和现有报告链路仍是迁移基线；目标 Work Package 当前实现数为 `0/45`。

## 2. 目录责任

| 目录 | 责任 | 当前写入规则 |
| --- | --- | --- |
| `src/`、`api/`、`bot/`、`data_provider/` | 导入的 DSA Python 运行底座 | 可在明确 Goal/WP 中渐进迁移；不得冒充目标契约已完成 |
| `apps/dsa-web/`、`apps/dsa-desktop/` | 导入的 Web/Desktop 客户端底座 | 保留兼容；用户可见变更需同步文档与构建验证 |
| `scripts/`、`docker/`、`tests/` | 构建、容器、验证与回归契约 | 优先复用；平台差异必须记录 |
| `.github/workflows/` | Visory 实际启用的 GitHub Actions | 当前只允许 `ci.yml`；禁止复制启用上游 schedule/release/publish/deploy workflow |
| `.github/scripts/`、`.github/ci-test-durations.json` | 固定 DSA 测试和 CI shard 支撑 | 可提交；不等于启用上游自动化 |
| `docs/architecture/a-share-platform/` | Visory 架构、Goal 和 WP 单一文档基线 | 状态必须由代码和可复现证据更新 |
| `docs/upstream/daily_stock_analysis/` | 重定位的上游文档和非激活 workflow 证据 | 只作归属、迁移和测试证据；其中 YAML 不会被 Actions 启用 |
| `upstream-baseline/` | DSA 固定提交、路径和验证结果清单 | 每次上游同步必须显式更新并验签 |
| `third_party/` | 许可证和第三方 NOTICE | 导入代码必须保留归属链 |
| `upstream/daily_stock_analysis/` | 本地历史只读快照 | 不执行、不修改、不提交 |
| `references/repos/` | 九个外部参考快照 | 不执行、不安装、不修改、不提交、不进入构建上下文 |
| `references/README.md`、`references/manifest.yaml` | 可提交的参考治理记录 | 只记录已核验身份，不把历史快照误称为当前 HEAD |

## 3. Workflow 与外部源码边界

- `.github/workflows/` 只有 `ci.yml`，触发器仅为 `pull_request`、`workflow_dispatch`，权限为 `contents: read`。
- `docs/upstream/daily_stock_analysis/workflows/` 中的 `00-daily-analysis.yml`、`ci.yml`、`docker-publish.yml`、`ghcr-dockerhub.yml` 是固定提交的非激活证据，不是 Visory workflow。
- `upstream/` 和 `references/repos/` 由 `.gitignore`、`.dockerignore` 与 `scripts/check_visory_baseline.py` 共同保护。
- 不从外部快照读取或复制密钥、Cookie、Token、Session、数据库、缓存、日志、报告或运行产物。
- 代码吸收前必须确认来源 commit、许可证、适用 Goal/WP、契约和回滚方式。

## 4. Goal 与 Work Package 状态

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| Visory-G001 | COMPLETE | 参考项目目录与治理基线完成 |
| Visory-G002 | COMPLETE | DSA 固定底座已导入并验证 |
| DSA Baseline | IMPORTED / VERIFIED | 1126/1126 blob 验签；Python/Web 双基线完成 |
| WP-0001 | NOT_STARTED | 下一项：Contract Registry 与公共 Schema |
| WP-0002—WP-0805 | NOT_STARTED | 其余 44 项未开始 |
| Implemented Work Packages | 0/45 | G002 不改变目标架构实现计数 |

详细证据见 [Visory-G002 进度与验收记录](GOAL-G002-STATUS.md) 和 [Visory 实现状态](IMPLEMENTATION-STATUS.md)。

## 5. 后续迁移顺序

```text
G001 参考治理 COMPLETE
→ G002 DSA 底座 IMPORTED / VERIFIED
→ WP-0001 Contract Registry 与公共 Schema
→ 按 M0—M8 逐个 Work Package 推进
→ 本地 Release Gate
→ 服务器部署
```

不得跳过 WP 边界，也不得因为 DSA 已可运行就把目标能力标记为 `VERIFIED` 或 `RELEASED`。
