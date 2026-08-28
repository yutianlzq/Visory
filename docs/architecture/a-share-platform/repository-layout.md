# Visory 仓库布局与目录责任

最后更新：2026-08-28

## 1. 当前目录结构

```text
Visory/
├── README.md
├── LICENSE
├── AGENTS.md
├── docs/
│   ├── architecture/
│   │   └── a-share-platform/
│   ├── 参考项目/                  # 保留的空目录，不再存放源码
│   ├── CHANGELOG.md
│   └── INDEX.md
├── upstream/
│   └── daily_stock_analysis/      # 基础上游归档，仅本地只读
├── references/
│   ├── repos/                     # 九个外部参考快照及空 _unverified 隔离目录，仅本地只读
│   ├── README.md
│   └── manifest.yaml
├── .gitignore
└── .dockerignore
```

项目 Git 仓库为 `https://github.com/yutianlzq/Visory`，默认分支为 `main`。当前仓库以文档和治理基线为主，尚无按目标架构完成的 Visory 第一方运行时代码；该结构不代表 MVP 已实现。

`upstream/daily_stock_analysis/` 与 `references/repos/` 只存在于本地工作区，由 `.gitignore` 排除，不提交到 Visory 仓库。GitHub 上仅保存第一方治理文件、文档和机器可读核验清单。

## 2. 目录责任

| 目录 | 责任 | 当前写入规则 |
| --- | --- | --- |
| `docs/` | Visory 第一方需求、架构、契约、实施与治理文档 | 可按文档工作流更新 |
| `docs/architecture/a-share-platform/` | Visory 架构单一文档基线 | 不因参考项目变化重写已确认架构结论 |
| `docs/参考项目/` | 旧位置兼容标记 | 保留为空，不再放完整源码，不删除 |
| `upstream/daily_stock_analysis/` | Visory 基础上游历史快照 | 仅本地只读；底座导入必须单独规划、核验和回滚 |
| `references/` | 参考治理说明和清单 | `README.md`、`manifest.yaml` 可提交和维护 |
| `references/repos/` | 九个外部参考快照及空 `_unverified/` 隔离目录 | 仅本地只读；不执行、不安装、不提交、不进入构建上下文；隔离目录不计入已核验项目 |

后续若收到来源、commit 或许可证不能完整确认的快照，应先在本地隔离并标记未验证；完成核验前不得把它提升为正式上游、依赖或“当前 HEAD”。当前十个快照均已定位直接来源和提交，详见 [`../../../references/manifest.yaml`](../../../references/manifest.yaml)。

## 3. 只读与安全边界

- 不执行 `upstream/` 或 `references/repos/` 中的脚本、Docker、安装器和代理指令。
- 不修改参考仓库内部内容；需要补充说明时更新根级治理文档。
- 不从参考项目读取密钥、Cookie、Token、Session 或本地运行配置。
- 参考代码不直接进入生产镜像，相关目录由 `.dockerignore` 排除。
- 参考源码归档由 `.gitignore` 排除；治理文件保留在项目根级。
- 代码吸收前必须核验仓库、commit、许可证、适用 Work Package 和回滚方式。

## 4. 未来第一方代码规划

本轮不创建业务目录。完成 `daily_stock_analysis` 底座导入方案后，再按照架构契约和独立 Work Package 建立实际目录。预期职责如下，最终名称以底座导入设计为准：

```text
apps/                         # Web、Desktop 等用户界面
services/                     # API、Worker 或明确的进程入口
packages/                     # 公共 Schema、契约、SDK 和共享模块
migrations/                   # PostgreSQL/Alembic Migration
scripts/                      # 项目级验证、构建、迁移和运维脚本
tests/                        # 契约、单元、集成、确定性和端到端测试
```

目录创建必须满足：

1. 不破坏现有 `daily_stock_analysis` 迁移基线；
2. 先完成 WP-0001 Contract Registry 与公共 Schema；
3. 模块所有权、Schema、时间语义、StorageRef 和失败语义有明确归属；
4. 本地验证通过后才进入 Docker 和服务器部署阶段。

## 5. 后续迁移顺序

```text
复核 upstream 身份、许可证与历史提交
→ 制定 daily_stock_analysis 底座导入和回滚方案
→ 建立 Visory 第一方工程骨架
→ 实施 WP-0001
→ 按 M0—M8 路线推进
```

参考项目角色和允许采用方式见 [`reference-adoption-matrix.md`](reference-adoption-matrix.md)，快照身份见 [`../../../references/manifest.yaml`](../../../references/manifest.yaml)。
