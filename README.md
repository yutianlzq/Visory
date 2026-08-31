# Visory

Visory 是面向个人使用的 A 股研究、策略验证与复盘平台。项目目标是以可追溯的数据快照、统一契约、Hikyuu 回测和分层研究流程，逐步形成从数据采集到分析、回测和复盘的本地优先闭环。

### Visory 平台状态

当前数据平台推进至 WP-0201 Dataset/Provider Registry（已完成），首批登记 `a-stock-data` 核心源、`Financial-API` 补充源，以及 `security_master`、`trading_calendar`、`bar_1d_raw` 数据集；本阶段仅提供控制面只读投影，不连接真实数据源；Settings 页面只展示凭据是否配置，不暴露引用或密钥。

## 当前状态

当前仓库以需求、架构、契约、实施路线和外部参考治理为主。Visory 第一方运行时代码尚未按目标架构完成，仓库内容不代表可直接部署的成品。

## 文档入口

- [文档中心](docs/INDEX.md)
- [架构索引](docs/architecture/a-share-platform/README.md)
- [实现状态](docs/architecture/a-share-platform/IMPLEMENTATION-STATUS.md)
- [实施路线与验收方案](docs/architecture/a-share-platform/implementation-roadmap-and-acceptance-v1.md)
- [外部参考项目治理](references/README.md)

## 外部源码边界

`upstream/daily_stock_analysis/` 与 `references/repos/` 是本地只读快照，用于后续迁移、设计参考和独立 Work Package 核验。它们不属于 Visory 第一方代码，不进入本仓库 Git 提交，也不进入 Docker 构建上下文。快照来源、提交、许可证证据和采用边界见 [`references/manifest.yaml`](references/manifest.yaml)。
