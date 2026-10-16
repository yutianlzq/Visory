# WP-0207 端到端闭环验收记录

日期：2026-10-16。状态：本地 WP-only 候选补丁达到 `PR-ready`（非 ready for merge）；`WP-0207=IN_PROGRESS`，生产 `NOT CERTIFIED`，`RELEASED=false`。以下最新记录覆盖历史轮次的当前验收结论，不改写历史证据。

## 2026-10-16 dirty delta 续验：父门禁与来源证据

在下方初次审查后，已于同一 WP-0207 范围内关闭父 Backfill fixture 门禁反例：实际 pipeline plan 生成后、进度累计和业务子任务创建前，父入口复用 Raw `_configuration` 与 adapter 解析，按来源/Capability/Raw Schema 缺口投影 `UNAVAILABLE_*`；无效 plan 保持失败，不返回空成功。Raw 对经 Pydantic `model_copy(update=...)` 绕过校验的 route 重新验证类型、状态和 hash。新增离线与真实隔离 PostgreSQL 负向测试，确保无业务子任务、ProviderRun 或 RawObject 伪发布。之前的 `BLOCKED` 父门禁说明仅为当时历史发现，不再作为当前未修问题。

最终文件状态的 WP-0207 Backfill/API/Contract/Golden 定向 Python 为 436 passed / 122 skipped（skip 不计通过）；首次隔离 PostgreSQL Backfill/Raw/Foundation 为 117 passed / 0 skipped（发生于最终 route hash 校验前），之后对成功链及负向场景再验为 5 passed / 0 skipped。测试仅使用显式 fixture 和临时 loopback/tmpfs PostgreSQL，不证明真实来源、历史覆盖、PIT、合法零行或生产。两轮测试容器及临时凭据已限定清理。最终状态的 Web 定向 Vitest 52 passed、九文件 ESLint、`tsc -b`、Vite build 均 exit 0；最初误用系统 Node 14 导致 Vitest/ESLint/Vite 启动失败，改用已存在的 Node 24 后通过；未做本轮浏览器联调。27 文件 py_compile、critical flake8、生成契约、治理、baseline、`git diff --check` 均 exit 0；受影响五份 Python 文件完整 flake8 为 176 条，与续做前相同签名（exit 1），不称 strict lint 通过。

最终文件状态的 `bash scripts/ci_gate.sh all` 为 81 failed / 7051 passed / 173 skipped / 4 deselected（exit 1），另有 572 subtests passed。81 个失败节点逐一属于已核验 SHA 的同 HEAD 纯归档基线 84 个节点，`current-only=0`；两次环境不完全等价（纯 HEAD 使用隔离 PG），不能从节点重合推出相同根因、全门禁通过或数据库全覆盖。初次续做 gate 的 82 failed 发生于最终 route 修改前，仅保留在仓库外日志作为过程证据。完整状态/52 文件 SHA-256、原字节及两个保护工作树 HEAD/branch/status 字节再次复核一致；10 个本 Goal 修改路径有单独的精确逆向补丁与仓库外逐字节回滚证明。

当前工作树 52 个 dirty/untracked 项中，`AGENTS.md` 的跨项目治理增量原字节保留，不属于 WP-0207 候选补丁。仓库外生成的单一 WP-only binary patch 包含其余 51 个物理路径，并从共享 `docs/CHANGELOG.md` 精确剔除 AGENTS 治理条目；在仓库外纯 HEAD 镜像 `git apply --check`、实际 apply 及 51 文件逐字节对比均通过。该候选补丁可审查；不可直接把当前工作树所有改动整体提交，也未创建分支/commit/PR。后续 PR 若获授权，仍需刷新远端基线、按 hunk 排除治理变更、附受影响 Web 页面截图并取得 CI/review；本地 PR-ready 不等于 ready for merge。

八条真实 route 仍 `BLOCKED`、Capability `UNVERIFIED`、Coverage `UNPROVEN`。Provider/data/archive owner 的固定授权版本、语义/身份/revision、终止分页、完整 universe/合法零行和历史 PIT 包仍缺；它是未来来源/历史验收条件，而非以 fixture 代填的当前本地 PR 范围。未访问生产数据库、真实 `/data`，未运行生产调度或全历史回填；未执行 commit/tag/push/PR/merge/deploy。

## 2026-10-16 dirty delta 收敛与 PR 就绪审查

固定工作树和分支不变，HEAD/缓存 `origin/main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，开工 52 个 dirty/untracked 状态项。完整 binary diff、候选文件原始字节和 SHA-256、主 checkout/f468 的 HEAD/branch/status 已先保存至仓库外 `C:\Users\lzq11\.codex\task-evidence\WP-0207-DELTA-CONVERGENCE-20261016-102844-01a14287`；本轮未 fetch、切分支或覆盖旧封存。

本轮只修复 Raw dirty delta 中两项 BLOCKER：preflight 失败也进入既有 Task failure/终态路径，避免已 start 的 Task 留在 RUNNING；fixture factory 必须返回绑定当前 Provider/Dataset/Adapter/version 的 `FIXTURE/FIXTURE_ONLY` route，普通 transport 不得借允许 fixture 的 registry 放行。补充实际配置校验的离线反例及 PostgreSQL 终态/零 ProviderRun 断言；离线桩不代表 PostgreSQL 验证。

剩余 BLOCKER 与停止边界：

- `src/services/platform/backfill.py` 的 `_unavailable_contract` 仅检查 `fixture_only` 和 factory 可调用后提前返回，不校验 route 或 Raw Schema。离线调用真实父门禁与 Raw 配置方法：返回无效 route 的同一 factory 在父门禁未被调用、得到 `None`，Raw 则拒绝为 `RAW_SOURCE_ROUTE_FIXTURE_INVALID`。因此不能声称无效 fixture 在业务子任务创建前被拒绝；没有 transport fetch 或虚假业务发布的证据。需统一 preflight 契约及父入口回归，不再只给 Raw 追加补丁。
- `AGENTS.md` 的十个参考项目治理路由超出单一 WP-0207，保留原始字节、不擅自回滚。建议独立治理变更，连同 CHANGELOG 中对应治理条目单独归属；其余 51 个路径属于 WP-0207 候选集，不自动等于已验收。治理拆分不依赖业务增量；WP-0207 需关闭父门禁反例后再申请 PR 准备。

| 本轮实际验证 | 退出码 | 结果与边界 |
| --- | --- | --- |
| 生成契约 / AI 资产 / baseline | 0 / 0 / 0 | 契约无漂移，治理与本地基线检查通过 |
| 27 文件 py_compile / critical flake8 | 0 / 0 | 本轮两份 Python 文件完整 flake8 也为 0 |
| 27 文件完整 flake8 | 1 | 189 条；开工原始字节为 197 条，按文件/code/消息比较无本轮新增诊断，不称整体 lint 通过 |
| Backfill/API/generated/migration/route/Raw 定向 pytest | 0 | 297 passed / 39 skipped；skip 不计通过 |
| Contract Registry/Schema/Golden/Raw Contract + Backfill/Foundation | 0 | 135 passed / 82 skipped；包括 1 个非数据库 Backfill 场景 |
| Web 三文件 Vitest / 九文件 ESLint / tsc -b / Vite build | 0 / 0 / 0 / 0 | 52 tests；无本轮浏览器视觉或真实 API 联调证据，未运行全量 Web lint |
| `bash scripts/ci_gate.sh all` | 1 | 79 failed / 7049 passed / 172 skipped / 4 deselected；syntax、critical lint、deterministic 阶段通过，offline suite 失败 |
| 全 gate 节点归因 | 0 | 79 个失败均在已校验 SHA-256 的同 HEAD 纯归档基线 84 个失败节点中，current-only=0；九个失败测试文件与归档按 LF 比较一致。旧基线有 PostgreSQL、本轮无，不把总数差异写成修复或完整环境等价 |

Docker daemon 当前不可用，未启动服务、下载镜像或运行隔离 PostgreSQL，本轮数据库场景仅 skipped。历史 PostgreSQL 成功不是本轮通过证据。完整命令、退出码、节点集合、文件 Hash、剩余问题、拆分和回滚见同一仓库外证据目录的最终验收记录。八条真实候选 route 继续 `BLOCKED`、Capability `UNVERIFIED`、Coverage `UNPROVEN`；未新增真实来源/PIT/合法零行/生产认证，不访问生产数据库、真实 `/data` 或调度。

本轮按 B 类 `BLOCKED` 交付，停止追加实现补丁。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`；未执行 commit/tag/push/PR/merge/deploy。仅可在复核当前 SHA-256 后逆向应用本轮精确增量补丁，禁止整文件 restore/reset；不回滚开工前 52 路径成果或既有 migration/数据库状态。中文专题文档没有对应英文版本，本轮未修改双语首页。

## 2026-10-15 16:48 `a-stock-data` 来源绑定与本地封存

本轮继续使用独立工作树 `C:\Users\lzq11\.codex\worktrees\wp-0207-end-to-end-closeout\Visory`，branch `codex/wp-0207-end-to-end-closeout`，HEAD 与缓存 `origin/main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。开工时已有 39 个 WP-0207 dirty/untracked 路径；其 status、binary diff、当前字节、候选文件原始字节与 Hash 已保存到仓库外 `C:\Users\lzq11\.codex\task-evidence\WP-0207-A-STOCK-DATA-ARCH-20261015-152247-01a134a9`。15:23 与 16:48 两次 `git fetch origin --prune` 分别因 connection reset 和无法连接 GitHub exit 128，因此本轮只能确认缓存远程基线；不把当天 12:42 的成功远程核验冒充当前实时结果。主 checkout、f468、参考项目和其他容器均未写入、覆盖、回滚或清理。

架构增量把 `a-stock-data` 固定为受控 Adapter/toolkit，而非事实数据源：Release `3.10.2`、commit/tree、`SKILL.md` blob 和许可证 blob 固定进入候选路由；新增不可变 `ProviderSourceRouteEvidence`、确定性 route Hash 和 `ProviderRun.source_route_evidence`，请求 fingerprint 同时绑定 route Hash，响应 upstream 必须与批准路由一致。现有 8 个平台 Dataset 候选路由全部 `BLOCKED`，默认 Capability 仍 `UNVERIFIED`；缺 Dataset/Policy/Capability/Raw Schema/route 的阶段在业务子任务和 transport 前投影为 `UNAVAILABLE_*`。fixture 必须显式 `fixture_only=True`，普通 transport 即使实现 fixture route factory 也不能绕过门禁。旧 ProviderRun 字段允许 null 只为历史兼容，不补造旧来源证据。

`ProviderRun` contract 升到 `1.1.0`，新增可逆 migration `0014_wp0207_provider_source_binding`，同步 Contract Registry、OpenAPI、Golden 和前端生成类型；没有新增 Task Queue、Publisher 或 Repository。Backfill 原有 checkpoint、按月缺口、已有 Task 恢复、公开错误脱敏和 Operations 投影继续复用。固定 Adapter 不能补足 `valuation_daily`、`industry_membership`、`non_core_observation` 的正式平台契约，也不能把参考项目 README/SKILL、自述历史或重新下载的当前数据提升为 Coverage/PIT/revision 证据。

| 本轮验收项 | 四态结果 | 证据与限制 |
| --- | --- | --- |
| `a-stock-data` 固定版本、route Hash 与篡改/fixture 门禁 | 已通过（本地契约） | route 单元/负向/fixture 回归通过；8 条真实候选路由仍全部 `BLOCKED` |
| 新执行 ProviderRun 来源绑定、upstream/fingerprint 校验 | 已通过（本地实现） | Raw/Backfill scoped backend `303 passed`；generated contracts `7 passed` |
| 临时 PostgreSQL Raw→Canonical→Snapshot、checkpoint/恢复/事务 | 已通过（合成来源） | 最终 `96 passed / 0 skipped`，260.42 秒；不证明真实 Provider 或完整历史 |
| Web 公开错误与 Operations 投影 | 已通过（定向） | Vitest `52 passed`；9 个受影响文件 ESLint、`tsc -b`、Vite build 均 exit 0 |
| Python/Contract/治理 | 已通过 | 27 个受影响 Python 文件 py_compile、生成契约 `--check`、AI 资产、634 links/0 broken/0 imported secrets、`git diff --check` 均 exit 0 |
| 完整 `bash scripts/ci_gate.sh all` | 失败 | 显式 Python 3.12.9；收集 7,291、选择 7,287，用例运行到 31% 后因既有 Windows Codex 子进程/进程组测试失败 exit 1，未得到全量通过结论 |
| 全门禁失败最窄复核 | 失败（既有 Windows 路径） | 未修改的 `test_codex_app_server_gate_a.py`/`test_codex_tool_process.py` 为 `43 failed / 2 passed`；根因为 Windows 无 `os.killpg/getpgid`、pipe 不能用 `select` 等，与 WP-0207 来源绑定路径无交集，但 gate 仍不能标记通过 |
| 七阶段真实来源、2018 至今核心覆盖、两真实成功源 | 无法验证 | 8 条路由 blocked，Capability unverified，Coverage/PIT/revision/分页和授权 package 不完整 |
| 远程 CI/合入和生产认证 | 未运行 / 无法验证 | 当前 fetch 失败；未执行 commit/tag/push/PR/merge/部署，未访问生产数据库、真实 `/data` 或调度 |

最终 PostgreSQL 使用本机已有 `postgres:16-alpine`、loopback `127.0.0.1:45955`、tmpfs 和随机临时凭据。容器 `visory-wp0207-source-2147ffb762` 已限定删除，密码文件和 `postgres.env` 已删除；目标容器及凭据复核不存在，其他 5 个容器保持不动。Web 初次命令因 PowerShell 函数参数名误用 `$args`，曾误跑全量 Vitest（3 failed / 1157 passed / 2 skipped）、全量 ESLint（38 errors）并启动 Vite dev server；原日志保留，dev server 仅终止本轮会话，随后正确的定向命令全部通过，不能用后者覆盖前者的失败事实。

本 Goal BLOCKER 是全部真实候选 route 仍 blocked、Capability unverified、三个后续阶段正式 Dataset 契约缺失，以及 S01-S14、完整 universe/Coverage/PIT/revision/分页、两真实成功源质量证据和完整 gate 未闭合。完整 WP/生产认证另缺当前增量远程 CI/合入、生产资源范围、全历史在线执行、部署和回滚授权。FOLLOW-UP 是由 Provider/data/archive owner 交付版本化来源包并关闭 G01-G14，再在不改变既有控制面的前提下把相应 route 明确升级为可执行；Windows Codex 进程测试和全量 Web lint 归属独立 Legacy 工作，不在 WP-0207 堆叠补丁。

仅撤回本轮 `a-stock-data` 架构增量时，先核对交付 Hash 与本轮 manifest 一致，再恢复本证据目录 `baseline/original-bytes/` 中开工时已存在文件的原始字节；对本轮新文件只删除 manifest 明确标为 `existed=false` 且 Hash 匹配的路径。不得 reset/clean/stash，不得触碰其余开工前 39 个 WP-0207 路径、主 checkout、f468、参考项目或旧封存。未执行回滚。继续保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，历史 `G020=COMPLETE` 不等同本 Goal 完成。

## 2026-10-15 12:43 BJ、分页契约与恢复投影续验

本轮继续使用独立实施树 `C:\Users\lzq11\.codex\worktrees\wp-0207-end-to-end-closeout\Visory`，branch `codex/wp-0207-end-to-end-closeout`。开工保存 39 个既有 dirty/untracked 路径的 status、binary diff、当前字节及 HEAD 原始字节到仓库外 `C:\Users\lzq11\.codex\task-evidence\WP-0207-RESUME-20261015-01a134a9-02`；不 reset/clean/stash，不写主 checkout、f468 或参考项目。12:42 的 `git fetch --all --prune` 与 `git ls-remote origin refs/heads/main` 均 exit 0，HEAD、`origin/main` 和实时 main 同为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。

按用户追加的 10 次额度，对 `https://fuyao.aicubes.cn` 实际执行 8 次 GET，频率不超过 1 QPS；未下载 Market Dump、访问生产数据库、真实 `/data`、生产调度或写接口。`920799.BJ` 最近窗口日线返回 10 行，2025-01-01 至 2026-09-30 闭合窗口返回 424 行，最新估值返回 1 行并包含目标代码。该结果只证明单标的限定窗口与最新估值可读，不证明北交所 universe、退市覆盖、历史估值或完整历史。

