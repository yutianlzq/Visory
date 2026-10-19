# Visory 实现状态

## 2026-10-19 WP-0207 / PR #42 公开文本安全与状态收敛

- PR #41 已合入，实时 main=`efe8e9b362cba13eca183c55be57bbbbc832b60b`；当前 main 的 VERIFIED 已为 15/45、IN_PROGRESS 1、NOT_STARTED 29、RELEASED 0。WP-0302 的代码/契约已合入，不再称“仅分支验收、未合入”；仍不代表生产认证或 RELEASED。下方带日期的旧准备结论/计数只作历史。
- PR #42 当前 OPEN / non-draft / MERGEABLE / CLEAN，远端 head `206b85c69e0e3c9181b496d468d0e743a688d98e`；Run `38871182213` governance/backend/Web 全绿只覆盖远端旧内容。本地后续补丁增强公开 JSON/Unicode/百分号编码与绝对路径检测，尚未提交/推送，不可声称 MERGE_READY；本轮 fetch exit 128，实时 SHA/PR/CI 由只读 GitHub API 独立确认。
- WP-0207 保持 IN_PROGRESS；8 条真实 routes BLOCKED、Capability UNVERIFIED、Coverage UNPROVEN、NOT CERTIFIED、RELEASED=false。无真实 Provider/生产数据库/真实 `/data`/生产调度访问，无相邻 WP 实现或生成物变化。共享语料、HTTP/SSE/内部恢复、PostgreSQL、完整 gate 和本地最终判定见[最新验收记录](WP-0207-END-TO-END-CLOSEOUT.md#2026-10-19-pr-42-公开文本安全与状态收敛)。
- 本轮按新增授权将已核验的 163 条既有完整 flake8 诊断记为 FOLLOW-UP，仍硬性要求 critical flake8 通过且新增诊断为 0；完整 flake8 的原始 exit 1 不改写为通过。只在隔离临时 Linux 容器安装 `procps` 及仓库既有 CI 依赖，使用 Docker 内置 `--init`，不改 scheduler 源码或断言。上轮精确 tree `19edbf6888f8cf6c1274fdf7ffe3358b9b96f335` 的完整 gate 为 1 failed/7782 passed/0 skipped/exit 1，唯一失败已证实容器缺少 `ps`；该历史失败不作为本轮结果。三文档先同步再封装，精确最终候选必须重跑完整 `scripts/ci_gate.sh` 和真实 PostgreSQL 四文件，不能用定向通过替代。最终 tree/hash、实际命令/退出码/数量、零新增诊断及清理证明统一封存在仓库外 `procps-resume-final-report.md` / manifest；不预记成功。
- 候选必须排除 AGENTS.md 与 CHANGELOG 开工已有治理 hunk；保护主 checkout/f468/所有其他 worktree，不 commit/push/merge 或更新 PR body。body 仅描述现有远端 head，未来推送后须同步新 head 与 CI，重新语义审查。回滚仅撤回本轮精确安全/状态 hunk，保留治理字节与 0014 迁移历史；不执行数据库 downgrade/stamp。中文专题无英文对应版本。

## 2026-10-16 WP-0207 delta 续验：本地 WP-only 候选补丁 PR-ready

- 父 Backfill 已复用 Raw 对实际 plan 的来源/Schema 配置检查，发生于业务子任务前；Raw 再验证 route 的状态/hash，防止未经重校验的模型副本绕过门禁。离线定向通过，隔离 PostgreSQL 首轮 117 passed/0 skipped，后续 route 修改再验 5 passed/0 skipped；均不证明真实来源/完整历史。
- 最终定向 Python 436 passed/122 skipped、Web 52 passed；完整 gate 81 failed/7051 passed/173 skipped（exit 1），逐节点与同 HEAD 纯归档基线比较 `current-only=0`，不称 gate 通过。51 路径 WP-only patch 已排除 `AGENTS.md` 及 CHANGELOG 治理条目，在仓库外纯 HEAD 镜像 apply 与逐字节核验通过；52 文件、保护树状态再次复核。当前整个 dirty 工作树不能直接当单一 WP PR 提交，未创建 PR。
- 真实 route BLOCKED、Capability UNVERIFIED、Coverage UNPROVEN；保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未访问生产或执行 Git 发布操作。下方初次审查结论仅为历史状态。

## 2026-10-16 WP-0207 delta 初次审查（历史）：BLOCKED

- Raw preflight 异常进入 Task failure/终态；fixture 必须绑定 Provider/Dataset/Adapter/version 且为 FIXTURE/FIXTURE_ONLY，普通 transport 不得执行 fixture route。
- 父 Backfill fixture 门禁尚未验证 factory 返回 route，与 Raw 严格校验不一致；AGENTS 跨项目参考治理须独立拆分但本轮不回滚。停止追加业务补丁，不能称单一 WP-0207 PR-ready，详见[验收记录](WP-0207-END-TO-END-CLOSEOUT.md)。
- 定向 Python 297 passed/39 skipped、Contract/Golden 与 Backfill/Foundation 135 passed/82 skipped、Web 52 passed；契约/治理/baseline、27 文件 py_compile/critical lint、Web 定向 lint/types/build 通过。完整 flake8 189 条开工既有诊断、完整 gate 79 failed/7049 passed/172 skipped 均 exit 1；79 个失败节点均在同 HEAD 历史纯归档基线中，不据此称全量通过。
- 当前 Docker daemon 不可用，数据库 skip 不计通过；未接入真实 Provider、不访问生产资源或真实 `/data`。八条真实 route BLOCKED、Capability UNVERIFIED，仍 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`。历史 PostgreSQL/浏览器结果不替代本轮验证，中文专题文档无英文对应版本。

## 2026-10-15 16:48 WP-0207 `a-stock-data` 架构增量

- 新增 `ProviderSourceRouteEvidence` 与固定 route registry；`a-stock-data` 的 Release/commit/blob/license 和实际 upstream 分开记录，route Hash 进入 ProviderRun 与请求 fingerprint。Adapter 固定版本不再被误当成数据来源、历史覆盖或 PIT 证明。
- Raw worker 与 Backfill preflight 复用既有 Provider Registry、Durable Task 和 Raw→Canonical→Snapshot 链路；Capability 非 `AVAILABLE/DEGRADED`、缺 Raw Schema、缺/blocked route、响应 upstream 不一致均 fail closed。没有新增 Queue、Publisher、Repository 或并行数据链路。
- `ProviderRun.source_route_evidence` 对新运行必填于实际 worker 路径，数据库列为 nullable 只兼容旧记录；Contract `1.1.0`、migration `0014_wp0207_source_binding`、Registry/OpenAPI/Golden/前端生成类型已同步。fixture 只有显式 `fixture_only=True` 才可绕过真实来源门禁用于测试。
- 相关本地验证：临时 PostgreSQL `96 passed / 0 skipped`，scoped backend `303 passed`，Web `52 passed`，generated contracts `7 passed`，受影响 lint/types/build、27 文件 py_compile、AI 资产/baseline/diff 检查通过。临时容器和随机凭据已清理；这些结果使用合成 transport，不提升来源证据等级。
- 完整 backend gate 仍失败：Windows Codex 子进程测试最窄复核 `43 failed / 2 passed`，全 gate 未跑完；当前 fetch 也失败，只有缓存 `origin/main=efe8e9b...`。8 条真实 route 均 blocked，Capability unverified，完整七阶段/历史 Coverage/PIT/revision/分页、远程和生产仍未完成，继续 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false`。

## 2026-10-15 12:43 WP-0207 来源与恢复投影续验

- 对 Financial-API 追加 8/10 次授权只读 GET：`920799.BJ` 最近窗口日线 10 行、闭合窗口 424 行和最新估值 1 行可用；没有下载 Market Dump、访问生产资源或保存 Key/完整响应。该窄样本只提升单标的可读性证据，不提升 Provider Capability 或历史认证状态。
- 同一闭合窗口的六个 offset（最高 1,000,000）返回相同 424 行和相同 item Hash，响应无显式终止元数据，确认历史端点实际忽略 offset；交易所过滤、退市 universe、PIT/修订和历史 Coverage 仍 fail closed。`WP-0207-SOURCE-UNBLOCK-PACKAGE.md` 已同步为线上 `FAILED_CONTRACT` 反例。
- 现有 checkpoint 公开投影、按月缺口与已有 Task 恢复动作无需新增实现；Backfill/公开投影 272、Contract/Golden/generated 138、Web 52 用例通过，受影响 lint、`tsc -b`、Vite build、17 文件 py_compile、契约与治理检查通过。没有新增 Queue、Publisher、Repository、Schema 或公开 API。
- 本轮没有可用 Docker/PostgreSQL，61 个相关集成场景被 skipped，不能算通过。完整 gate 在固定 venv Python 3.12.9 下为 82 failed / 7036 passed / 157 skipped / 4 deselected（exit 1），全量 Web lint 38 errors（exit 1）；保持既有 BLOCKER，不用定向通过替代全量结果。
- 实施树 HEAD 与 12:42 实时 main 均为 `efe8e9b...`。本轮仅五文档增量，保护其余 34 个 Goal 路径、主 checkout、f468 和参考项目；完整来源/七阶段历史、临时 PostgreSQL、远程 CI/合入及生产认证未闭合，继续 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 22:54 WP-0207 真实来源最小解阻包

- 只读核验 `E:\Personal Manager\参考项目` 的 Financial-API、a-stock-data、Fleur、UZI 和 daily_stock_analysis 指定入口，记录 17 个当前文件 Hash；未读取凭据、执行参考代码、发起真实取数或访问生产。
- 新增[WP-0207 真实来源最小解阻包](WP-0207-SOURCE-UNBLOCK-PACKAGE.md)，把 Provider 接口/字段/PIT/分页契约、七阶段历史覆盖、S01-S14 授权脱敏样本、owner 交付目录及 G01-G14 fail-closed Gate 固化为继续集成的最小输入。
- 参考材料仅为候选或反例，不能证明当前线上版本、授权和完整历史；历史 K 分页、长期日历、公司行动/财务 revision/PIT、北交所估值/状态、行业披露时间和双真实源质量仍缺。真实 package 未到齐前保持 Blocked/Unavailable，不生成空成功或伪造 `available_at`。
- 本次无运行时代码、测试或生成契约变化；固定 Python 的 AI 资产检查通过，baseline 检查 633 个相对链接且 0 个破损，diff 与 17 个参考文件 Hash 复验通过。未重跑后端/Web/PostgreSQL 或完整 gate，本轮未创建/清理 PostgreSQL 容器；`WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不改变相邻 WP 状态/计数，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 17:34 WP-0207 纯 HEAD 门禁归因

- 从当前 HEAD 的纯归档在同一固定 Python/Bash 和独立 PostgreSQL 上重跑完整 gate：纯 HEAD 84 failed / 7025 passed / 10 skipped，当前增量 83 failed / 7182 passed / 10 skipped，均 exit 1、另有 572 subtests passed。83 个当前失败全部在纯 HEAD 复现，`current_only=0`，失败测试文件与 HEAD 一致；没有发现 WP-0207 新增失败节点，但 gate 仍为失败。
- 三个重点新增节点分别收敛为既有 deadline 浮点边界、Windows 临时目录清理竞争和 Storage 时序不稳定；纯 HEAD 独有一项 Provider cache 失败。相关 Legacy 修复及全量 lint 38 errors 作为 FOLLOW-UP，不扩大本 WP。上一封存的 Backfill 601 passed/0 skipped、Web 66、Chromium 108/0 skipped 和对象 Hash 证据继续有效，但仍是合成/fixture 本地证据。
- HEAD 门禁临时 PostgreSQL与密码、纯源码解压目录和本轮三个临时目录已限定清理，归档 ZIP/日志保留；主 checkout 三文档、f468 52 文件及并行临时目录仅只读保护，未写入或清理。上一轮 603 文件封存开工复验通过，本轮只更新四份 WP-0207 状态文档，整体 38 文件中其余 34 字节不变。
- 真实 Provider 版本和授权、规定历史逐证券覆盖与退市 universe、两真实成功源质量、当前增量远程 CI/合入及生产资源认证仍未闭合。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不改变相邻 WP 状态或计数；继续条件、命令/Hash、验收矩阵和仅四文档回滚见[最新验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部本节，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 16:57 WP-0207 阶段租约隔离

- 在现有 Task Service/Repository 统一阶段 Task 的排队领取、过期 LEASED/RUNNING 恢复约束，避免多批次误租；保留默认调度及状态/能力/行锁门禁，不新增 API/Schema、Queue、Publisher 或 Repository。
- 新增 1 单元/9 PostgreSQL 场景；真实临时 PG 中相关 API/Contract/Golden、Backfill 对象链和原控制面 601 passed / 0 skipped，17 文件编译和生成契约通过。22 最终回执/223 对象/226 文件固定引用与 Hash 归档复验；合成 transport/plan-only，不将阶段首任务隔离验收当七阶段真实执行。
- 本轮实际完整 gate（固定 Python、独立 PG）83 failed / 7182 passed / 10 skipped，572 subtests passed，exit 1；其中平台集成 155 passed/0 failed/0 skipped。80 个失败与前轮重合，三个新增节点未完成根因证明；原始 python3 漂移及无 PG 全量失败保留，全量 Web lint 仍 38 errors。
- 客户端字节未改，继承 Web 66、Chromium 108/0 skipped、受影响 lint/types/build，来源绑定另行复验；两套 PG/密码和四个已归档 runtime 已限定清理，其他容器、主 checkout/f468/并行临时目录保留。16:08 fetch 失败，16:09/16:57 main API 成功，HEAD/main 为 `efe8e9b...`。
- 本轮 9 个既有路径、整体 38 文件及其余 29 开工字节、四份旧封存只读复验、固定 Hash/账本/四态验收与九文件恢复回滚见[最新验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部本节。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`；真实来源/规定全历史/两真实成功源、当前增量远程与生产验收未完成，不改变相邻 WP 状态或计数，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 15:55 WP-0207 Operations 请求归属验收

- Operations 结果绑定当前路由/筛选和请求序号，拒绝迟到响应覆盖当前状态；原生 SSE 独立绑定当前视图，连接重建等待自身 open/event，不继承旧连接健康状态。不修改 Task 事务、契约、Queue/Publisher/Repository。
- 原页面三项 lint 已关闭，受影响 lint、类型/build 通过；最终 Web 66 passed、Chromium 双视口 108 passed / 0 skipped，含十个新增浏览器生命周期场景。初次 106 场景/静态 zip 和连接重建 red 保留；全量 lint 38 errors、原完整 backend gate 81 failed 仍未通过，不用局部通过替代。
- 本轮六路径均开工前已存在，整体 36 文件，其他 30 字节不变；保留失败日志、三份旧封存与主/f468 并行成果，仓库外账本、固定 Hash、浏览器绑定和六文件恢复字节的回滚见[最新验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部本节。
- 本轮重跑 15 个 py_compile 和生成契约/治理/diff；未重跑后端 507/165、PG/files 73 或完整 gate，旧证据来源性质不变。15:06 main API/fetch 成功，HEAD/main 同为 `efe8e9b...`；所属浏览器服务关闭、旧 PG/密码清理复验，其他资源保留。
- 完整来源/历史、双真实源、当前增量远程和生产验收仍缺；保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不改变相邻 WP 状态或计数，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 WP-0207 浏览器与任务详情验收

- 连续授权下只追加 f468 已知四文档的只读快照，保护其余代码/临时目录和主 checkout；旧封存与失败记录不改写。完整 Goal 已恢复 active，本轮仅推进 WP-0207。
- Operations 列表、详情、受控操作错误分开保存；筛选刷新不丢详情诊断，退出详情不留旧告警，失败明确不可用而非持续加载。新增四个回归最终通过，完整 Web 定向 58 passed；真实 Chromium 双视口四页面及原生 SSE 98 passed，fixture API 与真实 backend/来源验收分开。
- 公开投影/API/Contract/Golden 165 passed、15 个 py_compile、契约检查、类型/build 通过。受影响 lint 3 errors、全量 41 errors，原始页面对照同样 3 errors；原全量 backend 81 failed / 7174 passed / 10 skipped 未关闭，本轮未重跑 PG 或全 backend。
- 本轮六文件、整体 36 文件，前轮其他 30 字节未改；14:22/14:23 远程核验/fetch 成功，HEAD/main 为 `efe8e9b...`。八截图、账本、固定 Hash/保护及清理复验/限定回滚见[最新验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部浏览器节，不更新其他 WP 状态或完成计数。
- 保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`；真实来源授权、七阶段完整历史、两真实成功源质量、远程 CI/合入和生产验收仍缺。未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 WP-0207 保护确认后的封存复验

- 保留 `seal-final` exit 1 的首次保护校验失败及其脚本副本；用户确认 f468 四文档新字节后，在本轮新证据目录追加 52 文件的只读快照，不覆盖旧封存或并行 WP-0303 成果。
- 旧封存 2874 文件 Hash/大小复验匹配，WP-0207 所属 PostgreSQL/密码已不存在；12:58 远程 main 核验/fetch 通过，HEAD/origin/main/实时 main 均为 `efe8e9b...`。
- 本次仍只更新四文档，整体 Goal 保持 34 文件，其他 30 文件字节不变；新的 `seal-confirmed` 实际结果、命令账本、交付 Hash、验收限制及限定回滚见[权威验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部本节。
- 完整 gate、全量 lint、真实七阶段/历史覆盖、两真实成功源质量及本增量远程/生产认证仍未闭合。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不提升其他 WP 状态或计数，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 12:30 WP-0207 验收归因续做

- 核验现有 Linux 资源：WSL Python 3.10 且无测试依赖、没有现成缓存测试镜像；不安装或下载依赖，CI 等价 Linux 验证尚不能执行。固定 Windows Python 实际为 3.12.9。
- 情报 fail-open 单测和全树收集后定向各 1 passed，API/Service 35 passed，main 未注入状态控制 1 passed；离线的 Requests 共享代理字典反例在实施树/main 归档均 1 failed。后者是既有机制反例，不等同原完整 gate 根因，不计为通过或本次新回归，不修无关模块。
- 本轮仅修改四文档并另存原始字节、命令和 Hash；整体仍为 34 文件，旧封存证据未覆盖，主目录三文档/f468 的 52 个确认文件保留。12:20/12:21 远程核验/fetch 成功，main/HEAD 均 `efe8e9b...`。
- 完整 WP 与生产保持 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不提升其他 WP 计数。最新阻塞、环境/来源条件及四文档回滚见[权威验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部 12:30 节；未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 11:03 WP-0207 收尾封存

- 补录最终清单、命令账本、四态验收与 Hash 复验记录：整体 Goal 34 文件（27 tracked 修改、7 新增），补源/隔离回合 14 文件，本次只补录四文档；分别保存编辑前字节及限定增量的回滚记录。
- 本地 507 定向、73 真实 PostgreSQL/files（0 skipped）、121 Golden、54 Web 通过，13 场景的 223 对象/223 文件已归档复验；全量 gate 81 failed / 7174 passed / 10 skipped / 4 deselected、572 subtests passed（exit 1），全量 lint 41 errors（exit 1），保留失败差异和未解释情报 fail-open。
- 本轮 PostgreSQL/密码和 13 个 runtime 已清理；原 4 个容器保留，清理时出现的并行 WP-0303 容器未由本轮清理或恢复。用户新确认的 f468 四文档变化及当前 52 文件快照只读保留，主目录三个既有文档未写入。11:03 fetch/实时 main 成功，实施 HEAD/origin/main/实时 main 均为 `efe8e9b...`。
- 以[最新权威验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部封存节为当前结论；七阶段真实来源、完整历史逐证券覆盖、两真实成功源质量、全量 gate、本增量远程 CI/合入和生产认证仍未闭合。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不改变其他 WP 计数；未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 WP-0207 续做：补源拒绝血缘与 Raw quarantine 恢复

- 拒绝/quarantine 回执追加失败主源 Hash；父 checkpoint 与公开投影保留 fallback、失败范围和已成功月份。恢复复验现有 Task/Attempt/ProviderRun/Policy/输入/文件；Raw quarantine 只恢复拒绝证据，不作为成功 Raw 提交下游。
- 新增 25 个回归；定向 507 passed、真实 PostgreSQL/files 73 passed / 0 skipped、Web 54 passed，受影响编译、契约、lint/tsc/build 通过。13 场景归档 223 对象/223 文件已复验并清理对应 runtime。全量 lint 仍有 41 errors；完整 gate、PostgreSQL 清理、命令和最终 Hash 以[最新验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部本节为准。
- 整体 Goal 的 34 个增量文件与本回合编辑前字节分别保存；主目录三个文档及 f468 最新确认的 52 文件没有写入。WP-0207 继续 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未改变相邻 WP 计数或历史认证，也未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 WP-0207 续做：发布拒绝与固定失败证据

- 父 Backfill 保留 Canonical/Snapshot 实际拒绝的稳定 code 和终态失败语义；checkpoint/公开投影追加 `rejection_evidence`，绑定 Batch/父 Task/分区、子 Task/Attempt/输入及 ProviderRun/Raw/Quality/Canonical Hash。恢复重新复验已持久化对象和文件，跨月拒绝保留已成功月份的固定回执。
- 本地定向 495 passed、真实 PostgreSQL/files 60 passed / 0 skipped、更新 Golden 121 passed、Web 54 passed；受影响 lint/类型/build、15 个 py_compile、生成契约和 AI 资产通过。全量 Web lint 仍 41 errors；完整 gate、清理、命令/文件/回滚明细见[本轮权威验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部 10-14 节。
- 实施工作树沿用 `codex/wp-0207-end-to-end-closeout@efe8e9b...`。主 checkout 的三个既有文档及 f468 的 52 个确认保护文件未写入；早期远程获取失败保留，09:34 的实时 main 核验/fetch 均成功且基线未变。
- 完整 gate 82 failed / 7148 passed / 10 skipped / 4 deselected、572 subtests passed，exit 1；新增两个失败在 main 归档复现，情报 fail-open 未解释。新增 9 场景的 129 对象/135 文件已导出复验；临时 PostgreSQL/密码及对应 9 个 runtime 目录已清理，其他容器不变。整体 34 文件、本回合 21 文件，按仓库外 Hash/原始字节账本限定回滚。
- WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false`；本地拒绝/恢复验证不是两真实成功源的质量比较、全历史或生产证据。其他 WP 状态和历史章节不变，没有 commit/tag/push/PR/merge/部署。

## 2026-10-13 WP-0207 续做：checkpoint 公开校验与恢复动作

- 公开投影共用 worker 的 checkpoint 输入/连续分区/固定引用校验；Hash 匹配但语义错误、缺 resolver 和 dry-run 虚假业务完成不再被接受。
- 既有 coverage API 追加按月执行区间、未安排日期和已有 Task 恢复动作；仅 `RETRY_WAIT` 指向既有 retries API，失败/取消/Unavailable/quarantine 保持明确审查。没有新 Queue/Publisher/Repository 或自动生产重试调度。
- 定向 `457 passed`、真实 PostgreSQL/files `43 passed / 0 skipped`、Web `54 passed`，受影响 lint/类型/build/py_compile/契约通过；全量 Web lint 仍 41 errors。完整 gate、来源、精确证券逐日覆盖、远程和生产结论见[本轮权威验收记录](WP-0207-END-TO-END-CLOSEOUT.md)顶部续做节，不覆盖历史证据。
- 续做完整 gate `80 failed / 7127 passed / 10 skipped / 4 deselected`、572 subtests passed，exit 1；临时 PostgreSQL 容器与密码已清理，其他 4 容器不变。本回合 17 文件/整体 33 文件的来源字节、交付 Hash、命令和增量回滚记录保存在仓库外。
- 交付时实时远程 main 的再次核验受网络失败/超时阻塞；最近成功 SHA 为 2026-10-13 23:09:44 的 `efe8e9b...`，不据本地缓存 refs 宣称最终远程通过。
- 保留主 checkout 三个既有文档和用户再次确认的 f468 全部并行内容。本 Goal 未满足完整验收，`WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`；未执行 commit/tag/push/PR/merge/部署，不改变相邻 WP 汇总。

## 2026-10-13 WP-0207 端到端闭环本地验收范围

- WP-0207 新增本地实际对象链固定回执、月分区/恢复校验、受控补源、隔离拒绝证据、失败范围与覆盖缺口公开投影和脱敏；Backfill PostgreSQL/files 为 `43 passed / 0 skipped`，相关单元/API/Contract/Golden/Snapshot 为 `428 passed`，Web 定向 `54 passed`。
- 完整七阶段真实来源、2018 起全证券日线及精确逐日缺口、双源冲突和全量质量、当前增量远程 CI/合入与生产认证仍缺证据；全量本地 gate 和 Web lint 失败。`coverage=UNPROVEN`，文件发布不等于历史覆盖认证。完整依据和实际命令见 [WP-0207 本轮验收记录](WP-0207-END-TO-END-CLOSEOUT.md)。
- 状态继续为 `WP-0207=IN_PROGRESS / NOT CERTIFIED`、`RELEASED=false`；历史 `G020=COMPLETE` 不用于完成本 Goal。保留主 checkout 和 f468 的既有成果，不改相邻 WP 状态/计数。下方 2026-10-07 汇总及历史章节按各自日期解读，本节没有重新计算 WP-0301/0302 的合入状态。
- 本次 dirty 增量保留在独立 `codex/wp-0207-end-to-end-closeout@efe8e9b362cba13eca183c55be57bbbbc832b60b`，没有 commit/tag/push/PR/merge/部署或生产资源操作。
- 最终收尾完成文件/命令/SHA256 账本及临时 PostgreSQL/密码清理；最终全 gate `80 failed / 7098 passed / 10 skipped`，exit 1。用户已确认并行 f468 WP-0303 变化，本轮仅保存只读快照、不修改或回滚；主 checkout 三个既有文档保持原始字节。真实来源和完整 WP 的验收条件仍不满足，不提升状态。
- 用户后续授权在根 AGENTS.md 增加十个本地参考项目的价值/源码路由；最终文件清单由 32 项扩为 33 项。参考目录提供候选来源契约和实现反例，允许继续只读分析与 Visory 契约映射；没有授权真实取数、凭据访问或生产资源操作，也不改变上述验收结果。

## 2026-10-07 WP-0302 PR 准备与状态收敛

- 实时 fetch 核验：远程 `main@6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`；准备起点 `codex/wp-0302-feature-bundle@2ac0f6e6103d91c829893b4ad9da48dd3332f40c`，包含两个 WP-0302 提交，基线差异为 `0 behind / 2 ahead`。主 checkout 的三个既有文档改动保持不变，收敛仅在 WP-0302 隔离 worktree 进行。
- WP-0301 已通过 PR #40 合入；实现 head `50b15b7f13b2787bde92f5ff96f093014165002f`，普通 merge commit `6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`，`merged_at=2026-09-29T16:52:37Z`。合入后 Run `36601155597` 的 Governance、Python、Web 三项 `completed / success`，WP-0301 修正为 `VERIFIED / MERGED`，不是 `NOT_STARTED`。
- 本文当前 WP 表的唯一条目计数：`VERIFIED=15`、`IN_PROGRESS=1`、`NOT_STARTED=29`、`RELEASED=0`，合计 `45`。implemented work packages 为 `15/45`（含本分支已验收但未合入的 WP-0302）；远程 main 已合入并验收的 WP 为 `14/45`。WP-0207 保持 `IN_PROGRESS`，不计入；同一 WP 的多次 Goal、hardening 或状态 PR 不重复计数。
- WP-0302 仍为实现分支代码/契约 `VERIFIED`，不是 `MERGED` 或 `RELEASED`。既有 Run `37568286328` 对应实现 head `a7ba8d055b3fccc8bfd5bd14eeabb27680ab0b8a`；它不是准备起点 `2ac0f6e` 或后续 PR 当前 HEAD 的 CI。PR 创建须单独授权，只有 PR 当前 HEAD 的三项阻断 CI 均成功后才可判为 merge-ready；本任务不执行 merge。
- 本节及下方当前结论/状态表为当前汇总；后续带日期的 G020/WP-0207 记录和其中 `13/45` 是历史快照，不覆盖当前计数。生产保持 `NOT CERTIFIED`、`RELEASED=false`；完整范围、验证限制及回滚计划见 [WP-0302 验收记录](WP-0302-IMPLEMENTATION.md)。

## 2026-10-07 WP-0302 实现分支验收

WP-0302 在 `codex/wp-0302-feature-bundle` 完成代码/契约验收，状态为 `VERIFIED`；[完整验收记录](WP-0302-IMPLEMENTATION.md) 包含指定基线、实现提交、Migration、Contract/Golden、反例、隔离 PostgreSQL、行执行覆盖率和远程阻断 CI 证据。该分支已推送但未合并 `main`；本节记录 PR 创建前的实现验收，未部署；WP-0207 的历史记录未改写；当前汇总已纳入 WP-0301 与 WP-0302 的独立验收条目，不将分支验收当作主线发布或生产认证。生产始终 `NOT CERTIFIED`、`RELEASED=false`。

## 2026-09-29 Visory-G020 合入后状态闭环

- PR #38 已按授权以普通 merge 合入：实际 PR head SHA `528baa072d32f0242cfdcfa8bb7b1314de19db78`，merge commit `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`，`merged_at=2026-09-29T04:01:18Z`，PR 已 `closed`；未使用 squash 或 rebase。
- 合入后 Run `36520276484`（`workflow_dispatch`，`main`，head SHA `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`）的 Governance and repository boundaries、Python deterministic gate、Web lint and build 均 `completed / success`。
- 实时 `git ls-remote origin refs/heads/main` 与缓存 `origin/main` 均为 `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`；本地 `main` 保持原值 `46804661dbb897433f114c25898c8da7021254a1`，仅作为远程 main 的祖先，未被覆盖或快进。
- PR review 只读复核无 submitted reviews、无 review threads、无 conversation comments；完整改动边界只覆盖 WP-0207，未启动 WP-0301 或其他相邻 Work Package。
- 当前状态：Visory-G020 = `COMPLETE`；WP-0207 = `IN_PROGRESS`；production certification = `NOT CERTIFIED`；implemented work packages = `13/45`；`RELEASED = false`。真实 Provider、生产数据库、真实 `/data`、生产调度和生产回填均未连接。
- 回滚方式：对完整 WP-0207 merge change set 执行 revert（merge commit `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`），不 reset、不 force-push，不做生产迁移或生产数据回滚。




## 2026-09-28 当前回合最新复核：实时远程基线成功

- 连续两次执行带连接超时保护的 `git ls-remote origin refs/heads/main` 均成功返回 `46804661dbb897433f114c25898c8da7021254a1`。
- 该 SHA 与本地 `HEAD`、本地 `main` 和缓存 `origin/main` 一致，`main...origin/main = 0/0`。
- 本次仅执行只读远程核验，未执行 `fetch`、`pull`、`reset`、`stash`、`commit` 或 `push`。


## 2026-09-28 当前回合复核：实时远程仍不可用

- 本回合执行 `git -c http.connectTimeout=10 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 ls-remote origin refs/heads/main`，因 GitHub 连接低速超时失败（exit 128）；本次未取得实时远程 SHA。
- 本地 `HEAD`、本地 `main` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，`main...origin/main = 0/0`；未执行 `fetch`、`pull`、`reset`、`stash`、`commit` 或 `push`。
- 实时远程基线继续记录为 `BLOCKER`；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 本轮最小充分验证：Backfill/API/Contract Python `188 passed, 4 warnings`；隔离 `postgres:16` integration `16 passed, 2 warnings`；Contract Registry、治理检查、受影响 Python `py_compile`、`git diff --check` 通过；Backfill Web Vitest `9 passed`，修改文件定向 ESLint、`tsc -b`、Vite build 通过。

## 2026-09-28 当前回合最终复核：实时远程阻断

- 本回合最后一次 `git ls-remote origin refs/heads/main` 因连接 `github.com:443` 失败（exit 128）；不能把缓存 `origin/main` 当作本次实时远程成功证据。失败前后本地 `HEAD`、本地 `main` 与缓存 `origin/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- 当前工作树仅包含 WP-0207 未提交改动；未执行 `fetch`、`pull`、`reset`、`stash`、`commit`、`push` 或 PR。WP-0206 的代码、状态文档和 Run `34581431121` 证据未被当前工作树覆盖，未发现其状态与实现/既有 CI 证据矛盾。
- 最新本地定向套件为 `189 passed, 15 skipped, 4 warnings`；隔离 PostgreSQL 16 Backfill integration 的既有成功证据为 `16 passed, 2 warnings`。本地 Web 修改文件 ESLint、`tsc -b`、Vite build 和 Backfill Vitest `9 passed` 通过；全量 Web ESLint 仍有 41 个未修改既有错误。
- 实时远程基线缺口记录为 `BLOCKER`；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。

最后更新：2026-09-28
最后更新：2026-09-28

## WP-0207 当前回合补验（2026-09-28）

- 实时 `git ls-remote origin refs/heads/main` 已成功返回 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD`、`main` 和缓存 `origin/main` 一致。
- 使用隔离临时 `postgres:16` 容器执行 Backfill integration，结果为 `16 passed, 2 warnings`；容器与临时密码已清理，未连接生产资源。
- BackfillWorker 现累计 checkpoint/Projection 的 `differences_summary`，不再在正常分区 checkpoint 和最终聚合中丢失摘要；相关定向 Python 套件为 `189 passed, 15 skipped, 4 warnings`。
- WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。远程 WP-0207 阻断 CI、七类数据完整执行/发布和生产资源认证仍未完成。

## 1. 当前结论

文档状态：可执行基线已形成。

工程底座状态：DSA 固定提交 `fb4735a1055caefa2396982af3b09121feb9ff30` 已完成导入和双基线验收，状态为 `IMPORTED / VERIFIED`。导入代码中的 React/FastAPI、Legacy SQLite、内存 Task Queue、分析、LLM、报告、通知和数据 Fetcher 仍是迁移基线，不能作为 Visory 新契约已实现的证据。

目标架构状态：implemented work packages 与远程 main 已合入并验收计数均为 `15/45`；`WP-0001`、`WP-0002`、`WP-0003`、`WP-0101`、`WP-0102`、`WP-0103`、`WP-0104`、`WP-0201`、`WP-0202`、`WP-0203`、`WP-0204`、`WP-0205`、`WP-0206`、`WP-0301`、`WP-0302` 为 `VERIFIED`；WP-0207 为 `IN_PROGRESS`，其余 29 项 `NOT_STARTED`。WP-0301 已合入且通过合入后 CI，WP-0302 已经 PR #41 合入 `main=efe8e9b362cba13eca183c55be57bbbbc832b60b`，Run `37645716721` 三项成功。G013 等同一 WP 的 hardening 或状态闭环不重复计数；没有 WP 为 `RELEASED`。

最近合入并验收的 Work Package：`WP-0301 Indicator Registry 与 DAG`。PR #40 的实现 head `50b15b7f13b2787bde92f5ff96f093014165002f` 已以普通 merge commit `6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222` 合入，合入后 Run `36601155597` 的三项阻断 Job 均成功。当前准备的是 `WP-0302 Feature Partition/Snapshot/Bundle` 专用 PR；其分支验收与 PR 合入门禁分开记录，不宣称 M3 整体完成或生产认证。

交付阶段：MVP 一期为本地核心功能版（M0—M6 + WP-0701—0703）；MVP 二期为本地生产预演与服务器发布版（WP-0704 + M8）。未过 Local Release Gate 不得将 WP 标记为 `RELEASED`。

### Goal 与底座状态

| 范围 | 状态 | 证据 |
| --- | --- | --- |
| Visory-G001 | COMPLETE | [G001 进度与验收记录](GOAL-STATUS.md) |
| Visory-G002 | COMPLETE | [G002 进度与验收记录](GOAL-G002-STATUS.md) |
| Visory-G003 | COMPLETE | [G003 / WP-0001 进度与验收记录](GOAL-G003-STATUS.md) |
| Visory-G004 | COMPLETE / MERGED | [G004 / WP-0002 进度与验收记录](GOAL-G004-STATUS.md)；PR #3 merge commit `7513208` |
| Visory-G005 | COMPLETE / MERGED | [G005 / WP-0003 进度与验收记录](GOAL-G005-STATUS.md)；PR #4 merge commit `98ab97e`；Runs `33265028192`、`33265537543` 全绿 |
| Visory-G006 | COMPLETE / MERGED | [G006 / WP-0101 进度与验收记录](GOAL-G006-STATUS.md)；PR #5 merge commit `01e1a986`；最终 Run `33288412520` 全绿 |
| Visory-G007 | COMPLETE / MERGED | [G007 / WP-0102 进度与验收记录](GOAL-G007-STATUS.md)；PR #6；merge commit `a9a640b`；最终 Run `33299476674` 三项全绿 |
| Visory-G008 | COMPLETE / MERGED | [G008 / WP-0103 进度与验收记录](GOAL-G008-STATUS.md)；merge commit `ea4f8b1`；PR #7；Run `33315054696` 三项全绿 |
| Visory-G009 | COMPLETE / MERGED | [G009 / WP-0104 进度与验收记录](GOAL-G009-STATUS.md)；PR #15 merge commit `9c03666740a1e7a90a616a2d774efc57ca5a0e6b`；真实认证 ASGI/浏览器旅程、PostgreSQL SSE replay 和连接清理通过；Run `33329710242` 三项阻断 Job 全绿 |
| Visory-G011 | COMPLETE / MERGED | [G011 / WP-0201 Registry Hardening](GOAL-G011-STATUS.md)；PR #20 merge commit `dbd8c271041b17323cff09ec00679f5f0ea59547`；Run `33373953485` 的 Governance、Python、Web 三项阻断 Job 全绿；进度保持 `8/45` |
| Visory-G012 | COMPLETE / MERGED / VERIFIED | [G012 / WP-0202 Raw Ingestion](GOAL-G012-STATUS.md)；PR #22；merge commit `1572a3f7f4bbeedc4fdeaafd03011b6a453073fe`；Migration `0007_wp0202_raw_ingestion`；Run `33405263970` 的 Governance、Python、Web 三项阻断 Job 全绿；进度 `9/45` |
| Visory-G013 | COMPLETE / VERIFIED | G013 / WP-0202 Provider Raw Schema Hardening; target migration `0008_wp0202_raw_schema_hardening`; PR #25 merged with head `766476d60bc3a1539dc8589fa2d830ed754b7117`, merge commit `71328fd512400a0cc0a2c38c128fead14a9a57d4`; final Run `33578007314` Governance/Python/Web all successful; progress remains `9/45` because WP-0202 is already counted |
| Visory-G014 | COMPLETE / MERGED | G014 / WP-0203 Core Canonical Normalization; PR #26 head `072484513b1f1a26d90bf6b33639fd8589af56a0`, ordinary merge commit `fbe34cbc0ee851ee99237a6b4e644abff5f48d66`; Run `33836754285` Governance/Python/Web all successful; Goal complete, WP-0203 remains `IN_PROGRESS`, progress `9/45` pending G015 |
| Visory-G015 | COMPLETE / MERGED / VERIFIED | [G015 / WP-0203 扩展 Canonical 数据集](GOAL-G015-STATUS.md)；Migration `0010_wp0203_extended_canonical_datasets`；四数据集、14 条 Provider Schema/Mapping 与质量血缘字段完成；PR #28 head `7e813208c710cd9ae3d43be541935e46085174e1`，普通 merge commit `76554416853314d6b3fe950f9d81a2c896320c27`；Run `33851938418` Governance/Python/Web 全绿；进度 `10/45` |
| Visory-G016 | COMPLETE / MERGED | [G016 / WP-0204 Snapshot Foundation](GOAL-G016-STATUS.md)；Migration `0011_wp0204_snapshot_foundation`；PR #30 merge commit `187550f434b64ea71d66452b748aba6943f8cb76`；Run `33941401645` 三项全绿；为 G017 提供不可变 Snapshot 基线 |
| Visory-G017 | COMPLETE / MERGED | [G017 / WP-0204 Backtest Core Certification](GOAL-G017-STATUS.md)；Migration `0012_wp0204_benchmark_dataset_extension`；独立 `benchmark_index_1d` Dataset/Provider/Raw/Canonical/Quality/Snapshot 血缘与 Formal Consumer Gate 完成；本地平台测试 `381 passed, 5 skipped` 与真实 PostgreSQL 16 集成 `61 passed`；PR #32 的 Run `34176102715` 中 Governance/Python deterministic gate/Web lint and build 三项阻断 Job 全部成功；实现提交 `6d28889b11e128f7d963acab469218c5c7955a8a` 以普通 merge commit `38bb737067e4e89bf766fb1b73023c3193cfa8ea` 合入 `main`；WP-0204 `VERIFIED`，`backtest_core` 代码能力门禁 `VERIFIED`，生产 `backtest_core` 数据 `NOT CERTIFIED` |
| Visory-G018 | COMPLETE / MERGED | [G018 / WP-0205 Daily Scheduler 与补充源](GOAL-G018-STATUS.md)；`Asia/Shanghai` 九阶段盘后调度、非交易日跳过、幂等依赖链、`a_stock_data` 主源与 `financial_api` 显式补充、19:00 Formal Deadline 和 20:30 Correction Audit 完成；本地平台 `390 passed, 5 skipped`、PostgreSQL 16 集成 `63 passed`；PR #34 head `d9255474dc52a4e36bf9eb33c5e967383a06f7a8`，Run `34264795037` 三项阻断 Job 全绿，普通 merge commit `76194dc378f689c0e0f34cc88d7a3989431a96fc`；WP-0205 `VERIFIED`，进度 `12/45`，生产数据 `NOT CERTIFIED` |
| DSA Baseline | IMPORTED / VERIFIED | 1126/1126 blob 验签；Python/Web 双基线；`baseline_regression_delta=0`；`web_lint_build_regression_delta=0` |
| Implemented Work Packages | 15/45 | 按下方 45 个唯一 WP 条目计数：15 个 `VERIFIED`、1 个 `IN_PROGRESS`、29 个 `NOT_STARTED`、0 个 `RELEASED`；15 个中 14 个已合入 main，WP-0302 为已验收未合入分支；WP-0207 和同一 WP 的重复 Goal/状态 PR 不计入 |

Historical Goal snapshot (2026-09-29): Visory-G020 / WP-0207 分批 Backfill is `COMPLETE / MERGED` after PR #38 merge commit `a1d31f9c3d16e62ea4fd78217c992bfe96dc33a8`; the WP-0207 implementation added BackfillBatch/TaskRequirements/Projection contracts, a fixed seven-stage Durable Task control chain, controlled Backfill Task creation, deterministic MONTH/YEAR partition planning, existing Durable Task child-task coordination, checkpoint validation, idempotent fixture publication, and Operations/P-DATA observation entry points. Implemented work packages were `13/45`; WP-0207 is not `VERIFIED` or `RELEASED`; no real Provider, production database, real `/data`, production scheduler, or production backfill certification is included.

### WP-0207 当前回合复核（2026-09-28，远程基线与定向套件）

- 当前分支为 `main`；本地 `HEAD`、本地 `main` 与缓存 `origin/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`。
- 本轮使用 `git -c http.connectTimeout=5 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=5 ls-remote origin refs/heads/main` 进行实时远程复核，因无法连接 `github.com:443` 失败；因此本轮不能把缓存 `origin/main` 作为实时远程成功证据，未执行 `fetch`、`pull`、`commit`、`push` 或 PR。
- `tests/platform/test_backfill.py tests/platform/api/test_generated_contracts.py` 定向套件为 `175 passed, 3 warnings`；`git diff --check` 通过。WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
### WP-0207 当前回合补验（2026-09-28，批次查询一致性）

- 修正 `BackfillService.get_batch` 的重复记录处理：查询窗口扩大为 2 条并检查 `has_more`，同一 `batch_id` 存在多个 Durable Task 记录时返回稳定 `BACKFILL_BATCH_AMBIGUOUS`，不再静默选择第一条记录。
- 新增重复批次查询 fail-closed 回归；`tests/platform/test_backfill.py` 当前为 `169 passed, 2 warnings`（该条为本轮批次查询补验时的局部快照）；本轮联合定向套件为 `183 passed, 15 skipped, 4 warnings`。受影响 Python `py_compile` 与 `git diff --check` 通过。
- WP-0207 继续保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`；本次仅收敛控制面可观测性，不改变七类数据完整执行、真实 Provider、生产数据库、真实 `/data`、生产调度或远程 CI 的未认证状态。

### WP-0207 当前验证补充（2026-09-27）

- Backfill 前端 API 的普通异常已统一脱敏为公开不可用文案，可信 API Envelope 仍仅投影公开错误字段；`platformBackfill` 定向 Vitest 为 `2 passed`。
- 新增只读 P-DATA 阶段链下钻 `GET /api/platform/v1/data-quality/backfills/{batch_id}/stages`；BackfillService 复用 `TaskListQuery(resource_id=..., task_type="backfill")`，固定路线图排序并对缺失批次、重复阶段和错误依赖 fail-closed；不创建 Task、不发布业务对象。
- 本轮 Backfill/阶段链/P-DATA/generated contract 定向 Python 套件为 `173 passed, 4 warnings`；本地 Docker `postgres:16` tmpfs/loopback 临时容器中的 Backfill integration 为 `16 passed, 2 warnings`。
- 本地 Docker `postgres:16` tmpfs 隔离容器中的 Backfill PostgreSQL integration 为 `16 passed, 2 warnings`。排除两个因未安装 `markdown2` 而无法导入完整 API 应用的既有模块后，`tests/integration/platform` 为 `81 passed, 3 warnings`；完整目录收集仍有 2 个同源 `ModuleNotFoundError: markdown2` 错误。排除三个同源 API 模块后，`tests/platform` 为 `549 passed, 5 skipped, 4 warnings`；完整目录收集仍有 3 个同源错误。持久化 `pg` 容器为 `Exited (255)`，未启动、未复用、未修改。
- bundled Node.js `v24.19.0` 直接运行项目本地 ESLint、`tsc -b`、Vite build 均通过；系统 Node.js `v16.20.2` 下的 `npm run lint/build` 受 Node/Vite 版本限制失败，未修改 Web 依赖。
- WP-0207 仍为 IN_PROGRESS、生产认证 NOT CERTIFIED、进度 13/45；本地 Docker PostgreSQL deterministic fixture 证据不代表真实 Provider、生产数据库、真实 /data、生产调度或生产回填已认证。
### WP-0207 当前回合补验（2026-09-28）

- 本轮再次尝试 `git ls-remote origin refs/heads/main` 时连接被远端重置；本地 `main`、缓存 `origin/main` 与 HEAD 仍一致，最近一次成功的实时复核仍返回 `46804661dbb897433f114c25898c8da7021254a1`，未执行 fetch、pull、commit、push 或 PR。
- 本轮使用 bundled Node.js `v24.19.0` 执行修改文件定向 ESLint 与 `npm run build`，均成功；全量 `npm run lint` 仍有 41 个既有未修改路径错误，构建产物包含 `BackfillPage` chunk。Docker 可用性探测未在本轮得到终态，因此没有新增 PostgreSQL 运行结果，继续引用此前隔离 `postgres:16` 证据。
- 随后使用临时 `postgres:16` 容器（tmpfs、loopback-only、独立数据库）实际执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 1 warning`；容器和临时密码文件已清理，未复用持久化数据库。

- 基线复核：当前分支为 `main`，本地 `HEAD`、本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`；未执行 fetch、pull、commit、push 或 PR。
- WP-0206 复核：GitHub 只读结果确认 PR #36 已合入、状态收尾 PR #37 已合入基线 `46804661dbb897433f114c25898c8da7021254a1`；PR #37 记录的 Run `34581431121` 三项阻断 Job 为成功。该历史证据不等同于 WP-0207 远程 CI。
- WP-0207 相关 Python 定向套件为 `389 passed, 53 skipped, 3 warnings`；隔离 `postgres:16` tmpfs/loopback 临时容器中的 `tests/integration/platform/test_backfill_integration.py` 为 `16 passed, 1 warning`。未配置环境的跳过项未被计入 PostgreSQL 通过证据。
- 本轮随后完成的完整 scripts/ci_gate.sh 离线 backend gate 为 6852 passed, 82 failed, 88 skipped, 4 deselected, 572 subtests passed；失败集中在既有 Codex transport/process、Local CLI、SQLite/Storage、screening 和 system-config 路径，未涉及 WP-0207 改动，故不据此扩大范围修复。
- Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、受影响 Python `py_compile`、`git diff --check` 均通过；Backfill 前端定向 Vitest 为 `7 passed`，bundled Node.js `v24.19.0` 下 Web lint/build 均通过。
- 完整 Web Vitest 为 `1107 passed, 3 failed, 2 skipped`；失败位于未被 WP-0207 修改的 `DecisionSignalsPage`、`AlertRuleForm`、`SettingsField` 既有测试路径，本轮不扩大范围修复，但不能将完整 Web 测试宣称为通过。新增 P-DATA 与 Backfill 四个公开入口未知异常脱敏回归后，WP-0207 定向 Backfill/API/Contract 套件为 `182 passed, 15 skipped, 3 warnings`；WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。


### WP-0207 当前回合 PostgreSQL 补验（2026-09-28）

- 使用临时 `postgres:16` 容器、`tmpfs`、`127.0.0.1` 随机端口、独立测试数据库和临时凭据执行 `tests/integration/platform/test_backfill_integration.py`，结果为 `16 passed, 2 warnings`。
- 覆盖 MONTH 1/YEAR 12 pilot、dry-run/plan-only、checkpoint 恢复、幂等、取消/失败、fallback/quarantine/unavailable、Correction 不覆盖旧 Snapshot、七阶段 StageChain 和受控依赖 Task；测试资源已清理，未连接生产数据库。
- 该结果属于隔离 deterministic fixture 证据，不证明真实 Provider、生产 `/data`、生产调度或生产回填认证；WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED`。

## 2. 状态定义

```text
NOT_STARTED  尚无目标代码与验收证据
IN_PROGRESS  有当前实现分支/工作树，Exit Gate尚未通过
BLOCKED      有明确外部依赖或决策阻断，并记录证据
VERIFIED     代码、Migration、测试和本地/集成证据通过
RELEASED     已部署且通过运行观察和回滚/恢复要求
```

implemented work packages 仅统计当前 WP 表中状态为 `VERIFIED` 或 `RELEASED` 的唯一 WP；不统计 `IN_PROGRESS`，不按 Goal/PR 数量计数。`VERIFIED` 可以是未合入的实现分支，必须另列已合入计数与 CI 所属 HEAD；`MERGED` 不自动等于 `RELEASED`。

状态不能由文档存在、代码行数、单个单元测试或主观描述更新。`VERIFIED/RELEASED`必须在“证据”列链接到代码、Migration、测试命令结果和运行产物。

## 3. Work Package状态

| WP | 交付物 | 状态 | 证据 |
| --- | --- | --- | --- |
| WP-0001 | Contract Registry与公共Schema | VERIFIED | Commit `5537569`；PR #2；GitHub Actions Run `33242596600` 的 Governance、Python、Web 三项阻断 Job 全绿；平台契约测试 93 passed |
| WP-0002 | PostgreSQL与Alembic基础 | VERIFIED | 实现 head `32b318a`；PR #3；Migration `0001_wp0002_baseline`；GitHub Actions Run `33250185521` 三项阻断 Job 全绿；Python 6487 passed，含 PostgreSQL 16 真实集成验收 |
| WP-0003 | API Envelope、Error与生成类型 | VERIFIED | PR #4；首轮 Actions Run `33265028192` 三项阻断 Job 全绿；Python 6522 passed；平台契约 35 passed；Legacy/API 定向回归 112 passed；无新增 Migration |
| WP-0101 | Asset Identity与Alias Resolver | VERIFIED | 实现提交 `a272b25`；PR #5；Migration `0002_wp0101_asset_identity`；GitHub Actions Run `33288021328` 三项阻断 Job 全绿；Python 6549 passed，含 PostgreSQL 16 Migration、排他约束、Quarantine、并发、事务与连接清理验收 |
| WP-0102 | Storage Namespace与Artifact Publisher | VERIFIED | [G007 / WP-0102 进度与验收记录](GOAL-G007-STATUS.md)；实现 head `92ddde7`；PR #6；Migration `0003_wp0102_artifact_registry`；平台 218 passed、本地 PostgreSQL 16 集成 15 passed；Run `33299055144` 三项全绿，Python 6591 passed |
| WP-0103 | Durable Task Control Plane | VERIFIED | [G008 / WP-0103 进度与验收记录](GOAL-G008-STATUS.md)；实现 head `826aacfa2965c98efff8a8795a46dc9f72edec5f`；PR #7；Migration `0004_wp0103_durable_task_control_plane`；平台 257 passed、5 skipped，本地 PostgreSQL 16 集成 30 passed，Legacy 定向回归 106 passed；Run `33314470672` 三项全绿 |
| WP-0104 | Operations最小页面 | VERIFIED | [G009 / WP-0104 进度与验收记录](GOAL-G009-STATUS.md)；PR #9、#12、#13、#14、#15 已合并；真实认证 ASGI/浏览器旅程、PostgreSQL SSE replay 和连接池清理通过；平台 260 passed、5 skipped；集成目录本地 PostgreSQL 16 实例 31 passed（清理后默认 31 skipped）；Playwright 6 passed + 真实认证 1 passed；Run `33329710242` 三项阻断 Job 全绿 |
| WP-0201 | Dataset/Provider Registry | VERIFIED | [G010 / WP-0201 进度与验收记录](GOAL-G010-STATUS.md)；实现 head `77a38e5bacc85e986d8062a55d0d867ec9387d89`；PR #17；merge commit `208f1d442f642a17d412c02eb06c3fb3e4b19ba3`；Migration `0005_wp0201_dataset_provider_registry`；补充 credential-safe Settings projection、GiST exclusion constraint 与真实 PostgreSQL 重叠拒绝测试；Run `33351050060` 三项阻断 Job 全绿 |
| WP-0202 | Raw Ingestion + Provider Raw Schema Hardening | VERIFIED | [G012 / WP-0202 进度与验收记录](GOAL-G012-STATUS.md)；PR #22；merge commit `1572a3f7f4bbeedc4fdeaafd03011b6a453073fe`；Migration `0007_wp0202_raw_ingestion`；平台 283 passed、PostgreSQL 16 integration 46 passed；Run `33405263970` 三项阻断 Job 全绿；G013 新增 Migration `0008_wp0202_raw_schema_hardening`、Provider Raw Schema Registry 与协调限流，平台 288 passed/5 skipped、PostgreSQL 16 integration 47 passed；PR #25 head `41c101236047eaf68618dd3d239bead649f1011f`；Run `33531064869` Governance/Python/Web 全绿 |
| WP-0203 | Canonical Normalization + Extended Datasets | VERIFIED | [G014 / WP-0203](GOAL-G014-STATUS.md) 已完成 Core；[G015 / WP-0203 扩展](GOAL-G015-STATUS.md) 新增 `0010_wp0203_extended_canonical_datasets`、四数据集、14 条 Provider Schema/Mapping 与质量血缘门禁；平台 `323 passed, 5 skipped`、PostgreSQL integration `55 passed`、Run `33851938418` Governance/Python/Web 全绿；PR #28 普通 merge commit `76554416853314d6b3fe950f9d81a2c896320c27`；进度 `10/45` |
| WP-0204 | DataSnapshot与Capability Gate + Backtest Core Certification | VERIFIED | [G016 / Snapshot Foundation](GOAL-G016-STATUS.md) 已通过 PR #30 和 Run `33941401645` 合并，Migration `0011_wp0204_snapshot_foundation`；[G017 / Backtest Core Certification](GOAL-G017-STATUS.md) 新增 Migration `0012_wp0204_benchmark_dataset_extension`、独立 `benchmark_index_1d` 契约及 Formal Consumer Gate，本地平台测试 `381 passed, 5 skipped`、真实 PostgreSQL 16 集成 `61 passed`；PR #32 的 Run `34176102715` Governance/Python deterministic gate/Web lint and build 三项阻断 Job 全部成功；实现提交 `6d28889b11e128f7d963acab469218c5c7955a8a`、普通 merge commit `38bb737067e4e89bf766fb1b73023c3193cfa8ea`、最终 `main` SHA `38bb737067e4e89bf766fb1b73023c3193cfa8ea`；代码能力门禁 `VERIFIED`，生产 `backtest_core` 数据 `NOT CERTIFIED` |
| WP-0205 | 16:00 Scheduler与补充源 | VERIFIED | [G018 / WP-0205](GOAL-G018-STATUS.md)；既有 Durable Task Control Plane 上的 `Asia/Shanghai` 九阶段盘后调度、交易日跳过、幂等/依赖、`a_stock_data` 主源与 `financial_api` 显式补充、19:00 Formal Deadline、20:30 Correction Audit 和 Operations 投影完成；无新增 Migration，Alembic head `0012_wp0204_benchmark_dataset_extension`；平台 `390 passed, 5 skipped`、PostgreSQL 16 integration `63 passed`；PR #34 / Run `34264795037` 三项阻断 Job 全绿；普通 merge commit `76194dc378f689c0e0f34cc88d7a3989431a96fc`；生产数据 `NOT CERTIFIED` |
| WP-0206 | P-DATA数据质量页面 | VERIFIED | [G019 / WP-0206](GOAL-G019-STATUS.md)；PR #36；Run `34581431121` 三项阻断 Job 全绿；普通 merge commit `3db5057acd0029c6fb3557fe6a90ebfb2c288acd`；生产数据 `NOT CERTIFIED` |
| WP-0207 | 分批Backfill | IN_PROGRESS | 历史控制面 PR #38 已合入；当前来源绑定/公开边界增量为 PR #42（OPEN / non-draft），远端 head `206b85c69e0e3c9181b496d468d0e743a688d98e`、Run `38871182213` 三项成功仅覆盖远端内容。2026-10-19 后续安全补丁仍在本地、未提交/推送；精确共享语料、真实 HTTP/SSE、checkpoint/resume、隔离 PostgreSQL、完整 gate 与本地判定见 [WP-0207 最新验收](WP-0207-END-TO-END-CLOSEOUT.md#2026-10-19-pr-42-公开文本安全与状态收敛)。8 条真实 routes BLOCKED、Capability UNVERIFIED、Coverage UNPROVEN；完整七阶段真实来源/历史 PIT/生产认证未完成，NOT CERTIFIED、RELEASED=false；不计入 VERIFIED 15/45 |
| WP-0301 | Indicator Registry与DAG | VERIFIED | PR #40；实现 head `50b15b7f13b2787bde92f5ff96f093014165002f`；普通 merge commit `6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`；合入后 Run `36601155597` 三项阻断 Job 均 `completed / success`。IndicatorDefinition/Builtin Registry/确定性 DAG、参数与定义 Hash、PIT/Capability/universe 门禁及 C-006/Golden 完成；无新增 Migration 或 runtime API。测试入口 `tests/platform/test_indicator_registry.py` 与 generated contract 均由该 CI 覆盖；生产 `NOT CERTIFIED`，`RELEASED=false`；若单独回滚 WP-0301，使用 `git revert -m 1 6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`，不包含在 WP-0302 回滚中 |
| WP-0302 | Feature Partition/Snapshot/Bundle | VERIFIED | [WP-0302 实现与验收](WP-0302-IMPLEMENTATION.md)；基于 `6aa9fa82e31ad0ad175cc1f6650ad7db67fa0222`；核心契约、增量/warmup/PIT、Schema/质量/覆盖率、correction lineage、固定引用、Formal pin 同事务、跨进程发布锁与 Migration `0013_wp0302_feature_store` 已验收。实现阶段：Feature 定向/隔离 PostgreSQL `56 passed`、核心行执行覆盖率 `87.86%`，Run `37568286328` 三项成功、Python `7119 passed`，均为实现提交 `a7ba8d055b3fccc8bfd5bd14eeabb27680ab0b8a` 的历史证据。本轮 PR-PREP：平台及隔离 PostgreSQL `761 passed, 5 skipped, 11 warnings`，治理/generated/syntax/flake8/deterministic/Web lint/build/diff 校验通过；未重测覆盖率；这些是 PR 创建前的准备证据，不能代替 PR 当前 HEAD 的阻断 CI。2026-10-19 实时核验：PR #41 已合入，merge/main=`efe8e9b362cba13eca183c55be57bbbbc832b60b`，Run `37645716721` 三项 SUCCESS；main 已为 15/45。上述 PR-PREP 为历史准备证据，不再表示当前未合入；未部署，生产 `NOT CERTIFIED`，`RELEASED=false` |
| WP-0303 | 市场宽度与情绪F2 | NOT_STARTED | — |
| WP-0304 | 板块与资金F2 | NOT_STARTED | — |
| WP-0305 | Hikyuu Cache Builder | NOT_STARTED | — |
| WP-0401 | Market Observation | NOT_STARTED | — |
| WP-0402 | Sector Registry与Observation | NOT_STARTED | — |
| WP-0403 | P-MARKET/P-SECTOR | NOT_STARTED | — |
| WP-0404 | P-DASH | NOT_STARTED | — |
| WP-0405 | 全球观察隔离 | NOT_STARTED | — |
| WP-0501 | MarketCloseFactPack | NOT_STARTED | — |
| WP-0502 | Review AI与Claim/Evidence | NOT_STARTED | — |
| WP-0503 | Review Projection与通知 | NOT_STARTED | — |
| WP-0504 | T+1/T+H Review Validation | NOT_STARTED | — |
| WP-0505 | P-REVIEW | NOT_STARTED | — |
| WP-0601 | StrategySpec Schema与安全DSL | NOT_STARTED | — |
| WP-0602 | Resolver/Compiler/Preview | NOT_STARTED | — |
| WP-0603 | A股市场规则与Hikyuu Adapter | NOT_STARTED | — |
| WP-0604 | Backtest Task与原子结果 | NOT_STARTED | — |
| WP-0605 | Prediction/Execution/Validation | NOT_STARTED | — |
| WP-0606 | P-STRATEGY/P-BACKTEST | NOT_STARTED | — |
| WP-0607 | 固定权重MVP | NOT_STARTED | — |
| WP-0701 | StockResearchFactPack/L0 | NOT_STARTED | — |
| WP-0702 | L1 Quick Research | NOT_STARTED | — |
| WP-0703 | P-STOCK/P-RESEARCH | NOT_STARTED | — |
| WP-0704 | L2 Deep Research（MVP二期、单只人工触发） | NOT_STARTED | — |
| WP-0801 | Owner Auth与Turnstile | NOT_STARTED | — |
| WP-0802 | 目标Compose与目录 | NOT_STARTED | — |
| WP-0803 | Cloudflare与NPM上线 | NOT_STARTED | — |
| WP-0804 | Backup/Restore | NOT_STARTED | — |
| WP-0805 | Release Candidate验收 | NOT_STARTED | — |

## 4. 状态更新要求

每次更新一行必须同时记录：

- 对应Commit/PR或当前工作树范围；
- Schema/Migration版本；
- 测试命令和结果；
- 运行环境和Fixture/Snapshot；
- 未验证项、风险和回滚；
- 若为页面，附可视证据；
- 若为`RELEASED`，附Deployment/Backup/Restore或运行观察Manifest。

Work Package定义与Exit Gate见[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)。
- 本轮新增阶段链连续性边界回归：`BackfillStageChainProjection` 现在只接受路线图连续前缀，拒绝跳过中间阶段的非连续 partial chain；WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前回合：`git ls-remote origin refs/heads/main` 曾短暂返回目标 SHA，但随后复核因连接 `github.com:443` 失败（exit 128）；本地 `HEAD`、`main` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，实时远程基线列为 BLOCKER。WP-0207 定向 Python 套件为 `185 passed, 15 skipped, 3 warnings`；PostgreSQL integration 因当前环境未配置连接变量而跳过，隔离 PostgreSQL 既有证据仍单独保留。WP-0206 代码、状态文档和 Run `34581431121` 未发现被当前未提交改动覆盖，WP-0207 继续为 IN_PROGRESS / NOT CERTIFIED / 13/45。
- 2026-09-28 当前 Goal 续验：本地分支 `main`、`HEAD` 与缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`，`main...origin/main = 0/0`；本次 `git ls-remote origin refs/heads/main` 因 GitHub 连接低速超时失败，记录为实时远程基线 `BLOCKER`，未执行 `fetch`、`pull`、`reset`、`stash`、`commit`、`push` 或 PR。定向 Python 为 `182 passed, 15 skipped, 2 warnings`；Backfill Web Vitest 为 `9 passed`；Contract/generation、治理检查、受影响 Python `py_compile`、定向 ESLint、`tsc -b`、Vite build 和 `git diff --check` 通过。全量 Web ESLint 的 41 个错误仍属于未修改路径既有问题；隔离 PostgreSQL `16 passed` 证据仍为 deterministic fixture，不代表生产认证。WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验补充：使用临时 `postgres:16-alpine`、tmpfs、loopback-only `127.0.0.1:55439` 和临时 Secret 文件执行 `tests/integration/platform/test_backfill_integration.py`，结果 `16 passed, 2 warnings`；测试容器和凭据已清理。该结果仅证明隔离 deterministic fixture，不代表真实 Provider、生产数据库、真实 `/data` 或生产回填认证。WP-0207 仍为 `IN_PROGRESS / NOT CERTIFIED / 13/45`。
- 2026-09-28 当前 Goal 续验：实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`，与本地 `HEAD`、`main` 和缓存 `origin/main` 一致，`main...origin/main = 0/0`。WP-0207 定向 Python/Contract 套件为 `182 passed, 15 skipped, 2 warnings`；Contract/generated exports、`check_ai_assets.py`、`check_visory_baseline.py` 均通过；范围审计未发现 WP-0301 或相邻 Work Package 路径。WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`。

## 2026-09-28 当前 checkout 与 TaskLease 脱敏复核

- 当前实际 checkout 为 `codex/wp-0207-backfill`；文档记录前代码工作树 clean，本轮当前仅有本节文档改动；HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`；本地 `main`、缓存 `origin/main` 与实时 `git ls-remote origin refs/heads/main` 均为 `46804661dbb897433f114c25898c8da7021254a1`，未执行 fetch、pull、reset、stash、commit 或 push。
- WP-0206 代码、`GOAL-G019-STATUS.md` 与既有 Run `34581431121` 证据未被 WP-0207 覆盖；WP-0207 仍保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
- 只读审计确认 `TaskLease.lease_token` 仅在 worker/Task Control Plane 内部使用；公共任务详情移除 `lease_token_hash`，列表/取消/重试仅返回 `TaskRecord`，SSE 仅返回 `TaskEventRecord`，Backfill/P-DATA Projection 不包含 raw lease token。当前未发现 WP-0207 直接的 raw lease token 公共暴露；本轮不修改既有 Durable Task 脱敏契约。
- 本轮不连接真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填；隔离 deterministic fixture 证据不等同于生产认证。

## 2026-09-28 当前回合续验结果

- 实时 `git ls-remote origin refs/heads/main` 成功返回 `46804661dbb897433f114c25898c8da7021254a1`；当前 checkout 为 `codex/wp-0207-backfill`，HEAD 为 `b5ab2da578cbad1e34e854cc3b67a0bc957185bb`，未执行任何 Git 写操作。
- `.venv` 定向 Python 套件 `tests/platform/test_backfill.py tests/platform/api/test_generated_contracts.py tests/integration/platform/test_data_quality_api.py` 为 `188 passed, 3 warnings`；临时 `postgres:16-alpine`、tmpfs、loopback-only 容器中的 `tests/integration/platform/test_backfill_integration.py` 为 `16 passed, 1 warning`，容器与测试凭据已清理。
- Contract Registry/generated exports、`check_ai_assets.py`、`check_visory_baseline.py`、22 个受影响 Python 文件 `py_compile`、`git diff --check`、Backfill Web Vitest `9 passed`、修改文件定向 ESLint、`tsc -b` 和 Vite build 均通过。
- 当前证据仍不包含真实 Provider、生产数据库、真实 `/data`、生产调度或生产回填认证；WP-0207 保持 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。

## 2026-09-28 当前回合远程阻断复核

- 本轮只读执行 `git ls-remote origin refs/heads/main` 因 GitHub 连接低速超时失败；本次未取得实时远程 SHA，记录为远程基线 `BLOCKER`。
- 本地 `main`、缓存 `origin/main` 仍为 `46804661dbb897433f114c25898c8da7021254a1`；当前 checkout 仍为 `codex/wp-0207-backfill`，未执行 fetch、pull、reset、stash、commit 或 push。
- 本地 WP-0207 验收证据保持有效。该历史记录形成时尚未完成远程复核；现已确认 PR #38 已存在，Run `36404883866` 的三项远程阻断 Job 均成功，因此本条“专用 PR 与远程阻断 CI 仍未建立”结论已被后续事实取代；状态继续为 `IN_PROGRESS / NOT CERTIFIED / 13/45`，不得标记 `VERIFIED` 或 `RELEASED`。
