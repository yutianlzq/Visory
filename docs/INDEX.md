# Visory 文档中心

这里是 Visory 当前文档工作区的统一入口。G002 已将固定的 `daily_stock_analysis` 运行底座导入项目仓库并完成双基线验收；目标架构 Work Package 仍为 `0/45`，下一项是 `WP-0001 Contract Registry 与公共 Schema`。

## 快速入口

| 我想要 | 文档 |
| --- | --- |
| 理解项目定位和总体架构 | [Visory 架构索引](architecture/a-share-platform/README.md) |
| 按统一规则开展后续实现 | [Visory 开发总指引](architecture/a-share-platform/CLAUDE-CODE-GUIDE.md) |
| 查看真实实施状态 | [Visory 实现状态](architecture/a-share-platform/IMPLEMENTATION-STATUS.md) |
| 查看 DSA 底座导入验收 | [Visory-G002 进度与验收记录](architecture/a-share-platform/GOAL-G002-STATUS.md) |
| 查看 DSA 固定提交与导入清单 | [DSA baseline manifest](../upstream-baseline/daily_stock_analysis.yaml) |
| 查看里程碑和 Work Package | [实施路线与验收方案](architecture/a-share-platform/implementation-roadmap-and-acceptance-v1.md) |
| 查看当前目录责任 | [仓库布局与目录责任](architecture/a-share-platform/repository-layout.md) |
| 确认参考项目使用边界 | [参考项目采用矩阵](architecture/a-share-platform/reference-adoption-matrix.md) |
| 查看参考快照身份 | [参考项目 manifest](../references/manifest.yaml) |
| 查看基础上游和参考快照核验 | [外部参考项目治理](../references/README.md) |
| 查看文档变更 | [CHANGELOG](CHANGELOG.md) |

## 产品、页面与闭环

| 文档 | 内容 |
| --- | --- |
| [需求与功能闭环 v1](architecture/a-share-platform/product-requirements-and-feature-closure-v1.md) | FR/NFR、用户旅程、页面、API、任务、产物和验收追踪 |
| [页面信息架构与低保真原型 v1](architecture/a-share-platform/page-prototypes-and-information-architecture-v1.md) | 页面路由、状态、Evidence 和响应式交互 |
| [模块化单体、API、任务与权限架构 v1](architecture/a-share-platform/platform-shell-api-task-permission-architecture.md) | FastAPI/React 平台壳、API 分域、持久任务和权限 |

## 契约、工程与实施

| 文档 | 内容 |
| --- | --- |
| [契约收敛总纲 v1](architecture/a-share-platform/platform-contract-convergence-v1.md) | C-001 至 C-003 标识、时间、状态、版本、Hash、StorageRef 和原子发布 |
| [实现契约目录 v1](architecture/a-share-platform/platform-implementation-contract-catalog-v1.md) | C-004 至 C-013 Provider、Snapshot、Feature、Task、Hikyuu、FactPack、API、调度和部署契约 |
| [工程与编码规范 v1](architecture/a-share-platform/engineering-and-coding-standards-v1.md) | Python、Schema、Migration、Parquet、FastAPI、React、测试和安全规范 |
| [实施路线与验收方案 v1](architecture/a-share-platform/implementation-roadmap-and-acceptance-v1.md) | M0—M9、WP-0001 至 WP-0805、Exit Gate、发布和回滚 |
| [实现状态](architecture/a-share-platform/IMPLEMENTATION-STATUS.md) | 真实代码、验证和发布证据状态 |
| [仓库布局与目录责任](architecture/a-share-platform/repository-layout.md) | 文档、上游、参考项目和未来第一方代码的责任边界 |
| [参考项目采用矩阵](architecture/a-share-platform/reference-adoption-matrix.md) | 外部项目角色、采用方式、允许用途和禁止边界 |

## 数据、特征与市场

| 文档 | 内容 |
| --- | --- |
| [数据平台与 Canonical Data Contract v1](architecture/a-share-platform/data-platform-and-canonical-contract.md) | Provider、Raw、Canonical、Snapshot 和质量门禁 |
| [盘后数据采集与 Snapshot 发布 SLA v1](architecture/a-share-platform/data-ingestion-and-snapshot-sla.md) | 盘后采集、Provisional、Certified、Correction 和能力认证 |
| [Feature Store 与指标注册中心架构 v1](architecture/a-share-platform/feature-store-architecture.md) | F1/F2/F3、依赖 DAG、PIT 和不可变 Manifest |
| [市场情绪与资金行为架构 v1](architecture/a-share-platform/market-sentiment-and-capital-flow-architecture.md) | 市场宽度、五维情绪和资金证据 |
| [板块观察与策略评分边界 v1](architecture/a-share-platform/sector-observation-and-strategy-scoring-architecture.md) | Taxonomy、独立榜单、规则事件和策略引用边界 |
| [全球市场观察与 A 股策略隔离 v1](architecture/a-share-platform/global-market-observation-boundary.md) | 全球观察数据与 A 股正式策略的隔离规则 |

## 复盘与研究

| 文档 | 内容 |
| --- | --- |
| [DSA 收盘复盘 FactPack 架构 v1](architecture/a-share-platform/dsa-close-review-fact-pack.md) | 事实、Claim/Evidence、AI 复盘和 T+1/T+H 验证 |
| [分层个股研究架构 v1](architecture/a-share-platform/stock-research-architecture.md) | L0/L1/L2、个股事实包、角色研究和质量门禁 |

## 策略、回测与权重

| 文档 | 内容 |
| --- | --- |
| [指标、预测与 Hikyuu 回测架构](architecture/a-share-platform/backtest-and-indicator-architecture.md) | 指标注册、预测、执行、验证和全链路追溯 |
| [A 股回测市场规则 v1](architecture/a-share-platform/backtest-market-rules-v1.md) | PIT 股票池、价格、T+1 撮合、费用、容量和基准 |
| [StrategySpec v1](architecture/a-share-platform/strategy-spec-v1.md) | 安全 DSL、Resolver、Compiler 和策略迁移 |
| [Fleur-Lite 回测运行架构](architecture/a-share-platform/fleur-lite-backtest-runtime.md) | Preview/Research/Formal、Task/Attempt 和确定性门禁 |
| [评分、仓位与自动权重优化架构](architecture/a-share-platform/weight-optimization-architecture.md) | 滚动寻优、AI Overlay、MVO 和权重追溯 |

## 部署与安全

| 文档 | 内容 |
| --- | --- |
| [Docker、Cloudflare、NPM 与访问安全架构](architecture/a-share-platform/docker-cloudflare-npm-deployment-architecture.md) | 本地生产预演、访问安全、最小挂载、备份和恢复 |

## 上游与参考项目

- 固定 DSA 提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 的运行底座已导入项目；身份、路径与验证结果见 [`upstream-baseline/daily_stock_analysis.yaml`](../upstream-baseline/daily_stock_analysis.yaml)。
- 重定位的 DSA 文档位于 [`docs/upstream/daily_stock_analysis/`](upstream/daily_stock_analysis/README.md)；其中 `workflows/` 仅为非激活测试证据。
- 基础历史快照 `upstream/daily_stock_analysis/` 仅本地保留、只读且不提交。
- 参考治理说明：[`references/README.md`](../references/README.md)
- 参考快照清单：[`references/manifest.yaml`](../references/manifest.yaml)
- 外部参考源码位于 `references/repos/`，默认只读且不进入 Git 或 Docker 构建上下文。
- 原 `docs/参考项目/` 保留为空目录，不再存放完整源码仓库。