历史分页得到明确失败证据：同一闭合窗口的 `offset=0/1/423/424/425/1000000` 全部返回相同 424 行，item SHA-256 一致，响应没有 `total/has_more/next_offset/page_size`。因此端点实际忽略 offset，无法通过分页到达终止页；S09/G05 从“未验证”收敛为 `FAILED_CONTRACT`。两轮认证证据分别位于 `C:\Users\lzq11\.codex\task-evidence\WP-0207-AUTH-API-VALIDATION-20261015-01a134a9` 和 `C:\Users\lzq11\.codex\task-evidence\WP-0207-AUTH-API-EXTENSION-20261015-01a134a9`，均不保存 Key、request ID 值或完整响应正文。

不依赖来源材料的当前实现无需追加运行时代码。固定范围复验为：Backfill 单元和公开投影 272 passed；Contract/Golden/Registry/generated 138 passed；Web Backfill/错误/Operations 3 files、52 passed；9 个受影响 TS/TSX 文件 lint、`tsc -b`、Vite build、17 个 Python py_compile、生成契约、AI 资产、634 links/0 broken/0 imported secrets 和 `git diff --check` 均 exit 0。公开 checkpoint 继续复用恢复时的输入 Hash、连续分区、固定引用及拒绝证据校验；coverage 继续返回按月执行缺口和既有 Task 的 `WAIT/RETRY/REVIEW/RESOLVE` 动作，同时固定 `coverage_state=UNPROVEN`，没有把执行月清单提升为逐证券逐交易日覆盖。

真实 PostgreSQL 本轮未能重跑：Docker Desktop API、127.0.0.1:5432、本机 PostgreSQL 服务和 `VISORY_TEST_POSTGRES_*` 均不可用；集成筛选实际为 1 passed / 61 skipped，exit 0，但 61 skip 不计通过。完整 gate 首两次因 Git Bash 的 `python3` 漂移到 Python 3.14.7 且缺 pandas 而在 deterministic 阶段 exit 1；显式绑定 `E:\Personal Manager\Visory\.venv\Scripts\python.exe` 3.12.9 后完整 `bash scripts/ci_gate.sh all` 为 82 failed / 7036 passed / 157 skipped / 4 deselected / 68 warnings，另有 572 subtests passed，exit 1，与此前记录的“固定解释器、无 PostgreSQL”结果一致。全量 Web lint 仍为 38 errors，exit 1；受影响文件 lint 通过不能替代全量结果。

| 本轮验收项 | 四态结果 | 证据与限制 |
| --- | --- | --- |
| `920799.BJ` 日线与最新估值 | 已通过（授权窄样本） | 10 行最近日线、424 行闭合窗口、1 行估值；不证明完整 BJ universe/历史 |
| 历史 offset 分页终止 | 失败 | 六个 offset 返回同一 424 行，`FAILED_CONTRACT`，无法到达终止页 |
| checkpoint 公开投影、按月缺口、既有 Task 恢复动作 | 已通过（本地无 PG） | 272 passed；公开校验、脱敏和 fail-closed 语义通过，不是实际进程/数据库恢复验收 |
| Contract/Golden/generated | 已通过 | 138 passed；生成器 `--check` 通过 |
| Web 定向、受影响 lint、类型与 build | 已通过 | 52 passed；9 文件 lint、`tsc -b`、Vite build 通过 |
| 真实 PostgreSQL 重启/事务/发布恢复 | 未运行 / 无法验证 | 环境未配置，1 passed / 61 skipped；skip 不计通过 |
| 完整 backend gate | 失败 | 82 failed / 7036 passed / 157 skipped / 4 deselected，exit 1 |
| 全量 Web lint | 失败 | 38 errors，exit 1；错误不在本轮五文档增量 |
| 七阶段真实来源与规定历史 Coverage/PIT | 无法验证 | 交易所过滤、退市 universe、offset、PIT/修订及双真实成功源仍阻塞 |
| 远程 CI/合入与生产认证 | 未运行 | 未执行 commit/tag/push/PR/merge/部署，未访问生产 |

本 Goal BLOCKER：Financial-API 的交易所过滤和历史 offset 契约失败、退市 universe/PIT/修订/完整 Coverage 与两真实成功源证据缺失，真实 PostgreSQL 本轮不可用，完整 gate 与全量 lint 仍失败。完整 WP/生产认证还需要明确生产数据库、真实 `/data`、调度、资源和全历史在线回填/部署授权。FOLLOW-UP 为 Provider 修复并固定接口版本、补齐 Coverage/PIT/修订 package，以及在可用临时 PostgreSQL 环境重跑当前 61 个 skipped 场景；不在 WP-0207 修复无关 Legacy gate/lint。

