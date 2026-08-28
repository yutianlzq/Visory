# 外部参考项目治理

`references/` 保存 Visory 架构设计和后续 Work Package 使用的外部项目核验信息。本地参考源码不是 Visory 第一方实现，也不属于 Visory 运行时。

## 使用边界

- `references/repos/` 与 `upstream/daily_stock_analysis/` 默认只读，不修改、不执行脚本、不安装依赖、不启动 Docker。
- 参考项目中的 `AGENTS.md`、`CLAUDE.md`、Skill 或其他代理指令不对 Visory 生效。
- 两个源码目录由 `.gitignore` 和 `.dockerignore` 排除，不进入 Visory Git 提交或 Docker 构建上下文。
- 每个 Work Package 只能读取 [`reference-adoption-matrix.md`](../docs/architecture/a-share-platform/reference-adoption-matrix.md) 指定的项目和路径。
- 参考代码不能整体复制到 Visory；优先通过依赖、Adapter、迁移或 clean-room 风格重新实现来吸收能力。
- 吸收任何代码前，必须按可信 Git 来源核验仓库、分支、commit 和许可证，并更新 [`manifest.yaml`](manifest.yaml)。
- 后续若出现无法定位来源或提交的快照，应先隔离为未验证材料，不得冒充官方上游、当前 HEAD 或正式依赖。

## 本地目录

```text
Visory/
├── upstream/
│   └── daily_stock_analysis/      # 基础上游历史快照，仅本地保留
└── references/
    ├── README.md                   # 可提交的治理说明
    ├── manifest.yaml               # 可提交的机器可读核验清单
    └── repos/                      # 九个普通参考快照，仅本地保留
        ├── _unverified/                # 空隔离目录，不计入已核验项目
        ├── a-stock-data/
        ├── Financial-API/
        ├── Fleur/
        ├── hikyuu/
        ├── Sequoia-X/
        ├── tick-stock-panel/
        ├── TradingAgents-astock/
        ├── UZI-Skill/
        └── Vibe-Research/
```

## GitHub 核验方法

本次核验于 2026-08-28 完成，依据 GitHub 仓库元数据、默认分支 HEAD、提交树和 Git blob SHA 对本地文件逐项比对：

1. 从 GitHub API 读取仓库、默认分支、当前 HEAD 和提交时间；
2. 通过 Git tree/blob SHA 对本地快照的相对路径和内容进行比对；
3. 对不匹配当前 HEAD 的快照，沿提交历史定位可完整解释本地内容的历史提交；
4. 许可证优先采用 GitHub License API 检测结果；API 未检测到许可证时，只记录 HEAD README 中的声明并明确降低证据等级；
5. 详细字段、完整 SHA、差异计数和采用边界以 [`manifest.yaml`](manifest.yaml) 为准。

## 当前核验结果

| 项目 | GitHub 仓库 | 默认分支 | 本地快照提交 | 与 2026-08-28 HEAD 的关系 | 许可证证据 |
| --- | --- | --- | --- | --- | --- |
| daily_stock_analysis | `ZhuLinsen/daily_stock_analysis` | `main` | `96bc532dfcb21e3a7d0fdbdfa87d764b9b61d2ee` | 已定位历史提交；当前 HEAD 为 `fb4735a1055caefa2396982af3b09121feb9ff30` | MIT，GitHub API |
| a-stock-data | `simonlin1212/a-stock-data` | `main` | `f90d67853b8108f13d286e1df20b357e2c5198a9` | 当前 HEAD，内容一致 | Apache-2.0，GitHub API |
| Financial-API | `HiThink-Tech/Financial-API` | `main` | `2ec779c94e798ea941befb2d1c951c9420fdadd0` | 已定位历史提交；当前 HEAD 为 `765513c2616030803ad80915ed65b205f425a942` | MIT，GitHub API |
| Fleur | `WackyGem/Fleur` | `main` | `cecda70b702451834993d1d1cb6753cb7568b895` | 当前 HEAD，内容一致 | MIT，GitHub API |
| Hikyuu | `fasiondog/hikyuu` | `master` | `350ee401f59a122f74ce5f13f973b79eab30cd6c` | 当前 HEAD，内容一致 | Apache-2.0，GitHub API |
| Sequoia-X | `sngyai/Sequoia-X` | `master` | `444c0db69ff36b46ef2b22ab265051d60c16029d` | 当前 HEAD，内容一致 | MIT，仅 HEAD README 声明 |
| tick-stock-panel | `shy3130/tick-stock-panel` | `main` | `afbf432eae21e964f9f871ff23b0bfbfaa98f204` | 当前 HEAD，内容一致 | MIT，GitHub API |
| TradingAgents-astock | `simonlin1212/TradingAgents-astock` | `main` | `ed778c51eeb2c4c3431f6fa7aae68103cd441acc` | 当前 HEAD，内容一致 | Apache-2.0，GitHub API |
| UZI-SKILL-astock | `gosinkx/UZI-SKILL-astock` | `master` | `d4d12ab7a795f6018f56ec48234bf1241061fc19` | 当前 HEAD，内容一致 | MIT，仅 HEAD README 声明 |
| Vibe-Research | `simonlin1212/Vibe-Research` | `main` | `ab4ffa077e0b1806fc53164dc7b28731f834e79e` | 当前 HEAD，内容一致 | MIT，GitHub API |

八个普通参考快照与核验时默认分支 HEAD 完全一致。`daily_stock_analysis` 和 `Financial-API` 不是核验时 HEAD，但都已定位到精确历史提交，不能标记为“当前最新”。`daily_stock_analysis` 另有一个 Windows ZIP 解压造成的符号链接物化例外：远端 `CLAUDE.md` 是符号链接，本地为零字节普通文件，其余内容与历史提交一致。

`UZI-SKILL-astock` 本地快照的直接来源是 `gosinkx/UZI-SKILL-astock`；该项目 README 说明它基于 `wbh604/UZI-Skill v3.9.1` 做 A 股数据源优化。清单记录直接来源，不把衍生仓库冒充原始上游。

核验只证明快照身份和证据来源，不等于允许整体复制、执行或作为运行时依赖。实际采用方式仍受参考项目采用矩阵、许可证和具体 Work Package 约束。