本轮仓库增量仅更新五份既有 WP-0207 文档：本文件、`WP-0207-SOURCE-UNBLOCK-PACKAGE.md`、`GOAL-G020-STATUS.md`、`IMPLEMENTATION-STATUS.md` 和 `docs/CHANGELOG.md`；没有业务代码、Schema、生成契约或测试字节变化。仅撤回本轮时，先核对这五份文件当前 Hash 等于本轮交付 Hash，再恢复 `WP-0207-RESUME-20261015-01a134a9-02/baseline/pre-resume-bytes/` 的对应原始字节；文件在本轮开工前均已存在，不能删除，也不得触碰其余 34 个既有 Goal 路径、主 checkout、f468、参考项目或旧证据。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`。

## 2026-10-14 22:54 真实来源最小解阻包

按 `AGENTS.md` 2.2 路由只读检查 `E:\Personal Manager\参考项目` 的 17 个指定文档/源码文件，未读取凭据、运行参考脚本、调用 Provider 或访问生产。已新增[WP-0207 真实来源最小解阻包](WP-0207-SOURCE-UNBLOCK-PACKAGE.md)，将 Provider endpoint/Adapter/字段/单位/Null/时区、分页、PIT、修订/取消、合法零行、历史 Coverage、S01-S14 授权脱敏样本和 G01-G14 fail-closed 验收标准整理为可直接转交给 Provider maintainer、数据 owner 和历史档案 owner 的输入要求。

本轮确认的关键阻塞包括：Financial-API 历史 K 文档声明 `offset` 但参考 SDK 未传分页参数，日历只覆盖近一年，估值 REST 只提供最新快照；公司行动缺稳定事件身份、revision/cancel 和披露/PIT，财务的报告日期不能自动作为 `available_at`；BaoStock 历史估值/状态不支持北交所；申万行业文件有生效日但没有已证明的披露时间和固定档案。参考目录当前文件只以本轮 SHA-256 固定，不能自动绑定 manifest 的历史提交或证明线上版本/授权。

本次只新增一份解阻文档并补录四份状态文档，不改后端、API、Web、测试或生成契约；固定 Python 下 `check_ai_assets.py` 通过，`check_visory_baseline.py` 检查 633 个相对链接且 0 个破损，`git diff --check` 通过，17 个参考文件 Hash 复验一致。上一轮本地合成对象链、浏览器、后端/Web/PostgreSQL 测试和完整门禁未重跑，来源性质不变；本轮未创建或清理 PostgreSQL 容器。最小包规范已完成，但真实 S01-S14、授权范围、Coverage/PIT/修订档案和双真实成功源仍未提供；完整 gate/lint、当前增量远程 CI/合入及生产认证也未闭合。继续保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 17:34 纯 HEAD 全量门禁归因与剩余验收

本节优先于下方历史记录，不改写此前失败、实现或封存。实施树仍为 `C:\Users\lzq11\.codex\worktrees\wp-0207-end-to-end-closeout\Visory`，branch `codex/wp-0207-end-to-end-closeout`，HEAD `efe8e9b362cba13eca183c55be57bbbbc832b60b`；17:23 `git fetch --all --prune` 与 GitHub main API 均 exit 0，`origin/main`、实时 main 和 HEAD 一致。本轮证据根为 `C:\Users\lzq11\.codex\task-evidence\WP-0207-GATE-ATTRIBUTION-20261014-01a134a9`。开工复验上一轮 603 个封存文件，保存整体 38 个 Goal 文件原始字节，并为主 checkout 三文档和 f468 52 个并行 WP-0303 文件追加只读保护快照；本轮未写、覆盖、回滚或清理两个保护 checkout 及其临时目录。

为解释上一轮相对旧结果新增的三个失败，本轮从同一 HEAD 用 `git archive` 生成不含全部 WP-0207 未提交增量的纯源码归档，ZIP SHA-256 为 `55d81a63c43ff22545f839d6543ae350728888ff1cc475a052570272c3a1ed33`。纯 HEAD 使用同一固定 Python 3.12.9、同一 Git Bash、独立 loopback/tmpfs `postgres:16-alpine` 和仓库既有依赖执行原始 `bash scripts/ci_gate.sh all`，实际为 `84 failed / 7025 passed / 10 skipped / 4 deselected`，另有 572 subtests passed，exit 1；当前增量门禁为 `83 failed / 7182 passed / 10 skipped / 4 deselected`，另有 572 subtests passed，exit 1。节点级集合比较结果为 `common=83`、`current_only=0`、`head_only=1`；当前全部 83 个失败均在纯 HEAD 复现，且这些失败所在测试文件与 HEAD 在换行规范化后字节一致。纯 HEAD 独有失败为 Provider cache 用例；通过数量不同来自当前增量新增的通过测试，不能用总数直接做因果判断。

三个重点节点的独立诊断也保留：搜索 deadline 在当前树和纯 HEAD 都可因浮点边界得到略大于 `0.2` 的剩余值；Local CLI 的预期 stat 错误已终止子进程，但 Windows 临时目录清理竞争会被外层 `OSError` 重标为 `process_start_failed`，当前树与纯 HEAD 诊断一致；Storage provider-turn 顺序在相同两测试序列中可失败后再通过，属于既有时序不稳定。上述结论只证明没有发现 WP-0207 增量新增的全量门禁失败节点，不把完整 gate 宣称为通过，也不在本 WP 修复无关 Legacy 路径。当前/纯 HEAD 的平台测试解析结果分别为 908/760 项，均只有同五个 Windows 符号链接或权限用例 skipped、无 failed；所有 skipped 仍不计通过。

| 本轮或继承验收项 | 四态结果 | 证据与限制 |
| --- | --- | --- |
| 当前增量与纯 HEAD 全量门禁归因 | 已通过（归因） | 83 个当前失败全部在纯 HEAD 复现，`current_only=0`；这不是 gate 通过 |
| 当前增量完整 `ci_gate.sh all` | 失败 | 83 failed / 7182 passed / 10 skipped / 4 deselected，572 subtests passed，exit 1 |
| 纯 HEAD 完整 `ci_gate.sh all` | 失败 | 84 failed / 7025 passed / 10 skipped / 4 deselected，572 subtests passed，exit 1 |
| Backfill 定向、实际 PostgreSQL/files 与对象固定引用 | 已通过（继承） | 601 passed / 0 skipped；22 回执、223 记录、226 文件；合成 transport/plan-only，不证明真实来源 |
| Web、Chromium、受影响 lint/types/build | 已通过（继承，本轮未重跑） | Web 66、Chromium 108 / 0 skipped；本轮客户端字节未改，上一 603 文件封存已复验 |
| 全量 Web lint | 失败（继承） | 38 errors，未用受影响 lint 通过替代 |
| 七阶段真实来源、规定完整历史与两真实成功源质量 | 无法验证 / 未运行 | 缺版本化接口、字段/单位/时区/修订/分页/PIT、授权样本或只读范围及历史覆盖包 |
| 当前增量远程 CI/合入及生产调度/回填/认证 | 未运行 | 未获 commit/push/PR/merge/部署或生产资源授权 |

临时 HEAD PostgreSQL 清理 exit 0：容器 `visory-wp0207-headgate-01a134a9` 及密码文件已移除，零其他活动客户端，其他容器从启动到清理保持不变，不删除镜像或 volume，不触碰生产资源。限定本地清理第一次因 Windows PowerShell 缺少 `Get-FileHash` 在任何删除前 exit 1；改用 .NET SHA-256 后复验归档 Hash，仅删除本证据根直接子目录 `head-source` 和三个 `tmp-*`，共 2300 个文件/205 个目录，保留 ZIP、日志和失败记录；未触碰仓库、主 checkout 或 f468。

本轮仓库实现和测试代码未修改；相对本轮开工快照仅四份状态文档变化，整体 Goal 仍为 38 文件，其余 34 文件保持开工字节。文件绝对路径、原因、开工/交付 Hash、实际 argv/cwd/exit/数量、保护复验、验收矩阵与限定回滚以本证据根最终 `changed-files.*`、`whole-goal-files.*`、`commands-results.md`、`acceptance-record.md`、`round-validation.json` 及 Manifest 为准。上一轮 603 文件封存保持只读不变。

失败原因已经收敛为两类：一是完整 gate 和全量 lint 仍实际失败，但本轮证明当前 gate 的 83 个失败不是 WP-0207 增量新增；二是完整 Goal 所需的真实来源和历史覆盖证据从未提供，无法合法执行或认证七阶段真实回填。继续实现/验收至少需要：固定 Provider endpoint/adapter 版本及字段、单位、时区、修订、分页、PIT/`available_at` 契约；获授权的脱敏样本或只读访问范围；覆盖核心日线 2018 至今、退市 universe、日历 2017 至次年末、财务 2017 年度起和其他数据有效起点的历史包与样本 Hash；两个真实成功源及冲突/质量证据。若要远程或生产闭环，还需分别授权 commit/push/PR/merge，以及生产数据库、真实 `/data`、调度、全历史执行、部署和回滚范围。

本 Goal BLOCKER 为上述来源/历史材料缺失及完整 gate/lint 未通过；完整 WP/生产认证另受两真实成功源、当前增量远程合入和生产资源授权阻塞。FOLLOW-UP 为把 83 个既有 Legacy 失败和 38 个 lint 错误交给相应模块/独立 WP 在 Linux CI 等价环境处理，不扩大 WP-0207。真实 backend→browser 联调、人工全页面、线上全历史执行和覆盖率百分比仍未验证。没有进一步安全且不依赖外部材料的 WP-0207 实现项；保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，历史 `G020=COMPLETE` 不用于关闭本 Goal。

仅撤回本轮四文档时，先核对当前 Hash 等于本轮交付 Hash，再恢复本轮 `baseline/original-bytes/` 对应原始字节；四路径开工前均已存在，不能删除。其余 34 个 Goal 文件、主 checkout/f468、上一封存和本轮证据不动，不 reset/clean/stash；遇后续修改立即停止。回滚未执行。AGENTS 2.2 的参考项目价值与具体源码路由已存在，本轮不重复修改；参考代码仍为只读证据，不能替代来源授权。未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 16:57 阶段租约隔离与实际 PostgreSQL 收尾

本节优先于下方历史记录，不改写旧失败或四份旧封存。实施树、branch/HEAD 不变；16:08 开工先复验原 Goal 36 文件与上一交付 Hash，保存原始字节、文件清单、diff 和两个原本干净的 Task 文件。主 checkout 三文档、f468 52 文件仅追加仓库外只读保护快照，已知 WP-0303 四文档允许后续变化，其余文件严格校验；不覆盖、回滚或清理并行成果及其测试临时目录。本轮证据根为 `C:\Users\lzq11\.codex\task-evidence\WP-0207-STAGE-LEASE-20261014-01a134a9`。

发现并复现七阶段执行器从全局 Backfill 队列领取后才检查 Task ID：更早的其他批次会被误租，随后报 `BACKFILL_STAGE_LEASE_INVALID`。修复在既有 `lease_next` 添加内部可选 Task ID 约束，同步用于排队领取、过期 LEASED 和过期 RUNNING 恢复；Repository 三条参数化查询保留状态/能力条件、排序和 PostgreSQL `FOR UPDATE SKIP LOCKED`。目标被锁时不转租其他任务，未指定目标的默认调度沿用。没有新增 REST/Schema、Queue、Publisher 或 Repository，不推进相邻 WP。

业务 red exit 1 保留，green 14 passed；新增一个单元回归及九个真实 PostgreSQL 场景，覆盖无关 QUEUED/LEASED/RUNNING 不被领取或恢复、目标自身 attempt 2、旧 token 无效、行锁及 BLOCKED/CANCELLED/能力门禁。首次定向 503 passed / 5 skipped，之后在真实临时 PostgreSQL 上完整执行同一相关范围及原 Task 控制面，最终 `postgres-full` exit 0 / 601 passed / 0 skipped，五个环境 skip 已实际补跑，不重复累计 probe 9 项。阶段链隔离场景只执行 plan-only 首阶段，不能作为七阶段真实对象执行完成证据。

最终 22 个回执保存 223 条 ProviderRun/RawObject/CanonicalPartition/QualityReport/DataSnapshot 固定记录、226 个实际文件及公开 Task/Backfill 投影，逐项复验记录 Hash、StorageRef、失败主源 Hash、Manifest 与文件；合成 transport 和 plan-only 来源性质不变。36 个包含中间执行的回执均复验；四个所属 runtime 完整 ZIP 归档校验后移除，失败产物和原始记录保留。初始回执插件的 float Hash、错误 Repository 导入，以及归档校验对 Manifest 报告 Hash、Decimal `1.0`/`1.00000` 表示的错误假设均已修正并保留失败日志/脚本，未修改发布契约或数据。

| 本轮或继承验收项 | 四态结果 | 证据与限制 |
| --- | --- | --- |
| Backfill 单元/API/Contract/Golden、原 Task 控制面及实际 PostgreSQL/files | 已通过 | 601 passed / 0 skipped，exit 0；合成来源，不证明线上历史 |
| 固定记录/文件/回执归档与恢复 | 已通过 | 最终 22 回执、223 记录、226 文件；实际 Hash/固定引用复验，不能将 plan-only 当业务发布 |
| 受影响 Python 与生成契约 | 已通过 | 17 文件 py_compile、生成器 --check，exit 0；本轮无公开 Schema/Web 改动 |
| AI 资产与治理 | 已通过 | exit 0；628 relative links / 0 broken / 0 imported secrets |
| 最终 diff 与交付 Hash | 以最终账本/封存复验结果为准 | 新增九文件清单与整体 38 文件；其余 29 个 Goal 文件保持开工字节 |
| Web、Chromium、受影响 lint/类型/build | 前轮已通过，本轮未重跑 | 继承 Web 66、Chromium 108 / 0 skipped；301 输入/静态/Golden 绑定另行只读复验 |
| 本轮完整 `bash scripts/ci_gate.sh all`，含独立 PostgreSQL | 失败 | 83 failed / 7182 passed / 10 skipped / 4 deselected、572 subtests passed，exit 1；其中平台集成 155 passed / 0 failed / 0 skipped |
| 全量 Web lint | 失败，继承 | 38 errors，尚未关闭；不能用受影响 lint 通过替代 |
| 七阶段真实来源、规定完整历史与双真实成功源质量 | 无法验证 / 未运行 | 缺版本化接口、字段/时间/修订/分页/PIT与已授权脱敏样本/只读范围 |
| 当前增量远程 CI/合入及生产调度/回填/认证 | 未运行 | 未获 Git 写入或生产资源授权，继续 NOT CERTIFIED |

完整 gate 首次在 `scripts/test.sh` 的 `python3` 漂移到 Python 3.14.7、缺 pandas 而 exit 1；保留原失败，通过测试子进程的 BASH_ENV 显式绑定固定 venv Python 3.12.9，不修改仓库脚本或安装依赖。固定解释器但未配置 PostgreSQL 的第一次全量为 82 failed / 7036 passed / 157 skipped；随后另建 loopback/tmpfs PostgreSQL 重跑为上表最终结果，所有 skip 均不计通过。与前轮 81 个失败节点相比最终 80 个重合，新增 CLI 输出 stat、搜索剩余 deadline、Storage provider-turn 删除三个节点，一项 Provider cache 失败本次未出现；测试源码与 HEAD 在换行规范化后相同，但没有完成等价全量基线或根因证明，不能把新增失败自动称为基线问题。详见 `gate-comparison-ci-all-postgres.json`。

本轮两套 PostgreSQL 容器及密码均已清理，身份/label、loopback、tmpfs、零活跃其他客户端、测试 DB 前缀和日志凭据检查通过；其他四个容器保持不变，不删镜像/卷。存储清理首次使用 Windows PowerShell 未解析到 Get-FileHash，在删除前失败；改用已核验的固定 PowerShell 7.6.5 后完成四个已归档 runtime 的限定清理，不清理全局 pytest 临时目录或 f468。16:08 fetch exit 128 / connection reset 保留；16:09:13 与 16:57:22 只读 GitHub main API 均 exit 0，main/缓存 origin/main/实施 HEAD 同为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，不把 API 核验当本轮 fetch 成功。

本 Goal BLOCKER 为完整 gate、全量 lint、来源/七阶段实际历史验收未闭合。完整 WP/生产认证还缺日线 2018 至今逐证券交易日与退市 universe，日历 2017 至 2027 年末、财务 2017 年度起、其他规定或可证明有效起点、两真实成功源质量、本增量远程 CI/合入和明确生产资源授权。按月执行缺口/已有 Task 恢复动作保持可查询，不能代替上述覆盖认证。FOLLOW-UP 为跨模块失败归因及就绪的 Linux CI 等价环境；真实 backend→browser 联调、人工所有页面和覆盖率百分比仍未验证。参考项目的价值/具体代码路由已在 AGENTS 2.2，本轮不重复编辑，参考代码不替代来源授权。

本轮九文件均已存在：三份后端、两份测试及四文档；整体 Goal 38 文件，两个 Task 文件开工时干净，其他七份包含本轮前 Goal 内容。`changed-files.md/json`、`whole-goal-files.md/json`、`commands-results.md`、`acceptance-record.md` 和 `round-validation.json` 保存绝对路径、原因、实际 argv/cwd/exit/数量及固定 Hash。四份旧封存仅校验自身文件，不能要求当前源码等于旧交付；本轮 Manifest 同时纳入实际对象的内层 Manifest，最终封存及独立只读复验结果为交付依据，不等于业务认证完成。

仅撤回本轮九文件时，先逐项核对当前 Hash 等于本轮交付 Hash，再恢复本轮 `baseline/original-bytes/` 九份原始字节；九路径均已存在，不能删除文件。不撤回其余 29 个 Goal 文件，不动主 checkout/f468/旧封存，不 reset/clean/stash，遇后续修改停止；回滚未执行。中文专题无英文对应副本，不扩大 README。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 15:55 Operations 请求归属与浏览器交付复验

本节为当前最新证据，保留下方旧失败和三次封存。实施树仍为 `C:\Users\lzq11\.codex\worktrees\wp-0207-end-to-end-closeout\Visory`，branch `codex/wp-0207-end-to-end-closeout`，HEAD `efe8e9b362cba13eca183c55be57bbbbc832b60b`。15:06:17 只读 GitHub main API、15:06:34 `git fetch --all --prune` 均 exit 0，15:43:04 main API 再次 exit 0，远程 main 与 HEAD 一致；不再把上一轮两次 Git 连接重置套用于本轮。完整 Goal 工具状态核验为 active，没有标记 complete。

本轮证据根为 `C:\Users\lzq11\.codex\task-evidence\WP-0207-OPERATIONS-LIFECYCLE-20261014-01a134a9`。15:06 开工先核对整体 36 文件与上一封存交付 Hash 一致，保存当前原始字节、清单、diff、HEAD/status；主目录三文档严格保护，f468 52 文件只追加只读快照。已知四份 WP-0303 文档后续变化继续按用户授权保存观察时刻版本，其余 48 文件严格核验；并行测试临时目录不清理。本轮实际只修改六个既有路径：Operations 页面、其测试及四份 WP-0207 文档；其他 30 个 Goal 文件不变。没有新增仓库路径；其中测试在本轮开工前已存在，不能按上一轮的新增语义删除。

四个请求生命周期反例在修复前为 4 failed / 4 passed：旧 Task 的迟到错误覆盖当前诊断、离开详情后迟到错误复活、旧筛选响应覆盖当前列表、成功 GET 把已断开的 SSE 标为健康。修复由 URL 派生筛选与标签，将详情/操作结果绑定当前路由身份，将列表绑定查询对象，并以请求序号拒绝同 Task/同筛选的旧 SSE 响应；离开路由后旧操作不刷新新 Task。SSE 仅由原生 onopen/event/onerror 标记连接状态，GET 成功不改变连接状态。沿用既有 API、公开脱敏和 Durable Task，不改变取消/重试事务，不新增 Queue/Publisher/Repository。

页面原三项 lint 已关闭：移除 URL 到 state 的同步镜像，加载状态从当前匹配结果派生，state 只在真正 API Promise 完成后更新。最终 effect 直接调用加载函数，没有用 Promise.resolve、queueMicrotask、setTimeout 或规则禁用绕过 lint。收尾又复现 SSE 重建时沿用旧连接健康状态，`sse-reconnect-red` 为 1 failed / 11 selected-out skipped；连接结果也绑定当前查询/视图，等待新连接自己的 open/event。测试在原四项基础上新增八项（页面共 12 项），包含同 Task/同筛选请求排序、连接重建和既有 TaskDetails Golden 成功刷新。Golden 经 Vitest Node 环境只读加载，未修改 Golden、Vite fs allowlist、依赖或全局浏览器类型。

保留本轮所有失败：`lint-green` 中间 2 errors / 1 warning；`web-targeted` 因 Web 根外的 `?raw` Golden import 未收集 Operations suite；`web-final` 为 64 passed / 1 failed（重复 QUEUED 文本断言），随后改为精确状态字段；`types-accepted` 缺 Node 模块类型，`types-node-reference` 的全局 Node 类型引出三处既有浏览器计时器类型冲突。最终使用测试内 Vitest 读取接口隔离类型后通过，未修改这些其他模块。一次 `web-isolated-golden` 实际只选中 4 files / 53 passed（两个 API 路径不存在），不算六套件完整结果；`web-delivery-complete` 正确六套件为 65 passed，追加连接重建后最终 `web-reconnect-final` 为 6 files / 66 passed。所有修复前/中间结果保留，不能累计成独立用例总数。

15:38:41 的初次 Chromium 106 passed 及静态 zip/绑定/截图完整保留。连接重建修复后，以独立 `accepted-browser/` 执行最终 `browser-reconnect-final`，15:54:57 结束，108 passed / 0 skipped（exit 0）：原四页面、双视口的 98 个脱敏/原生 SSE 场景，加十个双视口生命周期场景。直接验证旧 Task 成功回执、旧筛选失败、同 Task SSE 刷新排序、GET 成功后 SSE 仍断开及等待新连接自身 open。最后两个场景仍使用浏览器原生 EventSource，仅将 URL 路由到同一 loopback server 的可控 `/fixture-stream`，实际延迟新连接响应头，不模拟 onopen。浏览器仅访问 loopback 随机端口，API 全部为本地 fulfillment，外部请求阻断；未使用生产 Provider 或 backend→browser 联调。最终八截图在 `accepted-browser/delivery-screenshots/`，人工抽查任务详情移动端与 Backfill 桌面端。该目录的 `browser-delivery-cleanup.json` 证明 serverClosed/portReleased，零外部请求、零未声明 API，最终端口 55809 及初次端口 50132 已释放。

最终构建绑定 301 个前端输入 fingerprint `5ef26923bcdc5a8627aba8db3006c990cf1e0927243107647e98b550f1308ece`，revision `efe8e9b362cb`，并额外保存读取的权威 TaskDetails Golden Hash。`accepted-browser/browser-delivery-build-binding.json` 与最终静态 zip 固定实际交付字节。初次 fingerprint `b6b1cfcf621284988ff463fc6eeaeac1b95136fa16a12dd70e7bec3e1d225de0` 及 `browser-pre-reconnect-static.zip` 只绑定其当时 106 场景源码，不用于最终交付验收。

| 当前验收项 | 状态 | 证据与限制 |
| --- | --- | --- |
| 请求归属、公开脱敏、双视口及原生 SSE | 已通过 | Web 6 files / 66 passed，Chromium 108 passed / 0 skipped；本地 fixture API |
| 受影响 lint、类型与 build | 已通过 | 八个受影响文件 lint、tsc -b、Vite build 均 exit 0；Operations 三项错误关闭 |
| 全量 Web lint | 失败 | 38 errors / 0 warnings，exit 1；从上一轮 41 减少三项，未修无关模块 |
| 15 个 Python 编译、生成契约、治理及 diff | 已通过，以最终账本为准 | 本轮重跑，治理 626 links / 0 broken / 0 secrets；后端与生成契约字节保持开工版本 |
| Backfill 单元/API/Contract/Golden | 前轮已通过，本轮未重跑 | 原 507 定向、最近公开 API/Contract/Golden 165 为既有独立证据，不重复累计 |
| 实际 PostgreSQL/files 对象链 | 前轮已通过，本轮未重跑 | 73 passed / 0 skipped、13 场景 223 对象/223 文件；合成 transport，不证明真实来源 |
| 完整 bash scripts/ci_gate.sh all | 失败，未关闭 | 最近完整执行 81 failed / 7174 passed / 10 skipped / 4 deselected，572 subtests passed；本轮仅前端增量未重跑 |
| 七阶段真实来源、完整历史和双真实源质量 | 无法验证 / 未运行 | 缺版本化接口、字段/时间/修订/分页/PIT、授权样本或只读范围；不生成假数据或伪造 available_at |
| 本增量远程 CI/合入、生产调度/回填/认证 | 未运行 | 未获 Git 写入或生产范围授权，继续 NOT CERTIFIED |

本 Goal BLOCKER 仍为全量 lint、完整 gate 和来源/历史验收未闭合；Operations 受影响 lint 已不再列为 blocker。完整 WP/生产认证还缺核心 2018-01-01 至今逐证券交易日/退市 universe，日历 2017-01-01 至 2027 年末，财务 2017 年度起、行业/估值各自有效起点的真实覆盖证明，以及两真实成功源质量、本增量远程 CI/合入和明确生产资源授权。现有按月执行缺口与已有 Task 恢复动作仍可查询，但不等于证券逐日覆盖认证。FOLLOW-UP 为超出当前 WP 的 Legacy/其他模块失败、就绪的 Linux CI 等价环境；人工全页面、真实 backend 浏览器联调和覆盖率百分比未验证。

`changed-files.md/json` 给出本轮六文件绝对路径、原因、开工及交付 Hash；`whole-goal-files.md/json` 给出整体 36 文件及原始来源，`commands-results.md` 保存实际 argv/cwd/退出码/数量与失败日志。旧三份封存逐文件只读复验，新保护快照不修改旧 Hash；原 WP-0207 四个 PostgreSQL 容器/密码不存在，本轮未创建数据库或清理任何其他容器。最终状态、文件/保护/旧封存/清理复验以 `round-validation.json`、`manifest.json/.sha256` 和独立只读验证结果为准，不把封存本身等同业务验收完成。

只撤回本轮六文件时，先核对当前 Hash 等于本轮交付 Hash，再恢复 `baseline/original-bytes/` 的六份原始字节；六路径均已存在，不能删除测试。其余 30 个 Goal 文件、主目录/f468、旧证据和并行测试目录均不动，不 reset/clean/stash；遇后续编辑停止。ignored static 可用同一固定 Node 重建，源码回滚后当前截图不可继续作为绑定证据。回滚未执行。中文专题无英文对应副本，不扩大 README。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 浏览器验收与任务详情错误闭环

本节晚于 13:12 并行更新，保留下方历史、失败与旧封存。用户已持续授权保留 f468 此次及已知 WP-0303 四文档的后续变化；14:19 在新证据目录追加主 checkout 三文档及 f468 52 文件的只读原始字节/Hash、HEAD/status/diff。四份已知文档采用明确 allowlist 保存观察时刻字节，不再要求它们等于历史 Hash；其余 48 个文件、主 checkout 与实施树继续严格校验。未写、覆盖、回滚或清理这两个保护 checkout，也未清理 WP-0303 临时目录。完整 Goal 的工具状态已恢复为 `active`，没有缩小目标或标记 complete。

本轮证据根为 `C:\Users\lzq11\.codex\task-evidence\WP-0207-BROWSER-ERRORS-20261014-01a134a9`。首次 `baseline` exit 1 保留在原日志和 `failed-baseline-source/`，新命令 `baseline-confirmed` exit 0；编辑前原有 34 个 Goal 文件全部匹配上一交付 Hash。Operations 页面原本与 HEAD 一致，修改前另存 `baseline/additional-original-bytes/`；新测试路径不存在的开工事实另行记录。整体 Goal 现在为 36 文件（28 tracked 修改、8 新增），本轮仅改六文件：Operations 页面、新回归测试及四份 WP-0207 文档；此前其他 30 文件字节保持不变。

真实 Chromium 页面验证发现两个公开状态问题：列表刷新共用 `setError(null)` 会清掉任务详情请求的诊断，且详情失败时 `!details` 会持续显示加载骨架。修复将列表、详情和受控操作错误分开保存；列表筛选/标签刷新不清详情或操作错误，离开详情路由清除旧详情诊断，详情失败清掉旧对象并显示明确不可用提示。仍通过原 `formatPlatformTaskError` 脱敏，不新增 API、Queue、Publisher 或 Repository，不改变 Task 事务或重试状态。修复前原始页面三个确定性回归均 failed；骨架反例另跑 1 failed / 3 selected-out skipped。最终六文件 Web 定向为 58 passed，包括四个新增页面回归，不将此前 57 passed 或重复浏览器运行累计为独立测试总数。

首次浏览器命令 `browser-errors` 为 exit 1 / 98 failed，原因是默认寻找不存在的 headless shell 1243，页面断言未执行；未安装或下载浏览器。显式绑定已缓存 Chromium 1208 后，`browser-errors-pinned` 保留部分 41 passed、1 failed、154 未运行及 suite 错误：验证脚本误收集失败副本、未处理 Shell 的只读 screening/status，同时复现了实际任务详情告警丢失。修正验证隔离及页面后，中间 `browser-errors-final` 98 passed；补齐不可用展示后的最终 `browser-errors-delivery` 于 14:41:55 结束，exit 0 / 98 passed / 0 skipped。失败产物、脚本副本和中间成功证据均保留，只有最终交付绑定用于当前页面验收。

最终浏览器覆盖 Backfill、P-DATA、Operations 列表和任务详情，1440×1000 / 390×844 两个视口，各 12 类错误/控制反例，并有两个原生 EventSource 刷新场景。验证 token、lease、连接串、响应正文、Windows/POSIX 路径、stack、带凭据 URL、JWT、伪造 request ID 与 generic body 不出现在可见 DOM；合法公开 code、Request ID 和安全消息可见。任务详情 token 场景还执行列表筛选刷新，确认诊断仍在且失败不是加载状态。retryable 由真实格式化函数的 Vitest 契约验证，页面没有把它伪装成新的操作按钮。SSE 用浏览器原生解析/刷新，只验证事件 body 不被渲染；不是后端 SSE 生产投影或真实 backend→browser 联调。

浏览器只访问 loopback 随机端口的静态产物，全部 API 由本地反例 fulfillment 提供，阻断外部请求，未访问 Provider、生产数据库或真实 `/data`。测试产物绑定 301 个前端输入的 fingerprint `323bf10f76811b09cf3724b65453dc568cb4683d968123888111668ecd4116f9` 与 build revision `efe8e9b362cb`；实际加载的 Playwright 为 1.63.0，而不是把 manifest 的最低依赖声明当已安装版本。八张截图在仓库外 `delivery-screenshots/`，抽查任务详情移动端和 Backfill 桌面端；所有场景自动检查告警可见及视口边界，不声称手工点验全部页面。server 关闭、端口释放、零外部请求/零未声明 API 的结果由 `browser-delivery-cleanup.json` 给出。未留下本轮静态服务，也未创建 PostgreSQL 或下载依赖。

| 本轮/继承验收项 | 状态 | 证据与限制 |
| --- | --- | --- |
| 最终 Chromium 展示、任务详情筛选恢复、原生 SSE | 已通过 | 98 passed，exit 0；本地 fixture API，不是生产/真实来源验收 |
| Web 定向、类型与构建 | 已通过 | 6 files / 58 passed，tsc -b 与 Vite build exit 0 |
| Backfill 公开投影、API/Contract/Golden | 已通过 | 165 passed / 1 warning，exit 0；不与前轮 507 或 Golden 121 重复累计 |
| Python 编译与生成契约 | 已通过 | 原 Goal 15 个 Python 文件 py_compile，生成器 --check exit 0；本轮没有改后端字节 |
| 受影响 lint / 全量 lint | 失败 | 3 errors / 41 errors，均 exit 1；编辑前 Operations 页面 stdin 对照同样 3 errors，不关闭规则或顺手重构全仓 |
| AI 资产、治理、diff | 已通过 | 均 exit 0；治理 624 links / 0 broken / 0 imported secrets；保护与交付 Hash 另见封存逐项复验 |
| 实际 PostgreSQL/files 对象链 | 前轮已通过，本轮未重跑 | 73 passed / 0 skipped、223 对象/223 文件仍为合成 transport 证据，不变更其来源性质 |
| 完整 bash scripts/ci_gate.sh all | 失败，未关闭 | 最近完整执行仍 81 failed / 7174 passed / 10 skipped / 4 deselected、572 subtests passed；本轮前端增量未重跑完整后端 gate |
| 真实来源授权、七阶段实际历史、两真实成功源质量 | 无法验证 / 未运行 | 缺版本化来源与授权样本/只读范围，不把浏览器 fixture 或月末样本当历史完成 |
| 当前增量远程 CI/合入、生产调度/回填/认证 | 未运行 | 无 Git 写入或生产资源授权，保持 NOT CERTIFIED |

14:22:22 实时 main 核验及 14:23:04 fetch 均 exit 0，HEAD/origin/main/实时 main 同为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，branch 为 `codex/wp-0207-end-to-end-closeout`。最终文件绝对路径/原因、开工及交付 Hash 见 `changed-files.md/json` 与 `whole-goal-files.md/json`；真实 argv/cwd/退出码及失败日志见 `commands-results.md`。旧两份封存只读复验，不修改旧 manifest；本轮所属浏览器端口和此前 WP-0207 PostgreSQL/密码清理复验另记，新保护快照允许四个已知文档继续变化，不据历史字节回滚并行成果。

收尾两次 `ls-remote` 于 14:47/14:52 遇连接重置，均 exit 128，日志不覆盖成通过；14:53:33 通过固定 GitHub CLI 的只读 `GET git/ref/heads/main` 核验 SHA 仍为 `efe8e9b...`（exit 0）。这是当前远程 ref 的 API 证据，不证明 Git 传输已经恢复、CI 已通过或代码已合入。一次 lint 在仓库根执行而未找到 Web config 返回 exit 2，原记录保留；改在 Web cwd 重跑后实际仍为三项 lint 错误（exit 1），不把环境调用错误当代码回归或通过。

本 Goal BLOCKER 为受影响/全量 lint、原完整 gate 及真实来源/七阶段/规定完整历史等未闭合验收；完整 WP/生产认证还缺逐证券交易日覆盖、两真实成功源质量、本增量远程 CI/合入和生产资源授权/验收。FOLLOW-UP 为已复现的 Legacy 共享代理污染及其他跨模块基线失败、Linux CI 等价环境；不为变绿扩 WP 或增加 skip/超时。浏览器真实 backend/生产联调、人工全页面检查与覆盖率百分比未验证。风险在于 fixture 展示证据不能证明真实来源或生产发布，本地失败 gate 仍阻止完整关闭；历史 G020=COMPLETE 不改变本轮判定。

仅撤回本轮六文件时，逐文件核对当前 Hash 等于本轮交付 Hash：恢复四文档和 Operations 页的本轮原始字节，只移除本轮新增且 Hash 匹配的 OperationsTasksPage.test.tsx。不得移除原有八个中此前七个新增路径，不撤回前 30 文件，不触及主 checkout/f468，不 reset/clean/stash，遇后续编辑停止。ignored static 为可重建产物，回滚源码后需用同一固定 Node 重建，不能把当前截图继续绑定到旧源码。回滚未执行；中文专题文档无对应英文副本，不扩大 README 更新。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 保护确认后的封存复验

本节晚于下方 12:30 记录。首次新证据封存 `seal-final` 于 12:45 返回 exit 1：f468 的 CHANGELOG、IMPLEMENTATION-STATUS、WP-0303-B3-SOURCE-EVIDENCE-PREP 和 WP-0303-IMPLEMENTATION 在 12:33—12:41 出现新字节，与旧保护快照不符。该失败属于保护校验，不用于判断 WP-0303 内容是否正确，也不作为 WP-0207 业务回归。原失败日志、结果及对应脚本副本保留，未生成成功 manifest。

用户随后直接确认保留这四文档全部内容，并授权在本轮新证据目录追加保护快照、恢复完整 Goal。12:57:05 保存 `confirmed-protection-20261014T045705Z/f468/`：52 个 dirty/untracked 文件的原始字节、SHA256、HEAD/status 和 diff；其中四个变化逐项匹配用户已确认的版本，其余 48 个文件保持上一保护字节。快照位于 `C:\Users\lzq11\.codex\task-evidence\WP-0207-CI-ATTRIBUTION-20261014-01a134a9`，确认记录为 `confirmed-protection-authorization.json`。没有覆盖、回滚、清理或修改 f468 的代码、文档和测试临时目录，也没有重写旧封存。

12:47 只读复验旧封存 2874 个文件，大小和 SHA256 均匹配，manifest Hash 仍为 `8afc3876ed04f32d4f16a672a1013588b00bee34d2a8e99b4e2991e05557f24c`；WP-0207 所属临时 PostgreSQL 容器及密码文件均不存在，当前其他 4 个容器未由本轮清理。12:58:30 实时 main 核验及 12:58:45 fetch 均 exit 0，实时 main、origin/main、实施 HEAD 仍为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。

恢复后的封存使用独立命令标识 `seal-confirmed`，继续复验新保护快照、主 checkout 三文档、旧封存、整体 Goal 34 文件及本轮四文档交付字节。成功判定以该命令实际退出码、`round-validation.json` 和 `manifest.json/.sha256` 的逐项复验为准；首次 `seal-final` exit 1 仍在本轮账本中，不覆盖成成功。完整命令/cwd/退出码见 `commands-results.md`，本轮四文档原因/原始及交付 Hash 见 `changed-files.md/json`，整体 34 文件见 `whole-goal-files.json`，patch 及当前字节分别见 `delivery.patch`、`delivery-bytes/`。

本次只补录四份 WP-0207 文档，未再次修改业务代码、测试断言、客户端或生成契约。本轮定向诊断结果及其因果限制仍见下方 12:30 节；前轮 507 定向、73 PostgreSQL/files（0 skipped）、121 Golden、54 Web 不是本次重新运行结果。完整 gate 的 81 failed / 7174 passed / 10 skipped 和全量 Web lint 的 41 errors 仍未关闭，真实来源、七阶段完整历史、双真实成功源质量、远程增量 CI/合入及生产认证仍缺证据。没有新增依赖、容器或生产访问，保持 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

本轮四文档的回滚仍以本轮 `changed-files.json` 为守卫：只有当前文件 SHA256 等于交付 Hash 时才可恢复 `baseline/original-bytes/` 对应原始字节；不撤回此前 30 个 Goal 文件，不删除此前 7 个新增路径，不触及主 checkout 或 f468。遇到后续编辑停止，不执行 reset/clean/stash；回滚未执行。中文专题文档没有对应英文副本，未扩大更新 README/README_EN。

## 2026-10-14 12:30 续做：CI 环境核验与情报失败归因

本轮从封存的失败证据继续推进验收，不重写 Backfill 或修复相邻模块。12:20 开工时 34 个 Goal 文件全部匹配上一交付 Hash；主 checkout 三文档、f468 最新确认的 52 个文件及 HEAD/status 均未变。另存仓库外 `WP-0207-CI-ATTRIBUTION-20261014-01a134a9/baseline/` 的文件清单、原始字节、diff 和状态；上一轮封存目录不写入。本轮仅更新本记录、GOAL-G020-STATUS、IMPLEMENTATION-STATUS 和 CHANGELOG，业务代码、测试断言及生成契约不变。

12:20:10 实时 main 核验和 12:21:07 fetch 均 exit 0，远程/main/实施 HEAD 仍为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。CI 配置使用 Ubuntu/Python 3.11；本机现有 WSL Ubuntu-22.04 为 `/usr/bin/python3` 3.10.12，pytest、SQLAlchemy、Pydantic、pandas、FastAPI、flake8、psycopg 均未安装，标准路径没有 Python 3.11，缓存 Docker 镜像没有现成 Python 测试环境。未安装、下载或升级依赖，未创建容器；当前不能在不新增资源授权的边界内进行 CI 等价 Linux 验证。Windows 固定解释器实际为 Python 3.12.9，不能把 Git Bash 视为 Linux Python。

| 本轮实际验证 | 结果 | 证据与限制 |
| --- | --- | --- |
| 情报 fail-open 单独执行 | 已通过：1 passed，exit 0 | 仓库外只读诊断钩子仅记录异常类型及调用位置，不保存原始异常正文，不改断言 |
| 全测试树收集后仅执行 fail-open | 已通过：1 passed / 7268 deselected / 31 warnings，exit 0 | `-m "not network" -k test_fetch_enabled_sources_is_fail_open`；不能当作整个套件通过 |
| 情报 API/Service 组合执行 | 已通过：35 passed / 3 warnings，exit 0 | 没有复现原完整 gate 的执行顺序失败，不能关闭该失败 |
| Requests 共享代理字典反例，实施树 | 已复现：1 failed，exit 1 | 完全离线，真实 `Session.merge_environment_settings` 在测试中向共享默认字典追加 `no` 键；两个源的代理隔离断言失败，公开结果 saved_count=0 |
| 同一反例，main 源码归档 | 已复现：1 failed，exit 1 | Git archive 的 Service/测试源码与 HEAD、实施树在换行规范化后相同；相同失败机制不依赖 WP-0207 代码增量 |
| main 归档未注入代理状态的控制用例 | 已通过：1 passed，exit 0 | 同一解释器、源码及诊断钩子；与注入状态的反例构成控制对照，不替代原全量执行顺序复验 |
| Linux CI 等价环境 | 未运行 / 环境不满足 | 现有 WSL 缺 Python 3.11 与测试依赖；需要提供就绪环境或明确授权临时环境及依赖获取 |

反例没有执行 HTTP 请求，只用真实 Requests 的环境合并函数和测试内虚构代理配置；没有来源凭据、响应、生产资源或真实数据访问。现有 Service 将共享 `_DISABLE_REQUEST_PROXIES` 字典直接交给 Requests，后者可能原地追加代理环境键，随后 fail-open 测试的严格代理断言失败。诊断捕获到了 AssertionError 调用链；原完整 gate 仅保留了脱敏后的上游失败，因此这个反例证明一种可复现的既有状态污染机制，尚不能证明它就是此前完整 gate 的实际根因。未把两个预期失败反例计入验收通过数量，也没有借本轮授权修改 Legacy Service。

首次 main 归档验证因 CRLF/LF 原始字节不同失败（exit 1），记录保留。后续新检查复验归档条目字节和源码绑定通过（exit 0），相关 Service/测试内容只存在换行差异；未覆盖或重建归档。归档 CLAUDE.md 的 symlink 表示为普通文本，未用该归档宣称 symlink、Linux 或全量治理验收通过。此前真实 PostgreSQL/files 的 73 passed / 0 skipped 和 223 对象/223 文件证据仍为前轮记录，本轮没有重新创建数据库或重跑它们。

本轮证据位于独立仓库外目录 `C:\Users\lzq11\.codex\task-evidence\WP-0207-CI-ATTRIBUTION-20261014-01a134a9`：`environment-readiness.json`、`main-source-binding.json`、各 probe/result/log、`commands-results.md`、四文档增量清单与交付 Hash。旧封存文件保持不变；旧 manifest 表示上次交付字节，不用于声称本轮四文档仍匹配旧 Hash。

继续完整 Goal 的条件没有被缩小：需版本化真实来源契约及授权脱敏样本/只读范围、七阶段实际对象链、规定历史区间与逐证券/逐交易日缺口、两真实成功源质量、完整 gate/Web lint、远程 CI/合入和生产授权/认证。路线图要求 Security Master 至少 2018 起完整历史、交易日历 2017 起至当前年份后一年、日 K/状态/公司行动及行业 2018 起、财务 2017 年报期起，估值采用 2018 或可证明有效起点，非核心数据不得伪造历史。参考代码路由不替代这些来源证明。本轮环境及更强失败证据是验收推进，不是完整回填或认证。

BLOCKER：现有环境无法执行 CI 等价 Linux 验证，原完整 gate 和全量 Web lint 仍失败，真实来源/完整历史等验收仍缺证据。FOLLOW-UP：跨模块共享代理状态、进程组、文件句柄、编码、调度与 lint 根因修复需要对应范围授权；不关闭情报全量失败，不增加超时、跳过测试或关闭规则来变绿。仅撤回本轮四文档时，先核对当前 Hash 与本轮 `changed-files.json` 一致，再恢复本轮 baseline 的对应原始字节；不得撤回原有 34 文件实现、主 checkout 或 f468，回滚未执行。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，未执行 commit/tag/push/PR/merge/部署。

## 2026-10-14 11:03 收尾：最终账本、保护确认与验收封存

用户明确确认 f468 新增四份文档及测试临时目录均属于并行 WP-0303，授权更新只读保护快照并继续本轮收尾。11:01:42 将当前 f468 的 52 个 dirty/untracked 文件、HEAD/status/diff 和原始字节另存仓库外 `seal-round-baseline-20261014T030141Z/confirmed-f468/`；四个变化为 CHANGELOG、IMPLEMENTATION-STATUS、WP-0303-B3-SOURCE-EVIDENCE-PREP 和 WP-0303-IMPLEMENTATION。旧快照保留，不按旧 Hash 恢复。主 checkout 三个既有文档仍由开工快照保护；本次未写入这两个目录，也未清理、覆盖或回滚 WP-0303 的代码、文档、临时目录或容器。此前保护确认阻塞已获用户授权处理，不把并行改动归入 WP-0207 增量。

本次封存只补录四份 WP-0207 文档，编辑前核验整体 34 文件全部等于上一交付 Hash，并保存本次四文档原始字节、patch、HEAD/status 及上一版账本。补源/隔离实现回合相对 `fallback-round-baseline/` 仍为 14 文件、无新增仓库路径；整体 Goal 为 27 tracked 修改、7 新增。完整绝对路径、修改原因、原始/交付 SHA256 见仓库外 `changed-files.md/json`，14 文件回合清单见 `fallback-changed-files.md/json`，本次四文档清单见 `seal-changed-files.md/json`。实际 argv、工作目录、退出码、测试数量及失败日志见 `commands-results.md`，保护与交付复验见 `preservation-final.json`、`fallback-delivery-validation.json`；封存清单及 Hash 由 `seal-manifest.json` 给出。

11:03:16 的 HTTP/1.1 `git fetch --all --prune` 和 11:03:29 的 `git ls-remote origin refs/heads/main` 均 exit 0。独立实施 branch 为 `codex/wp-0207-end-to-end-closeout`，HEAD、origin/main 与实时 main 同为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，差异为上述 34 个未提交文件。本轮没有 commit/tag/push/PR/merge/部署；本增量没有远程 CI 或合入证据。

| 本轮验收项 | 状态 | 实际结果与边界 |
| --- | --- | --- |
| Backfill 单元、API/Contract、Golden、Snapshot 定向 | 已通过 | 507 passed / 8 warnings，exit 0；另跑 Golden 121 passed，exit 0；不累计重叠测试为独立总数 |
| 临时独立 PostgreSQL 与实际 files 对象链 | 已通过 | Backfill 65 + Canonical 8 = 73 passed / 0 skipped，exit 0；新增 13 个补源拒绝/quarantine 组合场景另跑 13 passed / 52 deselected |
| 固定引用及实际对象归档 | 已通过 | 13 场景、223 个数据库对象、223 个文件；归档复验 13 passed，exit 0；来源 `SYNTHETIC_TRANSPORT_ONLY` |
| 公开 checkpoint、按月缺口、已有 Task 恢复动作与脱敏 | 已通过（本地定向范围） | 包含输入/连续分区/固定引用校验、拒绝恢复及公开错误反例；真实浏览器手工验收未运行 |
| Web 定向及受影响工具链 | 已通过 | 5 files / 54 passed；受影响 lint、tsc、build exit 0；没有新增依赖 |
| Python/契约/AI 资产 | 已通过 | 15 个 py_compile、生成器 `--check`、AI 资产检查 exit 0 |
| 完整 `bash scripts/ci_gate.sh all` | 失败 | 81 failed / 7174 passed / 10 skipped / 4 deselected / 69 warnings，另有 572 subtests passed；10:22:51 结束，exit 1 |
| 全量 Web lint | 失败 | 41 errors，exit 1；不能以受影响文件通过替代全量结果 |
| 真实来源版本、字段契约、授权及真实 available_at | 无法验证 | 缺固定接口/字段/时间/修订/分页/PIT 证据和授权脱敏样本或明确只读范围；fixture 时钟 2026-12-31 不是真实来源证据 |
| 七阶段真实执行、2018 至今核心区间及其他规定起点 | 未运行 / 无法验证 | 不把七个 Task、月末样本、执行区间或 `PUBLISHED_UNCERTIFIED` 等同全证券逐交易日覆盖；按月缺口可查询，`coverage_state=UNPROVEN` |
| 两个成功真实来源的关键字段比较、冲突与全量质量 | 未运行 / 无法验证 | 补源失败/拒绝组合已有本地证据，两真实成功源的质量验收仍缺证据 |
| 实时远程 main 获取与核验 | 已通过 | 11:03:16 fetch、11:03:29 ls-remote 成功；不替代本增量远程 CI |
| 本增量远程 CI/合入、生产资源与认证 | 未运行 | 未获 Git 发布及生产资源授权；保持 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false` |

完整 gate 的 81 个失败中，78 个与未修改 main 的既有归档失败复验重合，相对上一 quality 回合没有新增失败节点。未在初次 main 全量基线复现的三项分别是情报 fail-open、Provider cache 捕获超时和 Runtime scheduler 超时；后两项已在上一回合 main 归档定向复现。情报 fail-open 独立运行通过，但全量失败原因仍未解释。失败测试文件均等于 HEAD 字节只证明测试文件未改，不能证明全部因果无关。比较、失败节点和原始日志见 `fallback-ci-baseline-comparison.json`、`fallback-ci-all.result.json/log`；全量 gate 继续是验收 BLOCKER，不在本轮修复无关模块。

临时资源清理已有实际记录：10:10:35 对 13 个归属明确、路径及文件 Hash 匹配的 runtime 目录逐一移除，223 个证据文件保留；10:23:40 移除本轮 `visory-wp0207-fallback-01a134a9` 容器（ID `b0088b7a656b701d5ad363dd7d05897d22c8513eab853400e4ea836e47d0447f`，loopback 45497、tmpfs）和测试密码文件，无其他活动客户端。清理前后其他 5 个容器不变；相对开工的 4 个容器，期间新增了并行 WP-0303 容器，因此 `other_containers_unchanged_since_start=false` 如实保留，不能改写为 true。本次封存只读 inventory 已无该并行容器，原 4 个容器仍在；未由本轮执行其清理或恢复，没有删除镜像/volume，没有生产数据或真实 `/data` 操作。详见 `fallback-cleanup-result.json`、`fallback-storage-cleanup.json`、`seal-authorization.json`。

本 Goal BLOCKER：版本化真实来源及授权材料、七阶段完整真实对象链、规定区间的证券逐日覆盖、两真实成功源的冲突质量验收、未通过的全量 gate/Web lint，以及本增量远程阻断 CI/合入。完整 WP/生产认证 BLOCKER：上述验收之外，还需明确生产数据库、真实 `/data`、调度、资源和在线历史回填授权，以及实际全历史、生产恢复/并发及部署认证证据。参考项目价值和具体代码路由已写入本实施树根 AGENTS.md 2.2 节，它不提供真实来源授权或认证。

FOLLOW-UP：跨范围 Legacy Windows、情报 fail-open、Provider cache、Runtime scheduler 与全量 Web lint 的根因由对应模块处理；授权后补真实浏览器手工验收和生产性能/资源验证。剩余风险包括合成 transport 不代表真实 Provider，月级执行清单不能证明逐证券/逐交易日完整性，旧补源 checkpoint 缺失败主源固定证据时会被完整恢复复验拒绝。历史 G020、其他 WP 状态和计数均未提升；本地收尾封存不构成完整 Goal 完成。

仅撤回本次四文档补录：先核对当前 Hash 等于 `seal-changed-files.json` 的交付 Hash，再恢复 `seal-round-baseline-20261014T030141Z/original-bytes/` 的对应字节。仅撤回补源/隔离实现回合：按 `fallback-changed-files.json` 核验当前交付 Hash，再恢复 14 个路径的 `fallback_original_backup_path`；不删除前期 7 个新增文件。整体 Goal 的撤回仍按 `changed-files.json` 的逐文件原始字节及新增路径 Hash 守卫处理。目标必须限制在独立实施树，遇到后续编辑停止，不使用 reset/clean/stash，不碰主 checkout 或 f468；回滚没有执行。中文专题文档没有对应英文副本，未扩大更新 README/README_EN。

## 2026-10-14 续做：补源拒绝血缘与 Raw quarantine 恢复

本回合继续使用独立 `codex/wp-0207-end-to-end-closeout` 工作树。09:51:55 编辑前核验整体 34 个 Goal 文件与上次交付 Hash 一致，主 checkout 的三个 dirty 文档和 f468 最近确认的 52 个保护文件也未变化；另存 `fallback-round-baseline/` 的当前清单、diff、原始字节及先前交付记录。09:52:09 fetch、09:54:15 实时 main 核验均成功，HEAD/origin-main/远程 main 为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。没有向两个保护目录写入，也没有覆盖历史快照。

真实 PostgreSQL 反例复现：主源超时、补源进入 Canonical 后被拒绝时，父任务虽已失败，却公开 `provider_fallback=false`，拒绝回执没有失败主源 Hash。现在 `BackfillRejectionEvidence` 和 `BackfillQuarantineEvidence` 都追加可选 `failed_provider_run_hashes`；父 checkpoint 记录全部 ProviderRun 引用和 `PROVIDER_FALLBACK_EXPLICIT`，聚合失败时保留此前成功月份的 fallback 状态。缺口/已有 Task 恢复动作沿用现有 API，终态拒绝仍要求 `REVIEW_FAILURE`，不调用仅接受 `RETRY_WAIT` 的 retries 入口。

失败主源证据从现有 PostgreSQL Task、Attempt、ProviderRun 和 Policy 重新复验：父 Batch/Task、分区索引、Raw 子任务幂等键与输入引用、请求 fingerprint、schema/policy 版本、主补源身份、授权触发条件、无业务 Raw 的失败结果和已取消的主源 Task 都必须一致。恢复不依赖 executor 内存中的来源列表。空失效 Hash、当前补源冒充失败主源、跨输入绑定以及遗漏 fallback 事件均拒绝验收；新字段使用默认空映射，旧主源回执仍可读取，旧补源回执若缺固定失败证据不能通过完整恢复复验。

Raw quarantine 在父 checkpoint 前崩溃后，通过专门的拒绝恢复路径读取已有隔离对象，复验 Raw Task/Attempt 终态、ProviderRun、数据库隔离记录、payload 和 Manifest。它不能复用为成功 Raw，不提交 Canonical/Snapshot、不重新 fetch。直接与新进程恢复均保持 `QUARANTINED`、完整失败范围及稳定不可重试 code。业务发布的既有成功复用规则仍要求子 Task 为 `SUCCEEDED`。

本回合新增 25 个回归：12 个 checkpoint/契约反例，9 个补源 Canonical/Snapshot 拒绝及跨月前缀用例，4 个主源/补源 Raw quarantine 直接或跨进程恢复用例。定向套件 507 passed；真实 PostgreSQL/files Backfill 与 Canonical 套件 73 passed / 0 skipped。13 个新增组合场景的 223 个固定数据库对象和 223 个实际文件已导出至仓库外 `fallback-object-evidence/`，复验 13 passed；证据明确标记 `SYNTHETIC_TRANSPORT_ONLY`。10:10:35 核对归属、路径和文件 Hash 后移除这 13 个临时 runtime 目录，归档保留。首次新增夹具回调签名、诊断断言和仓库外验证器字段名错误均已修正，失败日志保留；它们不作为成功证据。

Web 5 个文件/54 passed，受影响 lint、tsc、build、15 个 Python py_compile、生成契约检查及 AI 资产检查通过。全量 Web lint 仍为 41 errors，exit 1。完整 gate 为 81 failed / 7174 passed / 10 skipped / 4 deselected、572 subtests passed，exit 1；临时 PostgreSQL/密码和对应 runtime 已清理，最终清单、命令账本及交付 Hash 见顶部 11:03 封存节。实际对象证据不证明七阶段真实来源或全历史证券覆盖；完整 WP 和生产状态保持 `IN_PROGRESS / NOT CERTIFIED / RELEASED=false`。

## 2026-10-14 续做：子任务拒绝发布与固定失败证据

本回合继续在 `codex/wp-0207-end-to-end-closeout` 独立 worktree 实施。编辑前，33 个既有 Goal 增量文件全部匹配 2026-10-13 交付 Hash；主 checkout 三个文档、f468 最近确认快照中的 52 个 dirty/untracked 文件也匹配原始字节。另存 `quality-round-baseline/` 的文件清单、diff、原始字节、HEAD/status 和此前交付清单/账本；新增修改的 Canonical worker 在编辑前保存 HEAD 原始字节。保护目录没有写入。本回合没有推进 WP-0303，也没有新增 Queue、Publisher、Repository 或 Migration。

此前 Canonical worker 已将质量拒绝记录为不可重试失败，Snapshot worker 也持久化 gate 拒绝；父 Backfill 却将它们统一转成 `BACKFILL_*_NOT_PUBLISHED`、retryable。现在真实对象链直接保留子 Task 的稳定 code 和终态失败语义。输入边界质量报告补齐 Task/Attempt、Dataset/Schema、MappingVersion、ProviderRun/RawObject 绑定；子任务失败后的恢复沿用该持久化报告，不重新执行失败子任务。

追加可选 `rejection_evidence`，兼容旧 checkpoint：绑定 Batch/父 Task、分区日期、Dataset、拒绝阶段、子 Task/Attempt 与输入 Hash，固定 ProviderRun Hash、RawObject/逻辑 StorageRef/Manifest Hash、QualityReport ID/Hash；Snapshot 拒绝还固定已发布的 CanonicalPartition、文件和 Manifest Hash。恢复复验现有数据库对象和实际文件，不以返回值、任意 FAILED Task 或来自其他批次的报告授权复用。失败报告目前保存在 PostgreSQL 与带 Hash 的 checkpoint 中；Canonical 拒绝没有业务 Canonical 文件，Snapshot 拒绝没有业务 Snapshot，均未补造空文件或成功回执。

公开 checkpoint 校验增加拒绝证据的父 Task/Batch、失败范围、ProviderRun 和稳定诊断 code 绑定，拒绝重复子任务证据、错误阶段和 dry-run/plan-only 的业务发布拒绝声明。Backfill/P-DATA、嵌套 StageChain 和生成契约公开同一固定证据。跨月执行时保留首月实际完成范围、Snapshot 回执与文件，第二个月拒绝单独进入 failed_ranges；覆盖仍为 `UNPROVEN`。终态失败的恢复动作保持 `REVIEW_FAILURE`，不能调用只接受 `RETRY_WAIT` 的既有 retries API。原因修正后的新批次/Correction 仍遵循既有控制面，不修改旧对象。

本回合新增 23 个回归用例：14 个 checkpoint/契约反例和 9 个 PostgreSQL 链路用例。真实独立 PostgreSQL/files 覆盖重复键质量拒绝、缺失 Mapping 和 Snapshot PIT gate 拒绝；三种拒绝均验证直接失败、子任务失败后父 checkpoint 尚未写入时的新 Python 进程恢复、以及两个月批次中成功前缀不变。合成 transport 只提供测试输入；未开展两来源成功后的关键字段比较，也未声称真实来源冲突质量已验证。

| 本回合检查 | 结果 | 证据与限制 |
| --- | --- | --- |
| Backfill/Canonical 单元、API/Contract、Golden、Snapshot 定向 | 495 passed，0 skipped，8 warnings，exit 0 | `quality-scoped-final`；首次扩大验证 492 passed / 1 failed，遗漏新 OpenAPI component 的白名单断言已修正，历史失败保留 |
| Backfill 与 Canonical 真实 PostgreSQL/files | 60 passed，0 skipped，exit 0 | `quality-postgres-final`；其中 Backfill 52、Canonical 8；包含新增 9 个拒绝/恢复/前缀用例 |
| 更新后的 Golden | 121 passed，exit 0 | `quality-golden-final`；覆盖拒绝证据和 `REVIEW_FAILURE`，历史 gap_ranges 未减少 |
| Web 定向/受影响 lint/tsc/Vite build | 5 files / 54 passed；各检查 exit 0 | `quality-web-*`；只追加生成类型，页面布局未改，未创建 PR |
| 全量 Web lint | 41 errors，exit 1 | `quality-web-lint-all`；不扩展到其他页面治理 |
| Python 编译、生成契约、AI 资产 | 15 个 py_compile、`--check`、AI 资产均 exit 0 | 使用明确的 Python/Node，不安装、升级依赖 |
| 治理与 diff | 614 links / 0 broken / 0 imported secrets；exit 0 | `quality-governance`、`quality-diff-check` |
| `bash scripts/ci_gate.sh all` | 82 failed / 7148 passed / 10 skipped / 4 deselected，exit 1；572 subtests passed | `quality-ci-all`；2026-10-14 09:32:54 结束，完整 gate 未通过 |

完整 gate 的 82 个失败中，79 个与此前未修改 main 的失败复验重合。相对 10-13 新出现 Provider cache 本地捕获超时和 Runtime scheduler 超时两个失败；同一解释器下补跑当前这三个待解释节点为 1 failed / 2 passed，未修改 main 归档为 2 failed / 1 passed。两个新节点均在 main 归档复现；情报 fail-open 在两份代码独立运行均通过，完整 gate 的失败原因仍未解释。失败测试文件均与 HEAD 字节一致，不能据此声称全 gate 成功或全部根因已关闭；比较与原始日志保存在 `quality-ci-baseline-comparison.json` 和 `quality-extra-failures-*.result.json`，无关失败未借机扩展本轮修改。

本回合远程 fetch 于 2026-10-14 09:01:53 连接被重置（exit 128）；09:02:32 的 ls-remote 连接失败（exit 128）。有总时限的独立 runner 保留实际退出码。HTTP/1.1 收尾核验于 09:34:12 返回远程 main `efe8e9b362cba13eca183c55be57bbbbc832b60b`（exit 0），09:34:30 的 fetch --all --prune 也成功（exit 0），与实施 HEAD/origin/main 一致。此前传输失败作为历史保留，本回合远程基线获取/核验已通过；没有 rebase/reset 或改变保护工作树。

另用仓库外只读 pytest 导出器补跑新增 9 个场景（9 passed，0 skipped，exit 0），在 fixture 数据库清理前导出 129 个真实数据库对象记录、固定投影和 135 个实际文件；记录/文件 Hash 复验通过。证据位于 `quality-object-evidence/` 和 `quality-object-evidence-summary.json`，机器标记 `SYNTHETIC_TRANSPORT_ONLY`，不证明真实 Provider 来源或完整历史。原始 495/60 用例结果未由导出器替代。

2026-10-14 09:36:17 临时 PostgreSQL 清理 exit 0：容器 `visory-wp0207-quality-01a134a9`（ID `01d6f195591c9cfc0498e59c074f373067e2e567e0e8c264655c951ae2b6fd90`、loopback 45377、tmpfs）及密码文件均已移除；无其他活动客户端、无残留 fixture 数据库，另 4 个容器从本回合启动至清理的 ID/名称/状态不变，未删除镜像或 volume。09:37:43 对导出器明确归属的 9 个临时 runtime 目录逐一核验路径、清单和 Hash 后清理（exit 0），135 个证据文件继续保存在仓库外，不删除整个 pytest 目录或他人临时文件。分别见 `quality-cleanup-result.json`、`quality-storage-cleanup.json`；其他测试缓存由 pytest 管理，本回合没有清扫共享缓存。

本回合相对编辑前快照修改 21 个文件，没有新增仓库路径；整个 Goal 当前为 34 个文件（27 tracked 修改、7 新增），新增的 tracked 修改只有 Canonical worker。完整绝对路径/原因和原始/交付 Hash 见 `quality-changed-files.md/json`、`changed-files.md/json`；本回合 patch 为 `quality-delivery.patch`，原 10-13 清单/账本另存 `quality-round-baseline/previous-delivery/`。未新增代码依赖；本轮中文验收/状态文件没有对应英文副本，不扩展到英文 README。

本 Goal BLOCKER 仍包括版本化真实来源/授权材料、实际七阶段与完整历史覆盖、两源实际质量冲突验收，以及全 gate 和本增量的远程 CI/合入证据；完整 WP/生产认证还需要明确资源授权后完成真实数据库、真实 `/data`、生产调度、全历史回填及部署认证。参考项目路由已经写入本 worktree 根 AGENTS.md 2.2 节；参考代码继续是只读材料，不授予在线取数或凭据访问。与本轮无关的 Legacy Windows、情报 fail-open、Provider cache/Runtime scheduler 和前端 lint 问题记录为 FOLLOW-UP，不借此推进相邻 WP。补源后再遭遇 Canonical/Snapshot 拒绝的组合场景未在本回合新增 9 用例中验证，完整来源/质量验收继续阻塞。

本回合只撤回增量时，先核对 `quality-changed-files.json` 的交付 Hash，再按 `quality_original_backup_path` 恢复 `quality-round-baseline/original-bytes/`；不删除此前 7 个新文件。整体 Goal 撤回仍按 `changed-files.json` 中原始字节恢复 tracked 文件，仅对交付 Hash 未变化的 Goal 新增路径执行逐文件移除。两种方案都不操作主 checkout 或 f468，不 reset/clean/stash，不覆盖后续编辑；回滚未执行。实际绝对路径/原因、argv/cwd/退出码、清理证据与当前封存校验保存在同一仓库外证据目录。

## 2026-10-13 续做：checkpoint 公开校验和按月恢复动作

用户再次确认 f468 新增内容属于并行 WP-0303。本回合在原独立 WP-0207 worktree 实施；f468 当前全部 dirty/untracked 字节、HEAD/status/diff 另存仓库外 `resume-round-baseline/confirmed-f468/`，原确认快照继续保留。实施 worktree 的 33 个增量文件在编辑前全部匹配上次交付 Hash，并保存本回合原始字节；主 checkout 三个既有文档仍匹配开工快照。本回合没有向 f468 或主 checkout 写入。

公开 checkpoint 投影和 worker 恢复共用 `_validate_checkpoint_payload`：核验 Task/Batch、stage/dataset、起止日期、handler 和 input Hash、连续分区前缀、失败/跳过区间、资源计数及固定发布引用。公开读取还绑定数据库 checkpoint 的 task/input Hash/handler；存在 checkpoint 但缺 resolver 时返回 `BACKFILL_CHECKPOINT_UNAVAILABLE`（503、retryable），不默默丢弃进度。文件 Hash 正确但内容绑定错误时返回 `BACKFILL_CHECKPOINT_INVALID`（409），Backfill/P-DATA envelope 不暴露路径。dry-run/plan-only checkpoint 不得宣称业务 `completed_range`。公开审计不要求旧 checkpoint 未过期；实际恢复继续走现有 resume token、有效期及数据库/对象文件复验。

`GET /api/platform/v1/backfills/coverage` 在兼容既有字段的基础上追加 `execution_ranges`，按日历月和请求边缘列出精确的执行日期范围，绑定已有 task/batch/policy、底层 TaskState、记录的 Snapshot 引用和稳定诊断 code。没有已有 Task 的范围按月拆分；同月中已有部分日期批次时，保留左右未安排日期，不误算整月已完成。重复 Task 页、循环 cursor 或截断分页 fail closed；查询范围外的 checkpoint 不参与读取。不同 Task/Correction 的重叠记录分别保留，不挑任意一个覆盖另一个。

| next_action | 既有路径与条件 |
| --- | --- |
| `CREATE_MONTH_BATCH` | 按给出的 date_from/date_to 通过既有 `POST /api/platform/v1/backfills` 创建 MONTH 批次；先取得版本化来源授权证据，明确 provider_policy_id、stage、同范围阶段依赖、新 batch_id/requested_by 和 Idempotency-Key，不复用旧幂等键改写输入 |
| `WAIT_EXISTING_TASK` | 读取给出的 task_id，沿现有 worker/lease/checkpoint 继续，不另建重复任务 |
| `RETRY_EXISTING_TASK` | 只对当前 `RETRY_WAIT` Task 调用既有 `POST /api/platform/v1/tasks/{task_id}/retries`，正文 `{"reason_code":"TASK_RETRY_REQUESTED"}`；实际动作仍由控制面事务复核状态、worker 校验恢复输入和发布 fence |
| `RESOLVE_DEPENDENCY` | 核验已有前置阶段的状态、输入与质量；沿现有依赖解除阻断流程继续 |
| `REVIEW_SKIPPED_RANGE` | 依据稳定 code 核验 Unavailable/quarantine/跳过原因；修正来源契约或隔离问题后按已授权范围新建批次，不能把跳过分区直接算作成功 |
| `REVIEW_FAILURE` / `REVIEW_CANCELLED` | 终态失败或取消不显示可直接重试；审查原因和固定对象后决定新批次/Correction，保留旧对象与引用 |
| `VERIFY_COVERAGE` / `REVIEW_INCOMPLETE_PUBLICATION` | 固定发布回执只能标为 `PUBLISHED_UNCERTIFIED`；缺完整回执的旧成功、dry-run 或声明 completed_range 不能证明发布，更不能关闭历史覆盖缺口 |

查询是只读执行/恢复计划，不自动创建或重试 Task，不构成在线来源、生产调度或生产资源授权。`coverage_state=UNPROVEN` 与完整未证明 `gap_ranges` 继续保留；新字段说明执行缺口，尚不能计算证券逐交易日缺口，也不从月末单行样本推断完整 universe。2018-01-01 至 2026-10-13 无任务时返回 106 个按月未安排区间；当前查询已有 Task 时给出实际引用与动作，不把这 106 个计划范围称作已执行历史回填。

本回合验证：单元/API/Contract/Golden/Snapshot 定向 `457 passed / exit 0`，包含新增 29 个反例/边界验收；真实独立 PostgreSQL/files Backfill `43 passed / 0 skipped / exit 0`，增强月/年发布、COMMIT/文件故障的已有 Task 恢复动作、不可用范围和旧固定引用校验。Web 定向 `5 files / 54 passed`，受影响 ESLint、tsc、Vite build 及 14 个 Python 文件 py_compile、生成契约 `--check` 均 exit 0。治理检查 `612 links / 0 broken / 0 imported secrets`，AI 资产检查、diff 检查 exit 0。全量 Web lint 重跑仍为 `41 errors / exit 1`。

本回合实际 `bash scripts/ci_gate.sh all` 于 2026-10-13 23:17:02 Asia/Shanghai 结束：`80 failed / 7127 passed / 10 skipped / 4 deselected`，另有 `572 subtests passed`，exit 1。与未修改 main 的既有失败复验有 79 个重合；`test_fetch_enabled_sources_is_fail_open` 仍未由基线全量结果解释，保留此前当前/基线独立各 `1 passed` 证据，不推断根因。相对初次最终全 gate，`test_output_stat_error_is_structured_and_kills_process_group` 再次失败（已在基线失败复验出现），`test_provider_turns_do_not_appear_in_visible_or_web_messages_and_delete_with_session` 本次通过。失败测试文件均未被本 Goal 修改且与 HEAD 字节一致，但不能据此声称全 gate 通过或因果已全部解释；具体比较保存于仓库外 `resume-ci-baseline-comparison.json`。

本回合临时容器 `visory-wp0207-resume-01a134a9`（ID `9829ef1291634fe31893b72b5abcfe2e5d9941f45e76d197e94f1644e6e7dfc5`）使用已有 `postgres:16-alpine`、loopback 随机端口 46073、tmpfs 和单独密码文件，没有安装或下载依赖。2026-10-13 23:18:10 清理 exit 0：无其他活动客户端，测试数据库均由 fixture 清理，仅保留系统/default 测试库；随后移除该容器和密码，另 4 个容器从启动至清理的 ID/名称/状态一致，未删除镜像或 volume。新测试日志中临时密码扫描通过。证据为 `resume-postgres-settings.json`、`resume-postgres-cleanup.result.json`、`resume-cleanup-result.json`；设置文件仅保留审计参数，密码文件已经不存在。

本回合相对编辑前快照修改 17 个既有增量文件，整体 Goal 仍为 33 文件（26 tracked 修改、7 新增）；清单/原因/原始与交付 Hash 见 `resume-changed-files.md/json` 和 `changed-files.md/json`，本回合 patch 见 `resume-delivery.patch`，实际 argv/cwd/退出码/测试数量见 `commands-results.md`。checkpoint、按月计划和已有 Task 恢复动作的本地验收已闭合，原完整 Goal 仍受来源授权/真实七阶段、证券逐日完整覆盖、双源质量、全 gate、远程和生产证据阻塞，继续 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`。

仅撤回本回合：先核对当前 17 文件的 Hash 等于 `resume-changed-files.json` 的交付 Hash，再按各 `resume_original_backup_path` 恢复 `resume-round-baseline/original-bytes/` 中的编辑前字节。本回合没有新增仓库路径，不删除原 Goal 的 7 个新文件；原 33 文件整体撤回方案仍见本文末。两种方案均不写主 checkout 或 f468，不 reset/clean/stash，不覆盖后续编辑。未执行回滚。

本回合 23:09 fetch 遇到 GitHub 443 连接失败（exit 128），紧接着 `git ls-remote` 于 2026-10-13 23:09:44 Asia/Shanghai 返回 `efe8e9b362cba13eca183c55be57bbbbc832b60b`（exit 0），与本地 HEAD/origin/main 一致。失败与成功记录分别保留，不把失败 fetch 写成通过；不 rebase/reset/stash，也不执行 commit/tag/push/PR/merge/部署。

最终远程核验仍有传输阻塞：23:22:39 的 `ls-remote` 低速超时（exit 128）；23:23:24 的 HTTP/1.1 重试超过两分钟没有返回，23:26:13 只结束本回合该只读 Git 操作的两个网络 helper，Git 实际退出码为 `4294967295`。未结束无关进程、未修改 Git refs 或工作树，处置证据为 `resume-remote-timeout-cleanup.json`。最近成功的实时远程 SHA 仍是 23:09:44 的 `efe8e9b...`；交付时不能确认实时 main，当前本地 HEAD/origin/main 同值只能作为缓存基线。远程收尾核验列为 BLOCKER，不把历史成功、缓存 refs 或定向测试当作当前远程通过。

本轮补齐了现有 Backfill 控制面与 PostgreSQL、实际 Raw/Canonical/Snapshot 文件之间的固定证据回执、恢复校验、受控补源、隔离拒绝证据和公开脱敏。真实对象链测试使用合成 fixture transport；它证明数据库、文件和恢复机制可以工作，不能证明真实来源、全证券历史覆盖或七阶段完整回填。历史 `G020=COMPLETE` 仅保留为历史 Goal 结论。

## 基线和范围

- 实施目录：`C:\Users\lzq11\.codex\worktrees\wp-0207-end-to-end-closeout\Visory`。
- 分支：`codex/wp-0207-end-to-end-closeout`；开工 HEAD 与实时远程 `main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。先执行 `git fetch --all --prune` 和 `git ls-remote origin refs/heads/main`，再创建隔离 worktree/分支。
- 主 checkout `E:\Personal Manager\Visory` 保留 `528baa072d32f0242cfdcfa8bb7b1314de19db78`，相对开工远程 `0 ahead / 9 behind`；三个既有文档修改不属于本次增量。f468 的 WP-0303 dirty/untracked 成果不属于本轮。
- 用户于 2026-10-13 明确确认 f468 的变化属于并行 WP-0303，要求保留当前全部内容并继续本轮收尾。原开工快照不改写；确认时另存 51 个 dirty/untracked 文件的只读快照。本轮不向 f468 写入，也不以开工 Hash 回滚并行变化；主 checkout 的三个既有文档继续按开工原始字节核验。
- 用户后续指定 `E:\Personal Manager\参考项目` 为只读代码参考，并授权在根 AGENTS.md 写入价值说明和具体源码路由。初次收尾的 32 文件及证据另存不覆盖；增加 AGENTS.md 后最终为 33 文件。补充编辑前的五份文档字节、授权和 AGENTS.md 原始字节保存在仓库外 `reference-routing-baseline/`。
- 本次仅编辑 WP-0207 所需后端、公开 API/投影、浏览器错误格式化、生成契约、测试和文档；复用已有 Durable Task、Publisher、Repository。未修改 Migration、manifest/lockfile、生产配置或相邻 WP 状态。
- 开工清单、binary diff、拟修改文件原始字节和本次命令证据位于仓库外：`C:\Users\lzq11\.codex\task-evidence\WP-0207-END-TO-END-CLOSEOUT-20261013-01a134a9`。完整绝对路径/原因见其中 `changed-files.md`；逐条 argv、cwd、exit code、测试摘要见 `commands-results.md` 和各 `*.result.json`。

## 已完成的本地闭环

1. 真实 typed worker 生成 `BackfillPublicationEvidence`，固定 ProviderRun、RawObject、CanonicalPartition、QualityReport、DataSnapshot ID，输入 schema/policy/mapping 版本，逻辑 StorageRef、Manifest/file Hash 和失败主源 Hash。恢复前重新读取 PostgreSQL 对象并校验实际文件；文件损坏拒绝恢复。`PUBLISHED_UNCERTIFIED` 不等于全历史覆盖。
2. YEAR checkpoint 校验按连续月分区前缀处理；每份发布回执绑定实际月份，不能将每个月误记为整年。成功子任务、父 checkpoint 尚未写入时的崩溃，使用新 Python 进程从 PostgreSQL/files 复用固定对象，禁止重新 fetch。
3. 主源只有持久化 `RAW_TIMEOUT` / `RAW_PROVIDER_UNAVAILABLE` 且 Policy 明确允许 `PRIMARY_UNAVAILABLE` 和指定补源时才进入同一控制面的补充 Raw→Canonical→Snapshot 链。拒绝未授权补源，保留失败主源 Hash，结果公开为 `PARTIAL`。schema quarantine 不触发补源。
4. Raw quarantine 持久化 ProviderRun、隔离对象 ID、证据文件/Manifest Hash 和拒绝范围；公开 `QUARANTINED`，不生成业务 Raw/Canonical/Snapshot。发布链失败 checkpoint 保留既有进度与当前失败范围。Snapshot 的 I/O / 数据库失败进入现有 retry 控制面。
5. 缺 Dataset/Policy 契约时标记 `UNAVAILABLE_DATASET_CONTRACT`，不调用 transport、不创建业务子任务、不发布空成功。覆盖缺口查询为 `GET /api/platform/v1/backfills/coverage?dataset=bar_1d_raw&date_from=2018-01-01&date_to=2026-10-13`；扫描全部 Task 页，坏 cursor / 循环 fail closed。
6. Backfill、任务详情、P-DATA、Operations 使用的 task API、SSE、公开错误 envelope 和三处浏览器错误格式化统一脱敏。反例包括 token、lease、DSN、响应正文、Windows/Unix 路径和异常堆栈；保留稳定 code、retryable 和有效 request ID。平台未知异常的现有日志关联路径也由 API 套件验证。

覆盖查询当前返回 `coverage_state=UNPROVEN`，将整个请求区间列为尚未证明的 `gap_ranges`，同时列出授权来源证据、完整 universe/区间质量验证、重试缺失月份的前置条件。它是保守的未认证缺口投影，尚未实现证券逐日覆盖计算或可执行的生产重试调度；即使文件发布成功，也不从合成样本或月末单行扣减缺口。

## 七阶段与来源证据

阶段顺序继续沿用现有线性依赖，未以“七个 Task 已创建”替代执行验收。

| 阶段 | 路线图区间 | 本轮证据 | 完整验收 |
| --- | --- | --- | --- |
| Identity/Calendar | 身份/历史名称至少 2018-01-01 至今；日历 2017-01-01 至当前年份后一年 | 真实 PostgreSQL/files 身份和日历前置对象；阶段控制面 fixture 测试 | 无已授权真实来源样本；完整区间无法验证 |
| 行情月分区 | 2018-01-01 至今，包含退市证券 | 合成输入的 MONTH / YEAR 实际对象链、恢复和 Correction | 全证券日线、退市证券及完整历史未执行 |
| 状态/上市退市 | 2018-01-01 至今及可证明完整历史 | `instrument_status_daily` / `listing_status_history` MONTH / YEAR 实际对象链 | 真实历史状态、名称和上市退市来源无法验证 |
| 公司行动 | 2018-01-01 至今 | `corporate_action` MONTH / YEAR 实际对象链 | 真实行动与复权依据、冲突和全量质量规则无法验证 |
| 财务/估值 | 财务 2017 报告期至今；估值 2018 起或可证明有效起点 | `financial_statement` 实际对象链；估值缺契约机器可见 Unavailable | 缺真实披露/PIT、已验证历史估值契约和授权样本 |
| 行业 | 2018-01-01 至今；无法证明的历史 Unavailable | 缺可靠行业 Dataset/Policy 时 Unavailable | 历史成员关系来源与区间无法验证 |
| 非核心观察 | 可靠 Provider 历史或平台上线日起 | 缺可靠契约时 Unavailable | 无授权来源/上线范围；未伪造历史或 available_at |

fixture 中的 Registry schema/policy/mapping `1.0.0` 属于确定性测试输入，不能作为真实 Provider 接口版本或授权证据。真实源必须另行提供接口版本、字段契约、脱敏样本或只读资源范围。

2026-10-13 后续参考源码调查已定位候选契约：`a-stock-data-main/SKILL.md` 中的 `baostock_valuation_history`、`baostock_stock_basic`、`sw_industry_history` / `sw_industry_as_of`，以及 `Financial-API-main/docs/api/` 和 `python/marketdb/providers/rest.py` / `dump.py`。这些材料可继续支撑 Visory 字段映射、Adapter 和反例设计，不能证明线上接口当前版本、授权访问或真实响应。Financial-API 本地契约仅提供近一年交易日历、最新估值快照；历史名称、退市 universe、PIT 披露时间、历史行业和各来源覆盖仍需验证。UZI 的前复权/缺值补零与 Financial-API 下载异常正文也不能直接迁入 Visory。完整问题到源码的路由见根 AGENTS.md 2.2 节；本次没有执行参考脚本、读取凭据、安装依赖或发起真实 Provider 请求。

本次路由核验覆盖 10 个项目、30 个具体入口、4 个命名函数及五份编辑前备份；路径和反例检查、`check_ai_assets.py`、`check_visory_baseline.py` 与 diff 检查 exit 0，当次治理检查为 610 个相对链接、0 broken。指定 Python 可定位 `requests`、`pandas`、`pyarrow`、`baostock`，未据此宣称线上服务可用或接口版本已核验。参考路由补充当时没有新的后端/客户端行为变更，未重复此前全量测试；后续 checkpoint/按月恢复动作的增量与验证见本记录顶部续做节。来源真实样本、完整历史、远程和生产认证结论不变。

## 本地验证

指定 Python：`E:\Personal Manager\Visory\.venv\Scripts\python.exe`（3.12.9）。指定 Node：`C:\Users\lzq11\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`（v24.19.0）。Bash：`C:\Program Files\Git\bin\bash.exe`。`ci-python-env.sh` 在仓库外固定 `python` / `python3` / `flake8`，再运行仓库原始 `bash scripts/ci_gate.sh all`。

临时 PostgreSQL 使用已有 `postgres:16-alpine` 镜像、独立容器、tmpfs、随机密码和 loopback 端口；每个 fixture 创建独立 `visory_test_<uuid>` 数据库及临时文件存储。没有用 SQLite 或 mock SQL 替代对象链验收。COMMIT 故障用真实 PostgreSQL deferred constraint trigger 注入；文件发布故障发生在真实 staging 文件写入之后。

对象链 fixture 使用固定测试时钟 `2026-12-31`，YEAR 用例包含测试日期，不是截至实际日期 `2026-10-13` 的在线历史回填证据；这些时间和合成数据不用于推断真实 Provider 的 `available_at`。

| 项目 | 结果 | 限制 |
| --- | --- | --- |
| Backfill 单元、API/Contract、Golden、Snapshot 单元与 PostgreSQL gate | `428 passed`，exit 0，8 warnings | `scoped-current`；不证明真实来源 |
| Backfill PostgreSQL/files 端到端 | `43 passed`，exit 0，0 skipped | `postgres-final-current`；5 个支持数据集 MONTH/YEAR/新进程恢复；多批次、COMMIT、文件发布故障、受控补源、quarantine、Unavailable、旧对象不变 |
| 父取消 / lease 丢失的事务 fence | PostgreSQL 集成通过 | 当前 Backfill fence 用现有控制面与数据库事务；不等同生产并发压力测试 |
| Web 定向 Vitest | 5 files / `54 passed`，exit 0 | Backfill、三入口 formatter、任务详情、SSE hook |
| 受影响 Web ESLint、类型检查、Vite build | exit 0 | 生成类型与现有客户端兼容；未创建 PR，没有页面布局改动 |
| 全量 Web ESLint | exit 1，41 errors | 错误文件与远程基线字节一致，记录于 `web-lint-baseline.json`；未扩展任务修复既有页面 |
| `bash scripts/ci_gate.sh all` | 最终 `80 failed / 7098 passed / 10 skipped / 4 deselected`，exit 1，另有 572 subtests passed | `ci-all-current`；全 gate 未通过。首次固定解释器运行 `81 failed / 7090 passed` 也保留，不覆盖历史结果 |
| 基线失败复验 | 未修改远程 main 源码归档中 `80 failed / 1 passed`，exit 1 | 针对首次 81 个失败 node；最终失败与基线有 79 个重合，不能声称 80 个最终失败全部已由基线解释 |

受影响 14 个 Python 文件 `py_compile`、生成契约 `--check`、`check_ai_assets.py`、`check_visory_baseline.py` 与 `git diff --check` 均 exit 0；治理检查验证 608 个相对链接，broken links 为 0。逐条命令与退出码在外部账本。历史中间测试失败及解释器漂移结果保留，不覆盖删除。

最终失败中的 `tests/test_intelligence_service.py::IntelligenceServiceTestCase::test_fetch_enabled_sources_is_fail_open` 在基线独立运行未复现；基线失败的 `tests/test_local_cli_backend.py::test_output_stat_error_is_structured_and_kills_process_group` 在最终全 gate 未失败。对照保存在 `ci-baseline-comparison.json`，只表明运行结果差异，不推断根因，也不扩大 WP-0207 修改范围。

2026-10-13 收尾后补充定向对照：同一 Python 3.12.9、同一 node 和 timeout 参数分别在当前实施 worktree 与未修改 main 归档中单独运行上述情报 fail-open 用例，均为 `1 passed / exit 0`（`ci-unexplained-node-current` / `ci-unexplained-node-baseline`）。该用例及情报服务不属于本次增量；结果说明当前单用例也不能复现全量失败，尚不能判断运行顺序、共享状态或环境因素的根因。完整 gate 的 `80 failed` 和其中 `79` 个基线重合结论保持原样，不以这两次通过替代全量验证。未修改情报模块或扩展相邻 WP。

## 2026-10-13 收尾交付

- 当前分支/HEAD 仍为 `codex/wp-0207-end-to-end-closeout@efe8e9b362cba13eca183c55be57bbbbc832b60b`。收尾 `git ls-remote origin refs/heads/main` exit 0，实时远程 main 仍为同一 SHA；没有刷新或改写其他 checkout 的分支。
- 本次交付最终包含 33 个未提交文件增量（26 个修改、7 个新增），初次 32 文件收尾后按用户授权补充根 AGENTS.md 路由。完整绝对路径、修改原因、新增/修改分类和原始/交付 SHA256 见仓库外 `changed-files.md` / `changed-files.json`。`delivery.patch` 与 `delivery-bytes/` 保存本次 tracked diff 和全部增量字节；不会把主 checkout 或 f468 的内容纳入本次回滚。
- `commands-results.md` 记录实际 argv、cwd、exit code、测试数量及日志路径，时间使用 `Asia/Shanghai (+08:00)`。已有日志中的临时数据库密码扫描未发现泄露；失败日志和首次解释器漂移证据保留。
- 已核验本次临时容器 ID、`visory.goal=wp0207-closeout-01a134a9`、loopback 端口和 PostgreSQL tmpfs；确认没有其他活动客户端后移除该容器及其密码文件。清理 exit 0，另 4 个容器的 ID/名称/状态前后不变，未移除镜像或 volume，未触碰生产资源。具体证据见 `cleanup-scope.json` / `cleanup-result.json` / `postgres-cleanup.result.json`。
- 当前人工确认阻塞已解除，本轮文件/命令/文档/临时资源收尾已交付；原完整 Goal 的来源、七阶段、完整历史、全 gate、远程和生产验收条件仍未满足。保持 `WP-0207=IN_PROGRESS / NOT CERTIFIED / RELEASED=false`，不把收尾交付等同完整 Goal 完成。

## 验收矩阵与阻塞

本节保留初次收尾的历史矩阵；当前验收及实时远程结论以顶部 2026-10-14 11:03 封存节为准。

| 要求 | 判定 | 依据 |
| --- | --- | --- |
| 现有控制面复用、固定对象引用与实际文件 Hash | 已通过（本地 fixture 范围） | Durable Task + PostgreSQL + Raw/Canonical/Snapshot 文件复验 |
| 月/年试跑、多批次、恢复、幂等、Correction | 已通过（本地 fixture 范围） | 实际对象链测试，旧文件和引用保持不变 |
| 真实来源接口版本、字段契约和已授权访问 | 无法验证 | 已定位本地候选字段契约，仍缺线上版本核验与授权真实响应；不臆造接口 |
| 七阶段实际执行和前置质量条件 | 未完成 | 当前支持数据集具备对象链测试，后续 Dataset/Policy 缺口机器可见；不是完整七阶段验收 |
| 按月执行缺口、已有 Task 的恢复动作 | 已通过（本地范围） | coverage 追加执行区间与 TaskState 动作；实际 PG 故障后的 RETRY_WAIT 走既有 retries 控制面，不另建调度 |
| 2018 起核心回填/全证券逐日覆盖 | 未运行 / 无法验证 | 历史 `gap_ranges` 保持 UNPROVEN；执行范围和单行月末样本不能证明证券逐日完整覆盖 |
| 主源失败/补源、quarantine、Unavailable | 已通过（本地 fixture 范围） | 明确 Policy 授权及固定拒绝/失败证据 |
| 双源关键字段冲突与全量质量规则 | 无法验证 | 缺真实双源授权样本及全历史执行证据 |
| 公开投影、日志关联、浏览器错误脱敏 | 已通过（定向反例范围） | API/SSE 与三处 formatter 反例；不作任意敏感字符串零泄露保证 |
| 必需 PostgreSQL 集成 | 已通过，0 skipped | 不能用全 gate 的 10 skipped 抵消必需集成 |
| 全量本地 CI gate / Web lint | 失败 | 定向通过不替代全 gate |
| 本次远程 CI / 合入 | 未运行 | 无 commit / push / PR / merge 授权；历史 PR #38 CI 不支持本次 dirty 增量 |
| 生产数据库、真实 `/data`、调度、部署、完整在线回填 | 未运行 | 尚未获得明确资源授权 |

本 Goal 的 BLOCKER：本地候选字段契约已定位，但真实来源版本、字段和授权响应核验仍缺证据；七阶段完整对象链及精确历史覆盖尚未闭合；双源冲突和全量质量验收缺证据；全量 gate 未通过；最终实时远程 main 因传输失败无法确认（最近成功时间见顶部续做节）。完整 WP / 生产认证还需要全历史可查询覆盖、生产资源范围授权、生产并发/失败恢复证据和当前增量的远程阻断 CI / 合入。当前 Goal 和 WP 均不得标记 `COMPLETE` 或 `VERIFIED`。

FOLLOW-UP：将本轮复现的原生 Windows / Legacy CI 失败、既有全量 Web lint 问题交由对应范围处理；生产性能/资源测量在资源授权后执行。未扩大到 WP-0303，也未重写 WP-0301/0302 的状态和计数。现有专题文档只有中文版本，本轮同步这三份中文专题记录与 CHANGELOG；未修改首页级 README/README_EN。

## 风险和回滚

对象文件发布与数据库提交仍然遵守现有“文件先发布、注册事务后提交”的协议。COMMIT 失败可能留下未注册的不可变文件；本轮验证拒绝将其算作成功并可重试，不自动删除这些证据。生产 orphan 清理和灾难恢复没有得到资源授权，也没有执行。所有 publication receipt 仅表示本地对象完整性，不能作为 `backtest_core` 或全历史生产认证。

只撤回本次增量：使用仓库外 `implementation-baseline/original-bytes` 恢复初次修改的 tracked 文件，新增治理修改 AGENTS.md 的原始字节使用 `reference-routing-baseline/original-bytes/AGENTS.md`；恢复前核对当前 SHA256 与交付 `changed-files.json` 一致，避免覆盖后来编辑。本轮新文件仅在内容 Hash 与交付 Hash 一致时删除。若只撤回后续参考路由，按 `reference-routing-baseline/round-original-files.json` 核验并恢复此次编辑前的五份文档字节。工作树 root、每个目标绝对路径和新文件归属都必须核验；不使用 reset/clean/stash，不撤回主 checkout 的三个文档或 f468 任何内容。未执行回滚。

本轮仅执行 fetch、远程只读核验、本地分支/worktree、编辑和临时测试资源操作；未执行 commit、tag、push、PR、merge、部署或生产数据变更。
