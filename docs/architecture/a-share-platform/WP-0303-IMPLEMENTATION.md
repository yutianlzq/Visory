# WP-0303 市场宽度与情绪 F2 受限实现及本地验收

验收日期：2026-10-08

> 当前候选：2026-10-19 [mainline convergence 第 22 节](#mainline-convergence)。第 1–21 节是 f468 累计历史，不代表当前候选的 gate、远程 CI 或来源认证结果。当前只收敛 WP-0303；原真实完整输入 Goal 不因此关闭。

> 2026-10-13 最新参考源码固定与开发回归见[第 14 节](#reference-development)；完整输入链累计核验见[第 13 节](#13-2026-10-13-full-input-to-feature-closeout部分推进与阻断)，此前完整平台与 all gate 的环境验收见[第 13.7 节](#137-现有环境补充验收完整平台通过all-gate-失败)。完整输入链仍为 PARTIAL/NO_GO，不以参考源码或本地技术回归关闭 WP-0303；以下各轮历史结论和计数保留原文。

> 历史证据说明：第 1–6 节记录最初受限实现，第 7 节记录仅扩指标 ID 后因派生键阻塞而未关闭 B5 的历史验收，均保留原文。用户追加授权后的当前 B5 关闭结论、实际完整数据库链路及独立回滚见第 8 节；B5 关闭不表示 WP-0303 或生产认证完成。

## 1. 本轮结论与边界

本轮允许范围内的受限实现及定向本地验收已完成，可以结束 `WP-0303-IMPLEMENTATION` Goal；**不代表 WP-0303 完整完成、完整 backend gate 通过或 Formal 能力可用**。WP-0303 为 `IN_PROGRESS`，不标 `VERIFIED`、`MERGED` 或 `RELEASED`；已验收计数保持 `15/45`，WP-0207 状态不变，生产 `NOT CERTIFIED`、`RELEASED=false`。

实现依据为 [WP-0303-PREP](WP-0303-PREP.md)，未重复 PREP。复用既有 Indicator Registry、受控 Builtin、Dependency Resolver、FeatureStore 和 FeatureRepository；没有新增平行发布链、Dataset、Raw Schema、Provider Mapping、Migration、HTTP API、页面、Desktop、调度或依赖。

`market_breadth`、`market_emotion` 均保持 `missing_capabilities`。本轮“发布”只指临时目录及隔离数据库中的 FeatureSnapshot/Bundle 测试，不是运行环境数据发布、部署或生产认证。

## 2. 基线及已有输入保护

- 实际工作目录：`C:\Users\lzq11\.codex\worktrees\f468\Visory`，不是环境默认的 `fc68`。
- 开工检查工作区并执行 `git fetch --all --prune`；指定基线、本地 detached `HEAD` 与该次 fetch 后 `origin/main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`，差异 `0 behind / 0 ahead`。后续实现基于此固定基线；不把缓存 ref 当作持续实时查询。
- 原有五份输入：`docs/CHANGELOG.md`、`docs/INDEX.md`、`IMPLEMENTATION-STATUS.md`、`WP-0302-IMPLEMENTATION.md` 和未跟踪的 `WP-0303-PREP.md`。先备份到 `C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-input-20261008`，再在当前树实现。
- PREP 与 WP-0302 验收记录保持开工时字节内容；CHANGELOG/INDEX 追加当前 WP 路由，状态文档保留历史记录并最小同步当前汇总。五份输入没有被撤销或整体覆盖。
- 未执行 pull、分支创建/切换、worktree 创建、stash、reset、rebase、merge、commit、tag、push、PR 或部署。原输入与本轮实现均未合入远端。

## 3. 实现内容及输入状态

### 3.1 单一 Dataset 投影与旧 F1 保持不变

`FeatureDependencyResolver` 的 Catalog 从既有真实 `DatasetDefinition` 构建只读投影，范围仍为原八个 Dataset；对齐 `instrument_status_daily.status_date/instrument_status/is_tradable` 和 `benchmark_index_1d.return_type`，不再宣称不存在的 `shares_outstanding`、`corporate_action.factor` 可用。自定义 Catalog 与真实投影不一致直接拒绝；直接 Materializer 同样检查 Definition 输入字段。

原 14 个 F1 Definition、版本和 Hash 未改。回归从固定 `HEAD` 加载基线 Definition 并逐项比较完整载荷及 Hash。`return_point_in_time_adjusted`、`turnover_ratio`、`trading_halt_state` 与真实字段不一致的旧引用仍 fail-closed，不在本 WP 原地修订或用伪造 Catalog 放行。

仅 Indicator ID 校验兼容点分命名，其他 Dataset/Capability/资源标识符未放宽。新增 65 个 F2 Definition，版本 `1.0.0`、`domain=a_share`、`frequency=1d`、`F2_LONG_TERM`、`FROZEN_REQUIRED`、PIT、单输出 `value`。公式、股票池/分母、状态、方向、权重、SLA、标准化和递归语义进入固定参数契约及 Definition Hash；调用方不能覆盖该参数。

### 3.2 真实契约受限路径

新增 `src/services/platform/market_sentiment.py` 是 C-006 内部确定性计算模块，不是新的 Registry、Store 或公共 FeatureRow Schema。37 个原始指标中：16 个 `EXECUTABLE`、18 个 `BLOCKED`、3 个 `FIXTURE_ONLY`；另有 28 个标准化/维度/总分/平滑/状态 Definition。依赖传播后共有 43 个指标在真实受限路径不可用，不能借助非空 fixture 放行。

已实现的 16 个原始指标：

- 审计：`listed_count`、`bar_valid_count`、`limit_rule_count`；
- 涨跌停：`limit_up_count`、`limit_down_count`、`limit_up_down_spread`、`limit_break_count`、`limit_break_rate`、`max_streak_height`、`streak_stock_count`、`promotion_rate`；
- 流动性：`market_amount_cny`、`amount_ratio_20`、`top20_amount_concentration`、`zero_or_suspended_ratio`；
- 风险解释：`median_amplitude`。

`EXECUTABLE` 表示当前契约允许算法与隔离发布测试，不表示真实 Provider 或完整历史已认证。首封时刻、固定基准波动/回撤仍为 `FIXTURE_ONLY`；PIT 调整收益、流通市值、换手率及其派生项仍为 `BLOCKED`。纯评分算法接受显式合成原始输入，真实计算入口不接受这些替代值。

每日冻结 `cn_a_equity_v1`，仅沪深主板、创业板、科创板股票。Manifest Hash 固定日期、成员/原因、DataSnapshot 和 CanonicalPartition 引用；校验资产类型/交易所身份、上市区间、开放日、`available_at<=cutoff`、OHLC、金额及状态。市场行仍使用 `FeatureRow.entity_key=aggregate:cn_a_equity_v1`，不进入资产身份解析。

独立记录各指标 `valid_count`、`denominator_count`、`coverage_ratio`；EXECUTABLE 原始行将诊断写入确定性 `data_flags`，每行仍只有一个 `value`。分母零、未知状态和历史缺口不冒充零值；连板历史全部未知时数量为空，部分历史未知时明确 `HISTORY_GAP/PARTIAL`。核心行情 SLA 未达标时保留诊断事实但标为 `SCOPE_SLA_FAILED/PARTIAL`，不认证能力。

多日输入必须显式提供完整开放交易日序列，区间缺开放日拒绝；非开放日不作为有效候选。每日 scope Hash 不同的行不能混入同一 Partition，历史计算使用各日冻结成员，不用当前股票池回填。

### 3.3 标准化、固定权重及状态

- 标准化只读取 T-1 及更早的最多 252 条有效观察；60 条以前 `WARMING_UP`。使用 Decimal、median、`1.4826*MAD+1e-12`、z 截断及固定方向；拒绝 T/未来/重复日期与晚于 cutoff 的输入。
- 五维权重和 `25/30/20/15/10` 总权重按 PREP 固定，缺一必需输入就缺失，不补零、不沿用昨日值、不重加权。
- 平滑 alpha 为 0.5；首个完整日/缺失断点后的首日用 raw 初始化。状态含 20/40/60/80 边界、相邻两开放日确认、恰好 5 分直接迁移、方向反转、跨级迁移和缺失断点重置。
- 真实依赖尚缺，因此 raw、smoothed 和 state 始终为空。完整输入 fixture 仅证明标准化、合成、平滑与状态算法，不证明被阻断原始指标的真实来源或 Provider 算法已实现。

### 3.4 实际发布与固定消费门禁

既有 `materialize_and_publish` 支持市场 Preview 的 PARTIAL/UNAVAILABLE 诊断与 warming-up 空值，但拒绝 FAILED/STALE、混合 scope、伪造 Definition、真实路径非空的不可用指标及未隔离的 `FIXTURE_ONLY` 行。市场 Snapshot 始终 PROVISIONAL 且明确缺失两个市场能力；Store 和 Repository 的实际 Snapshot/Bundle 写入入口共同拒绝伪造认证与 Formal/Paper 绑定。

新增 Python 层 `consume_bundle(bundle_id, ConsumerRequirement)` 只消费固定已发布 Bundle，核验质量、状态、源可见性约束和固定 Parquet Hash；不支持“最新”。Preview 必须明确允许 provisional 并接受其质量/缺失元数据；这不是认证能力。Paper 使用既有 `FORMAL_BACKTEST` 要求，不能消费市场诊断 Bundle。未增加 HTTP/runtime API。

`FeatureStore(fixture_only=True)` 只用于显式隔离算法测试，行必须标注 FIXTURE_ONLY；不能因此认证或 Formal 消费。没有修改生产配置或运行入口。

### 3.5 Correction 与证据边界

完整评分 fixture 将最早受影响日改为另一个显式原始值，重算严格 T-1 统计、所有后续平滑、pending 状态与 regime；同一固定测试 scope/cutoff 下发布新 Partition/Snapshot revision。测试验证原 Manifest identity 不变、新内容 Hash/Bundle Hash 改变、旧 Parquet 字节与旧 Snapshot/Bundle 固定引用保持不变，并拒绝改变逻辑 identity 的 Correction。

隔离 PostgreSQL 另验证长度合格受限指标的重新计算、revision/supersedes、Store 重启后的固定 Bundle 消费及旧引用保留。该合成源内容变化用于验证算法和既有不可变控制面，并非真实 Canonical 源修订认证。

真实源 revision 若改变固定源引用或股票池 Manifest Hash，就改变 plan/partition identity；不能伪装成同一逻辑 Manifest 的 Correction，也不能改绑“最新”。完整评分的 PostgreSQL 落库与真实历史 Correction 仍受 B1–B3、B5 阻断。

## 4. 实际本地验证

命令在固定 `f468` 工作树执行，使用已有 Python 3.12.9；没有安装/升级/下载依赖。计数包含重叠套件，**不得相加为独立测试总数**。

| 命令 | 实际结果及范围 |
| --- | --- |
| `python -m pytest tests/platform/test_market_sentiment.py -q --tb=short` | **47 passed, 1 warning**；Definition/DAG/输入/算法/发布门禁/Correction。自审新增 4 个反例先为预期 RED，再修正为 GREEN |
| `python -m pytest tests/platform/test_market_sentiment.py tests/platform/test_indicator_registry.py tests/platform/test_feature_store_contracts.py tests/platform/test_feature_partition_golden_bytes.py -q --tb=short` | **111 passed, 1 warning**；包含既有 Store、固定 Parquet Golden 与 F1 保持不变 |
| `python -m pytest tests/platform --ignore=tests/platform/api -q --tb=short -rs` | **666 passed, 5 skipped, 2 warnings**；包含 Contract/Golden/Registry/generated export 与核心平台回归，不包含 API 目录 |
| `python -m pytest tests/integration/platform/test_market_sentiment_postgres.py tests/integration/platform/test_feature_store_postgres.py tests/integration/platform/test_feature_repository.py -q --tb=short -rs` | **14 passed, 1 warning，0 skipped**；本地现有 `postgres:16`、tmpfs、随机 loopback 端口及隔离测试数据库；新市场测试 3 项 |
| `python scripts/export_platform_contracts.py --check` | 通过；generated JSON Schema/OpenAPI/Web types 没有变更，不直接编辑生成文件 |
| `python scripts/check_ai_assets.py` | 通过 |
| `python scripts/check_visory_baseline.py` | 通过；相对链接无破损，外部源码与启用 workflow 边界通过 |
| `python -m py_compile @files` | 通过，文件清单见下方 |
| `python -m flake8 --select=E9,F63,F7,F82,F401,F821 @files` | 通过 |
| `git diff --check` | 通过 |

受影响 Python 的实际 PowerShell 命令：

```powershell
$files = @(
  'src/repositories/platform/feature.py',
  'src/schemas/platform/indicator.py',
  'src/services/platform/feature_dependency.py',
  'src/services/platform/feature_store.py',
  'src/services/platform/indicator_registry.py',
  'src/services/platform/market_sentiment.py',
  'tests/platform/test_indicator_registry.py',
  'tests/platform/test_market_sentiment.py',
  'tests/integration/platform/test_market_sentiment_postgres.py'
)
python -m py_compile @files
python -m flake8 --select=E9,F63,F7,F82,F401,F821 @files
```

5 个 skipped 的精确范围：`tests/platform/artifacts/test_namespace_resolver.py:38` 三项、`tests/platform/artifacts/test_orphan_sweeper.py:92` 一项，均因 Windows `WinError 1314` 无符号链接权限；`tests/platform/database/test_settings_and_secrets.py:172` 一项为 Windows 不支持权威 POSIX mode bits。它们不是通过或跳过的市场/PostgreSQL验收。

临时日志保存在本机 `C:\Users\lzq11\AppData\Local\Temp`：`visory-wp0303-targeted-final.log`、`visory-wp0303-platform-core-final.log`、`visory-wp0303-postgres-final.log`。日志不是仓库/远程 CI artifact，也不含凭据。自己的临时 PostgreSQL 容器在停止后自动删除，临时密码文件与上下文文件已删除；没有启动或复用其他数据库。

### 4.1 完整 gate 未通过与未验证项

| 实际命令或检查 | 缺口及处置 |
| --- | --- |
| `bash scripts/ci_gate.sh all` | syntax/critical flake8/export 阶段通过；`scripts/test.sh code` 选择环境默认 Python 3.14，因缺 pandas 失败，exit 1 |
| `python3` 函数固定到现有 Python 3.12 后的同一 all gate | code 阶段导入未修改的 `data_provider/efinance_fetcher.py` 时缺 `tenacity`，exit 1；没有继续完成整个 gate |
| `bash scripts/ci_gate.sh offline-tests` | 收集阶段 **131 errors**，exit 2；既有导入链缺 `tenacity`、`markdown2`、`json_repair`、`nacl` 等，未执行全量离线测试 |
| `python -m pytest tests/platform -q --tb=short` | API 导入链缺 `markdown2`，**3 collection errors**，exit 2；不把排除 API 的核心套件解释为完整平台套件通过 |
| Web lint/build、浏览器、Desktop、runtime API E2E | 未运行：没有客户端、生成类型或 runtime API 变更；不安装客户端依赖 |
| 远端本轮 HEAD 的 Governance/Python/Web CI、PR/合入 | 未执行：本轮禁止 commit/push/PR；旧 WP-0302 CI 不代表本轮未提交实现通过 CI |
| 覆盖率百分比、真实 Provider/历史/生产数据、调度/性能/灾备 | 未测量或未验证，不作 80% 覆盖率或生产认证声明 |

Python 3.12 all gate 使用的实际绑定命令：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -c 'python3() { /c/Users/lzq11/AppData/Local/Programs/Python/Python312/python.exe "$@"; }; export -f python3; bash scripts/ci_gate.sh all'
```

对应失败日志为 `visory-wp0303-backend-gate.log`、`visory-wp0303-backend-gate-python312.log`、`visory-wp0303-offline-tests.log`、`visory-wp0303-platform-tests.log`。上述环境/既有导入链缺口按 FOLLOW-UP 记录，未使用 stub、扩大范围修复或安装依赖绕过。

## 5. 剩余 BLOCKER 与远端门禁

| 编号 | 仍未闭合的契约/能力 |
| --- | --- |
| B1 | 无 PIT 流通市值 Dataset/字段/质量与 Provider 契约；`small_large_return_spread` 不得用当前或总市值替代 |
| B2 | 实际 `security_master@1.0.0` 无 `shares_outstanding`；旧 `turnover_ratio` 仍阻断，不改旧 Definition/Hash |
| B3 | 实际 `corporate_action@1.0.0` 无 `factor`，也无已认证推导方法；PIT 调整收益/价格、宽度及相关情绪维度不可用 |
| B4 的残余 | Catalog 投影漂移已修复；旧 `trading_halt_state@1.0.0` 仍引用不匹配字段，必须另行版本化修订，不能在本 WP 原地改写。基准字段已投影，但 PREP 中两个基准算法仍保持 FIXTURE_ONLY |
| B5 新增 | 现有 PostgreSQL `feature_partition.indicator_id` 为 64 字符；三个 PREP normalized ID 长度 67–69。完整 score DAG 在任何文件生成/SQL写入前拒绝；不改名、不扩表、不新增 Migration |
| 远端门禁 | 本轮授权外的 commit/push/PR、当前 PR head 三项阻断 CI、语义 review 和合入仍需独立执行/验收；不能复用旧 CI 宣称完成 |

B5 的精确 ID：

```text
market.sentiment.normalized.risk_appetite.small_large_return_spread       67
market.sentiment.normalized.risk_appetite.top_amount20_median_return     68
market.sentiment.normalized.risk_appetite.high_turnover_return_spread    69
```

这些是完整 WP/Formal 能力的 BLOCKER，不通过伪造 Catalog/Capability、缩写别名或测试 fixture 隐藏。本轮完成定义只覆盖受限实现与允许的本地验收；后续上游契约闭合、真实历史认证和长 ID 迁移必须另行授权。

## 6. 兼容性、风险与回滚

- **兼容性**：旧 F1 Definition/版本/Hash 和旧固定 Partition/Snapshot/Bundle 不改；真实字段投影和直接物化门禁会让原先仅靠错误 Catalog“可解析”的旧调用失败，这是显式 fail-closed，而非补兼容 fallback。无公共 FeatureRow、API/生成 Web 类型、数据库 Schema 或依赖变化。
- **风险**：受限原始事实/部分标准化可保留不完整诊断，但没有完整市场能力；完整算法测试使用合成输入。每日期股票池 Hash 不同，不能混写或伪装同一逻辑 Correction。B5 阻断完整 PostgreSQL评分链；完整 backend/API/远程 CI 仍未完成。
- **本地撤回**：以开工备份为文档真源恢复本轮对 CHANGELOG/INDEX/状态的增量，保留原五份输入；将五个原有生产 Python 文件及原 `test_indicator_registry.py` 仅撤回本轮差异，删除本轮新计算模块、两份测试和验收记录，撤回两个专题的新增实现路由。先检查是否出现更新的用户改动，禁止整体 `git reset/restore` 覆盖原输入或他人内容。
- **以后若获授权合入**：revert 完整 WP-0303 change set，不改 WP-0301/0302，不 force-push、不改绑旧 Bundle、不删除固定引用或 Parquet，也不原地重写历史 Definition/Manifest identity。真实源引用变更形成新固定 identity，不能借回滚切到“最新”。
- **数据与迁移回滚**：本轮没有新 Migration、生产数据或运行环境发布，无生产数据库降级动作；测试临时数据库/凭据已清理。未来关闭 B5 时必须另写独立迁移/备份/回滚方案。
- **文档同步**：仅本 WP 中文专题、索引、CHANGELOG、状态/验收记录；没有对应英文专题的受影响副本，不改中英文 README、API、Web 或 Desktop。


## 7. 2026-10-08 B5 指标 ID 持久化契约增量验收

### 7.1 当前结论、授权与保护

**B5 未关闭，当前 Goal 未完成。** 三个 `indicator_id` 的真实迁移、未迁移库 fail-closed 和独立安全降级已实际验证；但完整评分 fixture 在 `feature_partition.partition_key VARCHAR(255)` 遇到新的长度阻塞，未到达数据库重启消费及完整 Correction 验收。没有以 skipped、mock SQL、改名、别名或截断替代成功路径，也不把下述部分通过宣称为 B5 通过。

- 工作树固定 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。开工再次检查工作区并 fetch 后，`HEAD=origin/main=efe8e9b362cba13eca183c55be57bbbbc832b60b`；没有 pull、切分支、rebase、merge 或新建 worktree。
- 全部 **17 项既有变更**先逐文件备份并记录 SHA256，备份为 `C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-b5-input-fbbbe746b2fb4302adbf47edac9cbbbe`（`inventory.json`）。本次只追加 B5 增量；逐文件复核为 10 项字节不变、7 项仅 B5 增量。PREP、WP-0302 验收、F2 实现/fixture、Registry Definition、既有非 B5 代码与专题/索引保持开工字节内容。
- 本 Goal 仅授权后继 migration 扩三个 `indicator_id`，**不授权扩 `partition_key` 或其他字段，也不授权改变固定键算法**。实际唯一 head 从 `0013_wp0302_feature_store` 增加为 `0014_wp0303_indicator_id`；历史 0013 未改写。
- WP-0303 继续 `IN_PROGRESS`，唯一 WP 已验收数 **15/45**；`market_breadth/market_emotion` 仍 missing，Formal/Paper 继续拒绝。B1–B3 上游 Dataset/Provider/PIT 调整、B4 旧 F1 残余未处理；WP-0207/0304/0305 未推进。生产 `NOT CERTIFIED`、`RELEASED=false`。

### 7.2 已实现并局部验收的契约

1. `0014_wp0303_indicator_id` 只将 `feature_partition`、`feature_snapshot_partition_ref`、`feature_bundle_partition_ref` 的 `indicator_id` 从 64 扩为 128；不修改其他列、约束/索引定义、记录或旧固定文件。
2. `INDICATOR_ID_MAX_LENGTH=128` 是 Python 长度真源，Schema 字段和 SQLAlchemy 三列 metadata 共用；其他资源 ID/字段仍保留原上限。`FeatureRow/Partition/PartitionRef/Instance/InstanceKey/DependencyRef/Definition` 明确拒绝 129。生成 JSON Schema/OpenAPI 补 `maxLength`，仅通过 exporter 更新；生成 Web TypeScript 无 diff。
3. Store 在文件锁/Parquet 生成前开无 DML 的预检事务，锁定三表并反射**当前真实连接**上的列宽；持有 `ROW EXCLUSIVE` 表锁直至发布退出。Repository 的三个 add 入口同样在任何 DML 前验证实际列宽；不能以 Python metadata=128 推断旧库已迁移，也不缓存一次检查放过之后的 downgrade。Store 长度拒绝保持既有 `FeatureMaterializationError`，Repository 保持 `ValueError`；只转换长度预检的 ValueError，不隐藏数据库错误。
4. 真实旧 revision 下 65/128 和三个实际 67/68/69 ID 提前拒绝，无新文件或控制面残留；64 可写。新 revision 下 64/65 与两个 67/68 实际 ID 经 Store/Repository/数据库无截断写入，后两者可重启 Store 固定 Preview 消费。Repository 的独立三列 128 边界往返也通过，但其有效短 `partition_key` 测试**不替代 Store 128 或完整 DAG 验收**。
5. downgrade 先显式对三表执行 `ACCESS EXCLUSIVE`，再检查三列是否存在 `char_length(indicator_id)>64`，完成所有检查后才缩列。分别只在三个表之一放入长 ID 均拒绝；拒绝后列宽、数据、约束/索引、Alembic version、旧固定文件完全不变。短 ID 数据可安全降级再升级，所有旧记录/引用保持不变；真实锁超时反例通过 SQLSTATE=`55P03`（`lock_not_available`）精确证明预检事务阻止并发 downgrade，不将任意 SQL 失败当作互斥证据。
6. 开工 F1/F2 Definition 集合固定内容 Hash 分别为 `sha256:e65941d7c70b0e490ac95526a26c2baaafb9ecdf7ce73511156b72bb3a8a1d23`（14 个）和 `sha256:028758764bcb833e8231027db3b9f06dd9322596a9c1c0a291d18ad2871a858b`（65 个）。完整载荷/版本/Hash 回归通过；不改旧 F1/F2 Definition。

### 7.3 未关闭 BLOCKER 与完整链路失败证据

| 项目 | 实际结果 | 处置 |
| --- | --- | --- |
| B5 原始三列 64 字符缺口 | 真实 0013→0014 迁移及三列 128 检查通过 | 仅该子缺口局部验收；不等于 B5 关闭 |
| B5 新暴露的 `partition_key` | 原 67/68/69 指标在不改 ID/Hash 的 fixture 中生成键长 **254/255/256**；69 字符 `market.sentiment.normalized.risk_appetite.high_turnover_return_spread` 超过 255。合成 128 字符 ID 的 Store 最短边界键仍为 **257** | 保持现有列和键算法；需另行明确扩范围授权，不能擅自调整 |
| 完整 fixture PostgreSQL 发布 | `test_complete_score_dag_migration_fixed_consumption_restart_and_correction` 实际经过 Store→Repository→SQL；数据库报 `psycopg.errors.StringDataRightTruncation: value too long for type character varying(255)` | 测试仍失败，不改为 skip/xfail；已断言事务全部回滚、无新增 Parquet、旧短 ID 文件与控制面保持不变 |
| Store 128 正向路径 | `test_new_revision_boundary_publication_round_trip[128]` 同源失败 | Repository 128 可写不代表 Store 完整长度契约可用 |
| 完整 fixture 重启固定消费/Correction | 上述初次发布即失败，后续断言尚未到达 | 不声称完整数据库 Correction/三个长 ID 全部落库/旧完整 fixture Hash 链已验收；既有内存完整 fixture 与短 ID PostgreSQL Correction 回归是独立部分证据 |
| B1–B3、B4 残余及正式市场能力 | 未改变上游契约、旧 Definition 或能力认证 | 继续 BLOCKER；fixture 显式隔离、PROVISIONAL，Formal/Paper 拒绝 |

**2026-10-08 自动续跑只读复核**：保留现有 `_partition_key` 算法，以通过 `FeatureInstanceKey` 验证的输入、现有持久化列上限 `indicator_id=128`、`definition_version=32`、`frequency=32`、固定 SHA256 摘要和 ISO 日期区间推导，键长可达 **386**：`128 + 32 + 32 + 64 + 64 + 21 + 45`（末项为固定文字与分隔符）。因此只扩到 256/257 也不能覆盖现有其他列边界下的 128 字符指标 ID。此项仅为长度/范围决策证据，不是新增数据库成功路径；Schema 本身不提供所有其他字段的统一长度上限，不能把该推导当作整个 Schema 的无条件上限。完整 fixture 的 256 与边界 Store 的 257 真实失败仍保留；修改 `partition_key` 长度契约及后继迁移需要新的明确授权，本次自动续跑未改变任何代码、Schema、migration、fixture ID 或固定键。

### 7.4 本次实际验证与未验证项

使用机器已有 Python 3.12.9 和 `postgres:16` 镜像，没有安装、升级或下载依赖。两轮临时容器 `visory-wp0303-b5-6b15628615954a0a`、`visory-wp0303-b5-4d677ecbfdb84201` 均使用 tmpfs、随机 loopback 端口；每项 integration 新建随机 `visory_test_<20hex>` 数据库并在 finally 删除，不连接生产或已有业务库。末轮结束核验随机测试库计数为 0，两轮容器及本 Goal 密码/上下文文件均已清理。计数包含重叠套件，不能相加成独立测试总数。

| 实际命令 | 结果与边界 |
| --- | --- |
| `python -m alembic heads` | 唯一 head `0014_wp0303_indicator_id` |
| `python -m pytest tests/integration/platform/test_feature_indicator_id_postgres.py -q --tb=short -k old_revision` | 异常类型兼容 RED：**5 failed / 1 passed**；仅恢复 Store 既有错误类型后 GREEN：**6 passed / 15 deselected**。该定向结果是同一数据库套件的子集，不替代完整 DAG 验收 |
| `python -m pytest tests/platform/test_feature_indicator_id_contract.py -q` | **15 passed, 1 warning**；64/65/三个实际长 ID/128/129、七个 Schema、三列 metadata、原 14/65 Definition Hash |
| `python -m pytest tests/platform/test_feature_indicator_id_contract.py tests/platform/test_indicator_registry.py tests/platform/test_market_sentiment.py tests/platform/test_feature_store_contracts.py tests/platform/test_feature_partition_golden_bytes.py -q --tb=short -rs` | **126 passed, 1 warning**；F1/Registry、F2、Store、Golden |
| `python -m pytest tests/platform --ignore=tests/platform/api -q --tb=short -rs` | **681 passed, 5 skipped, 2 warnings**；Contract/Golden/export 核心回归。5 skips 仍为上文 Windows symlink/POSIX 权限限制，不是跳过 B5 迁移 |
| `python -m pytest tests/integration/platform/test_feature_indicator_id_postgres.py tests/integration/platform/test_market_sentiment_postgres.py -q --tb=short -rs` | **22 passed, 2 failed, 1 warning，0 skipped**；真实迁移/旧库保护/长 ID 部分成功/降级保护通过；上述两个 Store `partition_key` 反例失败，B5 保留 |
| `python -m pytest tests/integration/platform/test_feature_store_postgres.py tests/integration/platform/test_feature_repository.py tests/integration/platform/test_postgres_foundation.py -q --tb=short -rs` | **17 passed, 1 warning，0 skipped**；既有存储/Repository/数据库基础及新 head 回归 |
| `python scripts/export_platform_contracts.py --check` | 通过；仅 6 份生成 JSON Schema/OpenAPI 增加 `maxLength`，Web types 无变化 |
| `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | 通过 |
| `python -m py_compile @files`、`python -m flake8 --select=E9,F63,F7,F82,F401,F821 @files` | 通过；清单见下方。all gate 的全仓 syntax/critical lint/export 阶段也通过 |
| `git diff --check` | 通过；核对 B5 输入备份 diff 和新文件，未撤销原 17 项变更 |
| 固定 `python3` 为 Python 3.12 的 `bash scripts/ci_gate.sh all`（命令同第 4.1 节） | **exit 1**；未修改的 `data_provider/efinance_fetcher.py` 仍缺 `tenacity`，没有执行全量测试。不修复既有依赖缺口，也不以核心通过代替 all gate |
| 在 `apps/dsa-web` 执行 `npm.cmd run lint`、`npm.cmd run build` | 均 **exit 1**：没有 `node_modules`，`eslint`/`tsc` 不存在；本机 Node 16.20.2 还低于 manifest 范围。没有运行 npm ci 或更改依赖；客户端构建未验证 |

```powershell
$files = @(
  'migrations/versions/0014_wp0303_indicator_id.py',
  'src/repositories/platform/feature.py',
  'src/schemas/platform/indicator.py',
  'src/schemas/platform/feature.py',
  'src/services/platform/feature_dependency.py',
  'src/services/platform/feature_store.py',
  'src/services/platform/indicator_registry.py',
  'src/services/platform/market_sentiment.py',
  'tests/platform/test_feature_indicator_id_contract.py',
  'tests/platform/test_indicator_registry.py',
  'tests/platform/test_market_sentiment.py',
  'tests/integration/platform/test_feature_indicator_id_postgres.py',
  'tests/integration/platform/test_market_sentiment_postgres.py',
  'tests/integration/platform/test_postgres_foundation.py'
)
python -m py_compile @files
python -m flake8 --select=E9,F63,F7,F82,F401,F821 @files
```

本轮日志在 `C:\Users\lzq11\AppData\Local\Temp`，包括 `visory-wp0303-b5-targeted.log`、`visory-wp0303-b5-error-contract-red.log`、`visory-wp0303-b5-error-contract-green.log`、`visory-wp0303-b5-platform-core.log`、`visory-wp0303-b5-postgres-final.log`、`visory-wp0303-b5-postgres-regression.log`、`visory-wp0303-b5-backend-gate.log`、`visory-wp0303-b5-web-lint.log`、`visory-wp0303-b5-web-build.log`；不是远端 CI artifact。全量 API/offline suite 本轮未重跑（上一轮收集缺依赖仍见第 4.1 节）；Desktop/E2E/远端 CI/覆盖率/生产锁时长、性能与灾备未验证。没有 commit/tag/push/PR/merge/部署或运行环境发布。

### 7.5 兼容性、升级与独立回滚方案

- **兼容性**：三列扩宽和 Schema `maxLength=128` 不改变已存在的短 ID、固定文件路径、Definition/Partition/Snapshot/Bundle 内容 Hash 或引用。旧数据库仍可接收不超过其实际上限的 ID，长 ID 必须先迁移；新库仍有上述派生 `partition_key` BLOCKER。其他字段的上限和 TypeScript string 类型不变，未新增 API/UI/调度/依赖。长 ID 写入后旧代码的 metadata-only 64 长度保护会拒绝重新发布，不能承诺降级代码继续处理完整长 ID fixture。
- **升级/备份**：本轮只在随机临时数据库运行 `upgrade_database(engine, '0013_wp0302_feature_store')` 再到 `'0014_wp0303_indicator_id'`。任何以后已有数据库的升级需独立授权；先确认实际 revision、备份控制面与固定文件及其引用清单、核验可恢复性，再停写并安排维护窗口。升级只执行三项 ALTER COLUMN；降级显式锁三表为 `ACCESS EXCLUSIVE`。必须评估锁等待并设置操作级超时，不能假定“扩 varchar 就无锁/零影响”；本轮仅验证锁互斥，不提供生产耗时或在线升级保证。
- **独立数据库降级**：只在明确授权的连接上运行 `downgrade_database(engine, '0013_wp0302_feature_store')`。任一三列中存在 >64 ID 时必须拒绝，保持 schema/data/version 不变；不要为了降级截断、改名、删记录、删固定文件或重绑 Bundle。三列均无长 ID 才允许事务性缩列；降级后检查三列=64、约束/索引、数据/固定引用和 migration version，必要时独立再次升级。测试已分别覆盖拒绝和安全降级/重升，不把数据库降级与代码回滚联动执行。
- **独立代码回滚**：本轮未提交，只撤回本次相对 17 项输入备份的 B5 增量，保留上一轮实现与用户后续修改；不要整体 reset/restore。已升级库可以保留 128 列宽并独立回滚代码，但应停止长 ID 发布，确认旧代码行为与读取兼容性；若已有长 ID，数据库仍不得缩列。数据库版本/schema 与代码部署是两项独立决策，恢复完整备份也须单独审核，不通过破坏固定引用来“配合回滚”。
- **文档**：保留第 1–6 节与 PREP 原历史，当前状态/CHANGELOG 最小追加 B5 结果；本 WP 无对应英文专题，不修改中英文 README。完成 B5 仍需要 `partition_key` 范围决策及真实完整 fixture 的初次发布、重启固定消费和 Correction 全链路全部通过。


## 8. 2026-10-08 B5 后继派生键迁移与完整数据库链路验收

### 8.1 当前结论与追加授权

**B5 已关闭，`WP-0303-B5-ID-CONTRACT` Goal 的本地迁移及完整隔离 fixture 验收完成。** 用户在第 7 节阻塞报告后明确“授权”，允许在本 WP 追加 `partition_key` 长度契约与后继 migration；仍不得改 ID、键算法、Definition 版本/载荷/Hash 或旧固定引用。只关闭持久化长度缺口，不关闭 B1–B3 或 B4 残余，不将算法 fixture 当成真实来源认证。

- 实际工作树仍为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。追加授权后再次检查工作区并 `git fetch origin`，`HEAD=origin/main=efe8e9b362cba13eca183c55be57bbbbc832b60b`；未 pull、切分支、rebase、merge 或创建 worktree。
- 追加授权前 **28 项已有变更**逐文件 SHA256 备份到 `C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-b5-key-input-cac8c70ae5c04365932a62c9af9d62d9`，包含 `inventory.json`；第 7 节原 17 项备份保留。本次不覆盖或撤销此前成果，第 1–7 节正文保留，仅更新顶部历史路由并追加本节。
- WP-0303 继续 **`IN_PROGRESS`**；45 个唯一 WP 计数仍为 **`VERIFIED=15 / IN_PROGRESS=2 / NOT_STARTED=28 / RELEASED=0`，15/45**。生产 **`NOT CERTIFIED`、`RELEASED=false`**。本轮没有 commit/tag/push/PR/merge、部署或运行环境数据发布。

### 8.2 完整长度契约与未迁移库保护

| 层/迁移 | 最终契约及保护 |
| --- | --- |
| `0014_wp0303_indicator_id` | 保留第 7 节实现与字节，只扩三表 `indicator_id`：64→128；历史 0013 无修改 |
| 新后继 `0015_wp0303_partition_key` | `down_revision=0014_wp0303_indicator_id`，唯一 head；**只**扩 `feature_partition.partition_key`：255→386，不改变其他列、约束/索引、键内容或数据 |
| Schema/metadata | 指标 ID 共用 `INDICATOR_ID_MAX_LENGTH=128`；派生键共用 `FEATURE_PARTITION_KEY_MAX_LENGTH=386`，SQLAlchemy metadata 与 Schema `maxLength` 一致。其他资源/字段边界不变 |
| Store | 使用原 `_partition_key` 计算整个 plan 的键，先拒绝 >386；数据库模式在文件锁/Parquet 前检查三表实际 ID 列宽及实际 key 列宽；预检、水合和控制面持久化复用同一 Session/事务，兼容 `pool_size=1/max_overflow=0`；COMMIT 成功后才写入新缓存，失败回收本次新文件，不用新 Python metadata 推断旧库容量 |
| Repository | `add_partition/add_snapshot/add_bundle` 保留 ID 保护，分区入口另预检 key；先 Python 契约再真实列宽，任何 DML 前失败。当前事务先锁三表 `ROW EXCLUSIVE`，Store 在同一发布事务中保持预检表锁至控制面 COMMIT，与 downgrade 互斥；不缓存旧库列宽 |
| 生成契约 | 仅通过 exporter 更新 6 份 C-006/OpenAPI JSON；本轮 key 增量只影响 `C-006.FeaturePartition.schema.json` 和 `C-010.openapi.json`。生成 Web TypeScript 无 diff，无新增 API/UI/调度/依赖 |

386 按第 7.3 节现有持久化字段边界推导：`128 + 32 + 32 + 64 + 64 + 21 + 45`；它不是整个 Schema 其他字段的无条件统一上限。真实原算法的最大 386 键已经过 Store→Repository→PostgreSQL→重启读取验证；没有改键算法、ID、日期格式或 Hash，也没有缩写/替代别名。

兼容性明确区分 revision：0013 仍提前拒绝 >64 ID；0014 可存长 ID，但完整 fixture 的原 256 键及合成 128 ID 的 257 键仍提前拒绝；0015 才可完成这两条 Store 成功路径。同一 Store 在 0014 拒绝后，经实际升级至 0015 可以成功，证明没有用缓存或 metadata 掩盖真实数据库状态。超长失败前后数据库、既有文件及固定引用均不变。

### 8.3 真实 PostgreSQL 及完整 fixture 证据

- 使用本机已有 `postgres:16` 镜像（`--pull never`），本 Goal 专用临时容器 `visory-wp0303-b5-569f091e166b4582`，tmpfs、loopback-only 随机端口；每项测试创建随机 `visory_test_<20hex>` 数据库，在 finally 删除。只连接这些临时数据库，未连接生产或既有业务库。结束核验测试数据库计数 **0**，精确停止该容器（`--rm`），临时密码及上下文文件已删除。
- 最终单连接事务与 COMMIT 失败补验使用第二个本 Goal 临时容器 `visory-wp0303-b5-pool-59dca5c85f5b4eca`（同为本地已有镜像、tmpfs、loopback-only 随机端口），最终完整回归也在该实例逐测试随机数据库执行。结束再次核验随机测试数据库计数 **0**，容器已精确停止并由 `--rm` 删除，密码及上下文文件已删除；两轮日志与输入备份保留。未复用任何既有业务库。
- 实际运行 **0013→0014→0015**，逐项比较三个 `indicator_id`、派生键列、其他列的类型/nullability、全部 Feature 约束、索引、短 ID 控制面记录、固定文件/引用与 migration version；除授权列宽及版本外均保持不变。没有以 mock SQL 或 metadata.create_all 代替迁移。
- 边界覆盖 **64、65、三个原始 67/68/69 ID、128、129**；129 在 Schema 拒绝，绕过模型验证的 Repository 入口也在 DML 前拒绝。派生键覆盖 **255、256、386、387**；旧 revision 拒绝回归保留，新 revision 成功与超长拒绝并存。
- `test_complete_score_dag_migration_fixed_consumption_restart_and_correction` 将原 `regime.state` 完整评分依赖 DAG 实际经过 **Store→Repository→数据库**，在 Store 重启后按旧固定 Bundle 消费，再发布 Correction 并再次重启消费旧/新 Bundle。三个长 ID 原样存在三表，全部 Partition 保持原键，无截断。
- Correction 改动最早受影响的合成原始值，前 60 条历史不变，后 5 个输出的平滑全部改变且状态受影响；每个新 Partition/Snapshot 为 revision 2 并 supersedes 原 revision 1。新 manifest/bundle Hash 改变，逻辑 identity、旧数据库记录、旧 Parquet 字节/Hash 和旧 Snapshot/Bundle 固定引用不变；每个旧/新 Parquet 与原/重算 rows 的确定性 bytes 一致。错误 logical identity 的 Correction 拒绝且无残留。迁移前短 ID Bundle 仍可重启固定消费。
- 完整 fixture 继续显式 `fixture_only=True`、`FIXTURE_ONLY`、**PROVISIONAL**；`certified_capabilities=()`、`missing_capabilities=(market_breadth, market_emotion)`。非隔离入口不能冒充 fixture；Formal/Paper 固定消费与 Formal 物化均拒绝，且失败不改变数据库或文件。
- 原 **14 F1、65 F2** 的 ID/版本/完整载荷/Hash 保持不变，聚合载荷 Hash 分别为 `sha256:e65941d7c70b0e490ac95526a26c2baaafb9ecdf7ce73511156b72bb3a8a1d23`、`sha256:028758764bcb833e8231027db3b9f06dd9322596a9c1c0a291d18ad2871a858b`。PREP、F2 实现和完整 fixture 源文件、Registry Definition、历史 0013、先前 0014 和原 `_partition_key` 算法未修改。

### 8.4 本次实际验证及未验证项

机器已有 Python 3.12.9，无依赖安装/升级/下载。以下套件有重叠，**计数不相加**。

| 实际命令/检查 | 最终结果及边界 |
| --- | --- |
| `python -m pytest tests/integration/platform/test_feature_indicator_id_postgres.py tests/integration/platform/test_feature_partition_key_postgres.py tests/integration/platform/test_market_sentiment_postgres.py tests/integration/platform/test_feature_store_postgres.py tests/integration/platform/test_feature_repository.py tests/integration/platform/test_postgres_foundation.py -q --tb=short -rs` | **64 passed, 1 warning，0 skipped**；真实旧→新迁移、完整评分发布/重启固定消费/Correction、安全降级/重升、危险降级拒绝、锁互斥、单连接池、真实 COMMIT 失败清理及原 Repository/Foundation 回归全部通过 |
| `python -m pytest tests/platform/test_feature_indicator_id_contract.py tests/platform/test_indicator_registry.py tests/platform/test_market_sentiment.py tests/platform/test_feature_store_contracts.py tests/platform/test_feature_partition_golden_bytes.py -q --tb=short -rs` | **130 passed, 1 warning**；F1/Registry、F2、Schema/metadata、Store、Contract/Golden |
| `python -m pytest tests/platform --ignore=tests/platform/api -q --tb=short -rs` | **685 passed, 5 skipped, 2 warnings**；5 skips 精确原因同第 4 节 Windows symlink/POSIX mode，不是 B5/PostgreSQL 验收跳过；不等于完整 API/platform suite |
| `python -m pytest tests/integration/platform/test_feature_partition_key_postgres.py -q --tb=short -k "single_connection_pool or shared_publication_transaction"` | **3 passed, 19 deselected, 1 warning**；完整 fixture 与128 ID分别在单连接池初次发布/重启固定重试/Correction/消费通过；真实延迟约束触发器使 COMMIT 失败后 schema/data/version 不变、新文件/缓存为空、连接归还，同一 Store 后续成功重试 |
| `python -m alembic heads` | 唯一 head **`0015_wp0303_partition_key`** |
| `python scripts/export_platform_contracts.py --check` | 通过；生成 JSON 当前一致，生成 Web TypeScript 无变化 |
| `python scripts/check_ai_assets.py` / `python scripts/check_visory_baseline.py` | 通过；baseline 625 相对链接、0 broken、0 imported secrets |
| `python -m py_compile @files` / `python -m flake8 --select=E9,F63,F7,F82,F401,F821 @files` | 通过；覆盖第 7.4 节文件清单加 `0015_wp0303_partition_key.py` 和 `test_feature_partition_key_postgres.py`。all gate 全仓 syntax/critical lint/export 阶段同样通过 |
| `git diff --check`、输入备份与完整 diff 审阅 | 通过；仅本授权增量，原 17 项及授权前 28 项成果均保留；没有改历史 migration、算法、生成方式或无关依赖 |
| 固定 `python3` 为现有 Python 3.12 的 `bash scripts/ci_gate.sh all`（第 4.1 节命令） | **exit 1**；code 阶段未修改的 `data_provider/efinance_fetcher.py` 缺 `tenacity`，未完成全量测试；不扩大范围修复 |
| 在 `apps/dsa-web` 执行 `npm.cmd run lint` / `npm.cmd run build` | 均 **exit 1**：无 `node_modules`，`eslint`/`tsc` 不存在；Node 16.20.2 低于 manifest `>=20.19.0 <27`。没有 npm ci/升级，客户端构建仍未验证 |

保留 RED→GREEN 证据：授权后首轮 10 failed/2 passed，其中 **9 项**为真实长度缺口，1 项为负向测试自身非法 frequency 输入，后改为允许的版本字段构造 key387；不把该非法输入当有效业务反例。实现与输入校正后定向 59 passed；强化断言后的 PostgreSQL 首轮 60 passed/1 failed 是新增非隔离拒绝的错误消息 regex 不匹配，仅修正 regex、没有放松生产门禁，该阶段 **61 passed**。最终自审发现预检与持久化使用不同 Session 会耗尽合法单连接池，新增真实回归首先 **2 failed**（QueuePool size1/overflow0 timeout）；改为预检/水合/写入同一事务，再补真实延迟触发器 COMMIT 失败回归，定向 **3 passed**，最终完整 PostgreSQL **64 passed/0 skipped**。COMMIT 错误仍由原数据库异常边界包装，未 mock SQL 或增加依赖。第 7 节原始 Store256/257 失败及本节阶段性61 passed历史、全部日志均保留。

本轮日志位于 `C:\Users\lzq11\AppData\Local\Temp`：`visory-wp0303-b5-key-red.log`、`visory-wp0303-b5-key-green-final.log`、`visory-wp0303-b5-key-postgres-final.log`、`visory-wp0303-b5-key-postgres-accepted.log`、`visory-wp0303-b5-key-targeted.log`、`visory-wp0303-b5-key-platform-core.log`、`visory-wp0303-b5-key-checks.log`、`visory-wp0303-b5-key-backend-gate.log`、`visory-wp0303-b5-key-web-lint.log`、`visory-wp0303-b5-key-web-build.log`、`visory-wp0303-b5-pool-red.log`、`visory-wp0303-b5-pool-green.log`、`visory-wp0303-b5-final-postgres.log`、`visory-wp0303-b5-final-targeted.log`、`visory-wp0303-b5-final-platform-core.log`、`visory-wp0303-b5-final-checks.log`、`visory-wp0303-b5-final-backend-gate.log`。它们是本地证据，不是远端 CI artifact。

**未验证**：全量 API/offline suite 本次未重跑，其上一轮缺依赖记录仍见第 4.1 节；完整 backend gate、客户端构建未通过；Desktop、浏览器/runtime E2E、远端当前 head 三项 CI、review/合入、覆盖率百分比、真实 Provider/历史物化、生产锁耗时/并发负载/性能/备份恢复/灾备未验证。不使用旧 CI、核心套件或 fixture 为这些缺口背书。

### 8.5 迁移、备份、锁影响与独立回滚

1. **升级计划（非本轮业务库执行授权）**：以后需单独授权明确的数据库连接及维护窗口，先核验实际 revision、确认唯一迁移链为 0013→0014→0015。备份控制面、migration version、全部固定 Partition/Snapshot/Bundle 引用清单及对应不可变文件，记录 Hash 并实际核验可恢复性；数据库与文件备份不能只做一侧。本轮只对随机临时库调用 `upgrade_database(engine, '0015_wp0303_partition_key')`，不提供生产升级承诺。
2. **锁与发布协调**：停写/暂停受影响发布者，在事务内设置操作级 `lock_timeout`/`statement_timeout` 后执行授权迁移，超时失败保持原状并独立决定是否重试。upgrade ALTER 可能等待/阻塞；downgrade 明确三表 `ACCESS EXCLUSIVE`，Store 的 `ROW EXCLUSIVE` 预检锁在同一发布事务内持有至控制面 COMMIT（固定重试的只读事务则持有至退出）；不是用第二条连接提前释放或另行写入，不能假定 varchar 扩宽零锁/零耗时。真实测试验证 downgrade 锁等待触发 SQLSTATE **55P03** 且无变更；未测生产规模锁时长。升级后复核三列128/key386、约束/索引、短数据、固定文件/Hash/引用及 revision。
3. **独立数据库降级**：`downgrade_database(engine, '0014_wp0303_indicator_id')` 或 `'0013_wp0302_feature_store'` 只在另行授权连接执行。0015 在任何 ALTER 前同时锁三表，存在 **任一 key>255 或三表任一 ID>64 就拒绝**；即使仅降到0014，也保守拒绝>64 ID，避免向0013多步降级先缩键后发现ID不兼容。0014 自身保留三表>64拒绝。无长 ID 但有长 key 仍不能缩键。
4. **拒绝不是清理指令**：不得截断/改名/删记录/删固定文件或重绑 Bundle 以促成降级。测试分别在三表独立放置65 ID并监听真实 SQL，验证**任何 ALTER 前拒绝**；另验证长key256/386拒绝、完整fixture拒绝，失败后全部 schema/data/migration version/固定文件均不变。只有三表ID均≤64且key均≤255时才允许安全降级，之后核验三列64/key255或目标0014列宽、约束/索引/数据/引用及revision；安全降到0013/0014并再次升到0015均已有真实测试。
5. **独立代码回滚**：本轮未提交，只审阅撤回相对两轮备份的本次 B5 增量，保留原17项、此前成果与后续用户修改，不整体 reset/restore。代码回滚**不自动触发数据库降级**；可保留扩宽数据库，但须先停止长ID/长key发布并评估旧版本读取/发布限制。反之，数据库降级也不能自动改代码/文件/Bundle。已有长记录时只能保留扩宽schema或另行审核完整备份恢复方案，不能破坏固定引用适配旧代码。

### 8.6 关闭项与剩余边界

- **本次已关闭**：B5 指标 ID 及其原算法派生键的持久化长度缺口、未迁移库提前拒绝/无残留、单连接发布事务及真实 COMMIT 失败清理、完整评分隔离 fixture 的真实数据库发布/重启固定消费/Correction 链、危险降级保护与短记录安全降级/再次升级。
- **剩余 BLOCKER**：B1 PIT 流通市值、B2 `shares_outstanding`、B3 PIT adjustment factor/method；B4 原 `trading_halt_state@1.0.0` 等旧 F1 引用残余及 PREP 两个基准算法的 FIXTURE_ONLY 边界。本次不修订上游或旧 F1。完整 WP/Formal/生产能力不能因 B5 关闭认证。
- **FOLLOW-UP/门禁缺口**：既有依赖导致的全量 gate/客户端构建缺口、当前未提交实现的远端 CI/review/合入、真实历史/生产运行与恢复验证，需独立授权和证据；不增加已验收 WP 计数。
- **文档同步**：仅在当前实现验收追加本节，最小同步 IMPLEMENTATION-STATUS 唯一 WP 行和 CHANGELOG；PREP 及上一轮历史保持原文。本 WP 无对应受影响英文专题，不改中英文 README。WP-0207/0304/0305、API、页面、调度、Provider 和依赖无本轮扩展。

## 9. 2026-10-08 B3 第一阶段：离线派生血缘与 Method 契约验收

### 9.1 当前结论、授权及输入保护

**WP-0303-B3-DERIVED-CONTRACT 本地契约验收完成；不关闭 B3、完整 WP 或生产能力。** 本 Goal 在既有 [B3 PREP](WP-0303-B3-ADJUSTMENT-CONTRACT-PREP.md) 后单独获授权：采用 D1/D3/D4 的保守 Method 语义，D5 仅批准必要的新契约版本，D6 仅批准显式 DERIVED 血缘、版本派发及 Hash 兼容。D2 真实来源仍 NO_GO；本轮没有完整复权算法、因子计算或因子行生产。

- 唯一工作目录 `C:\Users\lzq11\.codex\worktrees\f468\Visory`，detached HEAD；开工 HEAD、缓存 origin/main 与只读 `git ls-remote` 观察均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。不 fetch/pull 或合并远端差异，不创建分支/worktree，不 commit/tag/push/PR/merge/部署。
- 本 Goal 开工实测 **20 tracked 修改 + 11 untracked = 31 项**。PREP、第 1–8 节、B5 代码/Migration/F1/F2及固定引用是本轮输入，不计为本轮成果。开工逐文件字节与 SHA-256、旧完整载荷/导出/Golden/序列化基线保存在 `C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-b3-derived-20261008-tp5sxaae` 的 `opening.json`、`opening/`、`baseline/` 和 `compatibility-baseline.json`；生成客户端原字节也在 exporter 前备份。
- 写入 allowlist：`src/schemas/platform/adjustment.py`、`__init__.py`、`registry.py`、`snapshot.py`；专项测试、兼容性 fixture、三个新 Golden；三个新 Schema及原 registry 索引；本文件仅追加第 9 节、状态当前说明/唯一 WP 行、CHANGELOG 扁平条目。无 Repository、Service、Provider Mapping、质量规则、Resolver/F1/F2、公共 API、Migration、manifest/lockfile/依赖变更。未修改 docs/INDEX、两份 PREP及第 1–8 节。

### 9.2 已实现的契约与严格边界

| 契约/入口 | 本轮实现事实 | 不是本轮实现的能力 |
| --- | --- | --- |
| [AdjustmentMethod](../../../src/schemas/platform/adjustment.py) `method_contract_version=1.0.0` | frozen/extra-forbid、严格整数/标识/版本；普通 BONUS/DIVIDEND/SPLIT 白名单、税前 CNY/每旧股现金、无偿新增股/旧股、拆分后/前股倍数；固定前/后复权方向与 A/B、P来源、组合公式、precision38/scale18/half-even、排序/量化、PIT/revision/coverage/失败政策；`execution_status=CONTRACT_ONLY` | `algorithm_version=1.0.0` 是已批准规范标签，不是已存在算法/源码指纹；未执行 Decimal 因子/收益计算、同日组合或未知事件发现 |
| Method Hash | `method_contract_hash` 覆盖完整版本化 Method 与 `formula_digest`；后者单独覆盖数学/单位/方向/数值/PIT/coverage政策，不冒充旧 F1 formula_hash。复用现有 Hash工具，新局部 `adjustment_semantic_json_1.0.0` profile 无递归排除项，固定嵌套 content_hash；三条注册及导出元数据与实际复算profile一致，旧全局算法不改 | Method不含操作时钟或随机实例ID；改方法版本改变contract hash，改方向改变两种hash；并不承诺修改输入实例后其血缘Hash不变 |
| DerivedCanonicalPartition `partition_contract_version=2.0.0` | 显式 `provenance_kind=DERIVED`；沿用 cpart资源身份与StorageRef、revision/supersedes和平台操作时间；固定 `adjustment_factor@1.0.0` 标签、四类直接输入/Method/覆盖/真实根证据 | 仅模型标签，**未注册 adjustment_factor DatasetDefinition**；未新增 factor row schema、文件写入、质量发布者、Repository或持久化 |
| DerivedDataSnapshot `manifest_version=2.0.0` | 固定已物化分区、同一lineage/cutoff/anchor；PROVISIONAL且不能认证任何能力；两市场能力必须missing。实例manifest hash包含操作时间，content hash是固定分区引用摘要 | 不接入原Snapshot发布/消费入口，不接入FeatureStore；partition_hash/schema_hash仍由输入提供，本轮不读取源字节或生成结果字节来认证它们 |
| SnapshotInputRef / SourceRootRef / QualityEvidenceRef | 直接 pin Snapshot ID、manifest/content Hash、精确1.0.0版本、cutoff与完整旧SnapshotPartitionRef；传递实际ProviderRun/RawObject契约Hash、Raw字节Hash、Raw Schema/adapter、源时间及质量报告/Mapping/规则版本Hash | 未伪造ProviderRun或RawObject；测试全为合成元数据，不能证明真实来源、公司行动单位或Mapping语义正确 |
| `validate_adjustment_references` | 纯内存解析；核对实际对象类型、重新校验对象、防止model_copy/construct或可变旧质量字典绕过；核对ID/版本/Hash/分区/报告/根关系。SUCCEEDED Run与唯一Raw必须schema/行数/字节数一致，且started≤observed≤ingested≤finished；根available=max(ingested,finished)，published≤available≤cutoff | 不查Repository/数据库/真实数据；未加载实际Mapping定义/源行，固定报告中的Mapping Hash不等于验证其业务含义；不认证源分页结束标记的真实性 |
| Coverage / Event / Lineage | 四输入角色raw行情/公司行动/identity/calendar不可少；COMPLETE、coverage=1、显式max_available_at、无excluded；覆盖收据pin目标范围/证券Hash/cutoff/页Raw refs/结束标记/总数，发现范围含RIGHTS/OTHER，不能仅覆盖受支持类型。零事件仍须完整四输入/根/报告/收据；非空源不得静默转空事件 | 仅接受旧PROVIDER输入及dataset version1.0.0、OBSERVED_INGESTION源时间；缺披露时间/availability上界拒绝。未接入候选corporate_action2，不执行最高revision/取消/区间事件选择、证券范围内容检查或同日组件完整性算法 |
| `parse_snapshot_contract` / `parse_partition_contract` | 缺版本或1.0.0走旧PROVIDER路径；2.0.0显式走新DERIVED；未知版本拒绝；旧直接消费者拒绝新载荷。旧DataSnapshot新增非1.0.0拒绝guard，但不加字段/默认值、不改旧Hash | 原运行入口没有自动调用新解析器；不存在静默升级旧Manifest或自动接受新派生数据的兼容层 |

Lineage hash 固定的是**输入实例血缘**：它包含源契约/引用Hash，不是跨不同输入实例的纯计算结果Hash。重新物化仅改输出created/published时，Method/lineage/固定content hash可保持；实例manifest hash明确可改变。不能把测试中由fixture提供的partition_hash称为重复运行复权算法所得结果Hash。

非空公司行动来源的事件选择尚未验收：本轮只拒绝“非空源+空选择”和选择数多于源行数，并对**传入的**未知类型/重复经济事件/超范围/迟到引用拒绝。不能据此断言没有漏掉源行中的未知行动或已选最高revision；取消引用测试仅证明CANCELLED证据能被显式pin，不证明取消选择算法。未来有效处理范围外事件也需要完整选择收据，而不是放宽为无证据空选择。

### 9.3 旧版本、序列化及固定引用保护

兼容性基线 fixture 为 [adjustment-compatibility-baseline.json](../../../tests/golden/platform/adjustment-compatibility-baseline.json)，专项 `test_legacy_payload_hashes_serialized_bytes_and_fixed_references_unchanged` 实际核验：

- 原 **14 F1、65 F2 完整载荷**聚合Hash分别仍为 `sha256:e65941d7c70b0e490ac95526a26c2baaafb9ecdf7ce73511156b72bb3a8a1d23`、`sha256:028758764bcb833e8231027db3b9f06dd9322596a9c1c0a291d18ad2871a858b`；不是仅比较ID/数量。未新增/改写Definition或其消费者。
- 原 **119 Golden 文件字节**聚合Hash不变；旧CanonicalPartition、DataSnapshot、FeaturePartition、FeatureSnapshot、FeatureBundle的完整序列化字节Hash及payload Hash不变。固定引用嵌在这些完整载荷内，未补默认字段后重新发布旧Manifest。
- 既有 exporter生成三个新Schema与registry新增条目；原 **74 非registry导出**（含已有C-006/OpenAPI本地成果）原字节不变，原全部registry条目及顺序不变。生成Web TypeScript原字节不变，无新API model list或客户端字段；本Goal不要求新的客户端构建。
- 新Method/Lineage的hash seal会拒绝伪造或陈旧Hash；负向用例先重新seal外层/收据，仍因引用版本/Hash/范围/cutoff/coverage不匹配失败，避免仅证明旧Hash失效。

这些是本Goal的内存模型/Golden/旧固定对象回归，**不是新DERIVED持久化、数据库重启固定消费或Correction端到端证据**。旧Store/窗口/Correction回归运行不代表新派生链已经接入。

### 9.4 实际命令与验收证据

所有命令执行目录均为本节9.1的f468工作树，Python 3.12.9、pydantic 2.13.4、pytest 9.1.1；无依赖安装/升级/下载。下表最终套件有重叠，**79和354不能相加**。`$audit`为9.1绝对审计目录，辅助脚本只位于该临时目录。

| 实际命令原文 | 结果/退出码 | 验证范围与证据 |
| --- | --- | --- |
| `git -c http.connectTimeout=10 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 ls-remote origin refs/heads/main` | 开工及收尾均0，返回9.1同SHA；收尾remote-closing.log | 仅远端ref读取，不fetch/合并/写远端；HEAD工作树保护另以opening.json核验 |
| `python -m pytest tests/platform/test_adjustment_derived_contract.py -q --tb=short` | 初始RED exit2，`ModuleNotFoundError: No module named 'src.schemas.platform.adjustment'`；最终 **79 passed, 1 warning，exit0** | [专项测试](../../../tests/platform/test_adjustment_derived_contract.py)：Method严类型/政策/Hash/不可变、六类必需实际对象/类型、完整零事件、精确版本/Hash、cutoff/覆盖/时间、旧版本隔离及旧载荷兼容；red.log、specialized-closing.log |
| `python -m pytest tests/platform/test_adjustment_derived_contract.py -q --tb=short -k 'inconsistent_run_metadata or successful_run_completion'` | 自审RED **6 failed / 66 deselected，exit1**；修后包含于最终79通过 | Run/Raw schema/行/字节/时序及可用时间不得早于成功Run完成；source-root-red.log/source-root-green.log |
| `python -m pytest tests/platform/test_adjustment_derived_contract.py -q --tb=short -k wrong_actual_object_types` | 自审RED **6 failed / 72 deselected，exit1**；修后包含于最终79通过 | 5项原AttributeError与1项已有Snapshot拒绝但无统一类型错误；改为期望模型显式拒绝，不把第6项当绕过成功；object-type-red.log |
| `python -m pytest tests/platform/test_adjustment_derived_contract.py tests/platform/test_contract_golden_payloads.py tests/platform/test_contract_registry.py tests/platform/test_contract_schema_export.py tests/platform/test_snapshot_foundation.py tests/platform/test_snapshot_lineage_gate.py tests/platform/test_feature_store_contracts.py tests/platform/test_feature_partition_golden_bytes.py tests/platform/test_indicator_registry.py tests/platform/test_market_sentiment.py -q --tb=short -rs` | **354 passed, 1 warning，exit0，0 skipped** | 新专项+旧Contract/Registry/Golden/Schema Export/Snapshot/Store/F1/F2定向回归；targeted-closing.log，不含PostgreSQL或全量API/offline suite |
| `python -m pytest tests/platform/test_adjustment_derived_contract.py -q --tb=short -k registry_profiles` | 最终自审RED **1 failed / 78 deselected，exit1**；修后包含于最终79通过 | 注册元数据错误沿用旧递归排除profile，不能复算实际新Snapshot manifest；统一新局部profile并验证Method/嵌套输入/导出声明，hash-profile-red.log |
| `python (Join-Path $audit 'create_golden.py')` | 临时脚本首轮exit1（缺本地repo sys.path）；校正后exit0，生成三个新Golden | 只构造合成元数据，不计算因子；未安装依赖。verify_exports.py首轮错取临时摘要的不存在键`export_names`，exit1，改读固定fixture后exit0；两者是辅助脚本错误，不是产品业务RED |
| `python scripts/export_platform_contracts.py` / `python scripts/export_platform_contracts.py --check` | 均exit0 | 仅通过原exporter写Schema/索引，78导出当前一致；OpenAPI/TS不变；export-hash-profile-final.log/export-check-final.log |
| `python (Join-Path $audit 'verify_exports.py')` | exit0 | 原74导出/TS原字节及旧registry条目顺序不变；verify-exports-closing.log |
| `python -m py_compile src/schemas/platform/adjustment.py src/schemas/platform/__init__.py src/schemas/platform/registry.py src/schemas/platform/snapshot.py tests/platform/test_adjustment_derived_contract.py` | exit0 | 本Goal五个Python文件语法；syntax-final.log |
| `python -m flake8 --select=E9,F63,F7,F82,F401,F821 src/schemas/platform/adjustment.py src/schemas/platform/__init__.py src/schemas/platform/registry.py src/schemas/platform/snapshot.py tests/platform/test_adjustment_derived_contract.py` | exit0 | 同五个文件critical lint；不是全仓lint；critical-lint-final.log |
| `python (Join-Path $audit 'line_execution.py')` | exit0；同专项79通过；**407/426=95.54%** | stdlib sys.settrace+CPython dis，仅新adjustment.py可执行行；不是branch/全仓/coverage.py报告。coverage包不可用，未安装；line-execution.json/line-execution-closing.log |
| `python scripts/check_ai_assets.py` / `python scripts/check_visory_baseline.py` | 均exit0 | 治理/外部源码边界/许可证/启用workflow/相对链接；0 broken/0 imported secrets；最终明细以baseline-final.log为准 |
| `git diff --check` / `python (Join-Path $audit 'final_audit.py')` | 均exit0 | 全tracked whitespace检查，加新文件空白/JSON/目标文档链接与锚点、增量allowlist、开工原字节保护、完整增量diff审阅及独立rollback patch；diff-check-final.log/final-audit.log |

阶段性fixture修正记录保留，不并入有效业务RED：green-first.log为类型化/JSON混合构造旧manifest、green-second.log为源披露晚于摄取、green-third.log为旧Snapshot未published、green-fourth.log为消息regex、green-contract.log为显式空Hash输入。它们没有放松生产门禁。后续green-pre-export.log的66、source-root-green.log的72和第一次347回归及最终HashProfile收敛前的78/353是中间证据，不冒充最终79/354结果。唯一warning为既有Starlette/httpx弃用提示，本轮未升级或消除。

### 9.5 剩余事项与下一阶段启动条件

- **本Goal BLOCKER：无**（必要离线契约与兼容性门禁完成）；**完整B3实施 BLOCKER：仍存在**。真实Provider业务语义/全类型与分页覆盖/历史availability为D2 NO_GO；corporate_action2及factor Dataset/row schema尚未注册，旧v1质量日期问题仍未修改；Method算法/最高已知revision/取消/同日组件/价格P/因子精度、持久化发布、Resolver精确版本、F1/F2接入及Correction传播均未实现或未验收。
- **FOLLOW-UP**：下一Goal需明确批准上述最小实施范围和实际新Dataset/消费者版本；提供脱敏离线字段/单位/基数/税/身份/修订/取消/分页与时间证据。需要在线Provider、数据库、真实数据或公共API时必须另行授权，不能从本契约Goal推出；B4及其他WP不得顺带推进。若下一Goal仅继续离线模型/算法，可作CONDITIONAL_GO，但须先批准输入语义、事件选择收据及固定范围；当前**真实来源实施NO_GO**。
- **未验证**：新DERIVED算法/结果字节/存储/Repository/重启消费/完整Correction E2E、真实Mapping/源行/证券范围与结束标记、线上PIT历史、数据库/Provider/真实/data、全量API/offline gate、branch覆盖、Web/Desktop/runtime E2E、远端当前变更CI/review/合入/发布/生产恢复。前第8节依赖/Node/gate失败属于**历史证据，本Goal未重跑**；本次未用354定向通过为这些缺口背书。
- B1/B2/B4、WP-0207/0304/0305无本轮变更。WP-0303 **IN_PROGRESS**、**15/45**；`market_breadth/market_emotion`仍missing、Formal/Paper继续拒绝，生产 **NOT CERTIFIED、RELEASED=false**。本地契约Goal完成不标完整WP VERIFIED或RELEASED。

### 9.6 兼容性、风险与仅撤销本Goal增量

没有新增算法执行/API/配置/数据写入/调度/依赖或发布路径；新增模型仅在离线校验/注册导出中使用。**唯一旧入口行为收紧**是DataSnapshot对未知/非1.0.0 manifest显式拒绝；已支持旧1.0.0字段、序列化和Hash保持原样，不声称所有非法旧输入行为完全不变。源契约被固定不等于Provider历史语义已认证，PROVISIONAL收据不能绕过Formal/Paper。

回滚不执行reset/stash/clean/整文件restore，不触碰已有固定文件/控制面/Bundle。审计目录的 `goal-increment.patch`仅含相对**本Goal开工字节**的7个既有文件增量，新文件清单含9项并带本Goal最终SHA-256；`delta-final/`保留本轮最终文件。以后撤销前重新比较清单Hash及工作区，存在后续修改则逐hunk人工反向合并，不能覆盖它们；无后续变更时也先 `git apply --reverse --check`该增量patch，再经用户授权应用，仅删除确认本Goal创建且未发生后续变化的9个文件。尤其WP-0303-IMPLEMENTATION原第1–8节、两份PREP、B5/Migration、原20 tracked+11 untracked成果和旧generated成果必须保留。无需数据库降级、重绑引用或重发旧Snapshot。回滚说明不是本轮执行删除/回滚的授权。

仅追加本节、状态当前说明和CHANGELOG；受影响WP没有对应英文专题，本轮无API/首页变更，不改中英文README。


## 10. 2026-10-09 B3 第二阶段：受限离线复权因子算法验收

**`WP-0303-B3-OFFLINE-FACTOR-ALGORITHM` 完成合成输入、事件选择、Decimal 计算、实际结果字节与 Hash 的本地验收；不是 B3 关闭、正式派生发布或真实 PIT 来源认证。** 本节为当前 B3 算法层结论，第 1–9 节保持历史原文；上一阶段 Method/DERIVED 契约不被改写为生产可执行能力。

### 10.1 授权、开工及保护

- 本 Goal 的完整授权来自本聊天持久化目标指定的 `goal-objective.md`：批准 PREP D1/D3/D4 **仅在合成 fixture 范围**实现；不批准真实 Provider、生产 Dataset/公共 API、数据库/Migration/发布、Resolver/F1/F2 或 FeatureStore 接入。不复写 PREP，也不推进 B1/B2/B4 或其他 WP。
- 唯一工作目录为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`；开工 detached HEAD、缓存 origin/main 和只读实时远端 main 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。实测 **24 tracked 修改 + 20 untracked = 44 项**，全部视为本轮输入，不计入本 Goal 成果。
- 开工 status、44 项原字节副本、1554 个既有文件 SHA-256、allowlist 和完整授权副本保存在仓库外 `C:\Users\lzq11\AppData\Local\Temp\visory-wp0303-b3-offline-20261009-2x4bbitp`。`opening/` 是本 Goal 开工字节，不是 HEAD 的干净版本。未 pull/fetch、切分支、reset/stash/clean 或覆盖历史文件。
- 增量只有：两个内部 Python 模块、专项测试、一个新 Golden，以及本记录/IMPLEMENTATION-STATUS/CHANGELOG 三个已有文件的最小增量。没有修改旧 adjustment.py、注册/导出/客户端、119 个旧 Golden、兼容性基线、14 F1/65 F2、0013/0014/0015 或任何开工代码。

### 10.2 实际实现与受限契约

| 实现 | 实际行为和证据 | 不代表的能力 |
| --- | --- | --- |
| [内部输入与收据类型](../../../src/schemas/platform/adjustment_calculation.py) | `FixtureAdjustmentInput`、price/action/calendar/identity/group/coverage 类型复用 frozen/extra-forbid 基类，明确 FIXTURE_ONLY；无生产 Dataset/API 注册。数量为十进制字符串/Decimal，不接受 float、整数隐式单位、指数文本、NaN/Infinity；quantity 与 share_denominator 明确，Null 不补零 | 不等于 Provider Raw Schema/Mapping 认证，不是 corporate_action@1 或候选 @2 的升级载荷 |
| [实际字节入口](../../../src/services/platform/adjustment_calculation.py) `calculate_fixture` | 只接收 UTF-8 JSON bytes；直接计算 raw_input_hash，拒绝重复 JSON 键、非有限及 float token；从实际内容另计算 input_semantic/action/price/identity/calendar/group/coverage Hash，而非相信传入摘要 | 不读取真实 Provider、数据库、真实 /data，不制造 RawObject/ProviderRun 或正式 Snapshot |
| `_validate_input/_select` | 固定证券 B/A/C；每个日历 session 在 [B,A] 的证券×日期价格网格完整且唯一，身份 CONFIRMED 覆盖区间；实际行情 source_published 的 UTC 日期不能早于 trade_date。全部行和收据 published≤available≤cutoff，哪怕将来生效、被替代或最终取消也不先过滤污染 | CONFIRMED/COMPLETE 是合成事实断言，不是真实历史来源的独立证明；不支持停牌填充/跳 session 或省略缺失证券 |
| 全 revision 选择收据 | 合成规则明确：每事件 revision 从 1 开始连续且唯一，available 严格递增、source_published 不下降，group/role/type 身份不漂移；每个输入 revision 固定行 Hash、最高 revision/行 Hash及 SELECTED/SUPERSEDED/CANCELLED/OUT_OF_RANGE 去向。未知或特殊类型连被替代/范围外行也拒绝 | 不将此严格合成序号规则套到真实 Provider，不放宽旧 SnapshotInputRef/AdjustmentLineage 的版本和非空源校验 |
| `_group_events/_calculate_events` | 仅普通现金、无偿 BONUS、纯 SPLIT、同组共同旧股基数现金+BONUS；完整独立 group roster 必须匹配实际选中组件，重复角色/多方案同日/现金+SPLIT/多个 SPLIT 拒绝；同组现金/bonus先求和，Q=(P−sum D)/(1+sum b)，不是各现金 q 独立累乘 | 不支持 RIGHTS、重整/特殊公式、反向拆分、含糊主备/方案；未知不以 factor=1 或 Provider 因子兜底 |
| Decimal 数学和端点 | P 唯一取固定 calendar 前一 session 的真实 raw close 行，保留日期/行 Hash，不用当日 prev_close。precision=38、HALF_EVEN，转换、除法、求和及排序连乘在固定 context 内；仅输出 factor 量化 18 位，拒绝 Q/q非正、溢出、量化零，后复权大于 1 合法。F(t,A)=product(q;t<ex≤A)，H(B)=1；H(t)=product(1/q;B<ex≤t) | 不是 total return、成交/分红账本或正式收益 F1；辅助调整 close/收益只在测试同价基验算 |
| 零行动与结果 | COMPLETE 覆盖固定证券、区间、cutoff、源行总数、完整类型发现和结束标记；空来源或完整收据证明最高版本全部取消/范围外，才产生 NO_ACTION。独立 FixtureFactorResult 固定 MethodRef、B/A/C、规范输入/选择 Hash、完整行，规范 JSON 字节直接生成 content_hash | 不构造正式 DERIVED Partition/Snapshot；不依赖虚填 partition_hash，不发布或认证能力 |
| 执行审计与源码指纹 | 另记原 JSON 字节 Hash、fixture instance、操作时钟、全选择/计算收据；固定 5 个实际源码文件字节 Hash（base、hashing、adjustment、两个本轮模块）、聚合 digest 及实际 Python/libmpdec/pydantic 版本。模块加载时固定指纹，执行时磁盘源码变化拒绝；`verify_fixture_execution` 从实际字节重算，外层重新 seal 的伪因子仍拒绝 | 版本字符串不是源码 Hash，也不是签名/可信构建证明；源码变化后旧收据不能冒充当前实现重验成功 |

旧 `AdjustmentMethod@1.0.0` 的载荷、Golden、Hash和 **CONTRACT_ONLY** 不变；离线执行能力只归于新的 `offline_fixture_factor_1.0.0` 收据，不改变 Method 的原执行状态。内部执行只批准该 Method 版本；任意版本标签不能解锁。

规范 input/result Hash归一数值表示、时区和行集顺序，不包含 fixture_instance_id、原字节表示或操作时钟；执行收据保留这些差异。**同一固定字节重复执行**内容字节/Hash相同，`1.0/1.00`、行集重排及同一时刻的时区表示不改变规范结果；原字节/实例/操作时钟变化不承诺 execution_hash 相同。cutoff、anchor、语义输入或 Method变化不能保持旧语义 Hash别名。

### 10.3 三任务与 PREP 案例的当前证据

专项 [test_adjustment_calculation.py](../../../tests/platform/test_adjustment_calculation.py) 的案例均已在本 Goal 实际运行；[factor-results.json](../../../tests/golden/platform/adjustment-calculation/factor-results.json) 包含 6 个手算情景×2 个方向的 12 个规范结果及字节 Hash。生成 Golden 前逐个对照独立手算向量；不是用生成字节替代数值断言。

| 要求/案例 | 测试与具体期望 | 证明边界 |
| --- | --- | --- |
| 任务1 / N01/N02 | `incomplete_zero_action_coverage`、`full_positive_coverage_binding`、`future_revision`、`all_input_availability`、`selected_highest_revision_and_cancelled_history`：缺收据/类型发现/结束标记、区间/范围/总数/cutoff不符拒绝；两行revision完整地归入替代/选中或取消，非空合法取消可全1 | 完整审计实际 fixture 行，不认证真实来源分页/历史可用性 |
| 任务2 / A01–A05 | 无行动 F/H全1；现金 P=10,D=1，q=.9；现金+bonus b=.5，q=.6；拆分s=2，q=.5；现金后再拆分 F=[.45,.5,1]、H=[1,1.111111111111111111,2.222222222222222222] | 38位运算/18位输出的实际字节与数学手算双重验证；含单独 BONUS 情景 |
| A03/A06 | 显式每10股 quantity=10/denominator=10 转D=1，5/10转b=.5；同日两个D=1组件一次组合q=.8，而不是.81，重复组件拒绝 | 只批准合成单位口径，不推断真实 ratio/cash 字段 |
| A07/A08 | B当日与 ex>A 的行动有 OUT_OF_RANGE 收据，不产生跳变；普通 record_date<ex被接受，P固定前一实际session，而非当日参考价 | A08只证明内部日期规则；旧 corporate_action@1 质量规则和生产 @2 未改/未注册 |
| N03/N04/N05/N06 | 重复/缺失组件、同日多方案、现金+SPLIT、未知/RIGHTS/重整、非法数量/基数、D≥P、停牌/缺行/重复日期/身份/非session、极小因子量化零/大因子溢出拒绝；合法H>1、HALF_EVEN边界通过 | 不过滤不支持事件，不zip缩短或降级因子为1 |
| 任务3 / N07/N08 | 实际源字节 SHA-256、源码文件逐个复算、重复执行/等值Decimal/重排行集/时区及外部 Decimal context；伪Method Hash/未支持版本拒绝，结果/执行收据重新seal也需实际重算一致 | 内容Hash与实例/操作收据Hash分开；不是“所有Hash均不变” |
| C01/C02/C03 | 原D=1在C0：Fpre=.9；新D=2在C1：Fpre=.8、辅助收益9/8−1=.125。前复权只变早于ex的因子，后复权只变ex及之后；取消新revision使C1全1，C0输入/字节/Hash不变；同cutoff已知修订也使用新固定fixture而不变旧输入 | 仅离线重述和方向影响区间；没有生产 Correction/supersedes 发布或完整下游传播 |
| C04–C06 / 旧兼容性 | 本轮重跑旧派生契约、Snapshot/Store/F1/F2及Golden/Registry/Export回归；旧兼容基线不改，原14 F1/65 F2完整payload/Hash、119旧Golden、旧固定Partition/Snapshot/Bundle序列化/引用与生成客户端字节通过保护断言 | 旧Store Correction回归不是新DERIVED发布/重启消费/完整Correction E2E证据，C04–C06新链路仍未验收 |

### 10.4 实际命令、RED和最终验证

执行目录均为10.1的f468；Python **3.12.9**、pytest **9.1.1**、pydantic **2.13.4**。下面套件重叠，**专项89、既有派生79和联合458不得相加**。`$audit` 表示10.1的绝对临时目录，辅助脚本和日志不纳入仓库。

| 命令原文 | 实际结果/退出码 | 验证范围/日志 |
| --- | --- | --- |
| `git status --porcelain=v1 --untracked-files=all`、`git rev-parse HEAD`、`git rev-parse origin/main`、`git branch --show-current` | 开工0，24 tracked/20 untracked，detached；相同10.1基线 | 工作树保护，不改refs |
| `git -c http.connectTimeout=10 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 ls-remote origin refs/heads/main` | 开工和收尾均exit0，同10.1 SHA；收尾HEAD/cache相同、差异0/0且仍detached | 只读远端，不fetch/pull/自动合并；remote-closing.log/json |
| `python -m pytest tests/platform/test_adjustment_calculation.py -q --tb=short -k 'future_revision or incomplete_zero or duplicate_component or two_cash'` | 初始RED exit1，**5 failed/74 deselected**，缺本轮待实现模块 | 测试成功收集并执行，缺实现RED，不是依赖缺失；red.log |
| `python -m pytest tests/platform/test_adjustment_calculation.py -q --tb=short -k 'raw_close_cannot or method_version_is_not'` | 自审业务RED exit1，**2 failed/79 deselected**，均 DID NOT RAISE | 增加实际行情日期与受支持Method版本拒绝；self-review-red.log |
| `python -m pytest tests/platform/test_adjustment_calculation.py -q --tb=short -k source_fingerprint_cannot` | 自审业务RED exit1，**1 failed/81 deselected**，DID NOT RAISE | 不允许缓存执行代码为改后的磁盘源码背书；source-binding-red.log |
| `python (Join-Path $audit 'create_golden.py')` | exit0，12个手算向量一致后写唯一新Golden | 新Golden一次创建，不修改旧基线 |
| `python -m pytest tests/platform/test_adjustment_calculation.py -q --tb=short` | 最终 **89 passed/0 skipped，exit0** | specialized-final.log；中间82通过不是最终范围 |
| `python -m pytest tests/platform/test_adjustment_derived_contract.py -q --tb=short` | **79 passed/0 skipped，exit0** | derived-final.log，保留旧CONTRACT_ONLY/Hash/固定引用 |
| `python -m pytest tests/platform/test_adjustment_calculation.py tests/platform/test_adjustment_derived_contract.py tests/platform/test_contract_golden_payloads.py tests/platform/test_contract_registry.py tests/platform/test_contract_schema_export.py tests/platform/test_snapshot_foundation.py tests/platform/test_snapshot_lineage_gate.py tests/platform/test_feature_store_contracts.py tests/platform/test_feature_partition_golden_bytes.py tests/platform/test_indicator_registry.py tests/platform/test_market_sentiment.py tests/platform/test_hashing.py tests/platform/test_extended_canonical.py -q --tb=short -rs` | **458 passed/0 skipped，exit0** | targeted-first.log；无PostgreSQL、完整API/offline gate或真实Provider |
| `python scripts/export_platform_contracts.py --check` | exit0，导出与生成TypeScript当前一致 | export-check-final.log；未运行写入exporter |
| `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | 均exit0；治理OK、645个相对链接、broken links=0/imported secrets=0 | ai-assets-final.log、baseline-final.log；不安装依赖 |
| `python -m py_compile src/schemas/platform/adjustment_calculation.py src/services/platform/adjustment_calculation.py tests/platform/test_adjustment_calculation.py` | exit0 | compile-final.log，仅本轮Python |
| `python -m flake8 --select=E9,F63,F7,F82,F401,F821 src/schemas/platform/adjustment_calculation.py src/services/platform/adjustment_calculation.py tests/platform/test_adjustment_calculation.py` | exit0 | critical-lint-final.log，不宣称全仓lint |
| `python (Join-Path $audit 'line_execution.py')` | exit0，同专项89通过；schema **245/252=97.22%**、service **247/257=96.11%** | stdlib sys.settrace/dis 可执行行命中，仅两个新模块；不是分支/全仓/coverage.py证据；line-execution-final.log/json |
| `git diff --check`、`python (Join-Path $audit 'final_audit.py')` | 均exit0；3个已有文档增量、4个新增文件；1551个其他既有文件Hash相同、46个本地链接/锚点检查通过 | diff-check-final.log、final-audit.log/goal-delta.json；全tracked空白、新文件空白/JSON、allowlist、原字节保护及仅增量patch审阅 |
| `git apply --reverse --check (Join-Path $audit 'goal-increment.patch')` | exit0，未实际应用 | rollback-check-final.log；仅校验3个既有文档增量patch可逆，不删除新文件 |

辅助错误分开记录：specialized-second.log 的 **88 passed/1 failed，exit1** 是新测试重新seal收据时错误显式传空Digest，已改为删除该字段触发seal；不是产品逻辑RED，也未放宽模型。首次行命中脚本在每次trace中解析磁盘绝对路径，耗时过高，仅终止本轮自建helper；优化临时脚本后重跑得到上表证据，不计首轮为通过。读取pytest.ini探测不存在，实际pytest配置为setup.cfg；未改配置。首次final_audit误将开工Hash采集时排除的两份references文件计为新文件，exit1；修正相同排除范围并核对完整dirty路径集合后通过（未改references）。随后加强原字节重构检查检出CHANGELOG/状态文件被转换为CRLF，byte-audit.log为exit1；恢复其开工LF后，移除本轮增量可精确还原原字节。首次反向patch检查exit1，原因是临时patch写出时被转换为CRLF；改为保留原始字节差异后检查exit0，未执行回滚。这些辅助检查失败与修正均保留日志，不计为产品业务RED。唯一warning为既有Starlette/httpx弃用提示，未安装/升级依赖或修无关历史问题。

收尾严格保护审计：开工44项中，41项原字节完全不变，3项授权文档只保留本轮增量；实施记录第1–9节保持完整原字节前缀，CHANGELOG删除唯一新条目、状态移除新摘要并还原唯一WP行后均精确等于开工字节（包含换行）。最终工作树仍24 tracked修改，untracked从20增至24；增加的4个路径全部在allowlist，无其他新增dirty路径。45条WP的计数仍为15 VERIFIED / 2 IN_PROGRESS / 28 NOT_STARTED / 0 RELEASED；WP-0303仍IN_PROGRESS。

### 10.5 兼容性、剩余事项与下一阶段

- **本 Goal BLOCKER：无**，受限离线计算及本地兼容性验收完成。**完整B3仍有BLOCKER**：D2真实Provider字段/单位/基数/税/修订取消/分页/历史availability证据、新Dataset及生产Mapping/质量/Resolver精确版本、F1/F2消费、正式派生物化/Repository/重启固定消费及完整Correction传播尚未完成。
- **FOLLOW-UP / 新授权**：下一阶段先明确真实输入证据与D5/D6的生产接入边界；内部fixture不能充当corporate_action2注册、市场覆盖或Formal认证。数据库/持久化/消费者/API/线上核验各须明确授权，B4/其他WP不得顺带推进。当前真实来源及正式市场链路仍 **NO_GO**。
- **未验证**：真实Provider/业务DB/真实/data、新DERIVED Partition/Snapshot发布/重启/Correction E2E、下游MA与F2传播、全量API/offline gate、Web/Desktop构建/E2E、branch coverage、远端本变更CI/review/合入/部署/生产恢复。前8/9节历史环境或CI数据不作为本轮新证据。
- 本轮不改变现有应用运行路径：没有导出/注册新的公开模型、调用方、配置/依赖/数据库/Migration/发布变更；新增执行入口只在内部离线调用和测试中使用。旧14 F1/65 F2聚合Hash仍分别为 `sha256:e65941d7c70b0e490ac95526a26c2baaafb9ecdf7ce73511156b72bb3a8a1d23` / `sha256:028758764bcb833e8231027db3b9f06dd9322596a9c1c0a291d18ad2871a858b`，兼容性基线原字节保留。
- WP-0303仍 **IN_PROGRESS、15/45**，两市场能力missing，Formal/Paper继续拒绝；生产 **NOT CERTIFIED、RELEASED=false**。本 Goal完成不等于B3关闭或完整WP VERIFIED。

### 10.6 仅本 Goal 增量的撤销方案

本轮未执行回滚。审计目录保存开工SHA、最终SHA、3个既有文档的 `goal-increment.patch`、4个新文件清单及最终副本。以后撤销必须先对照当前文件与最终SHA；已有后续修改时逐hunk人工反向合并，不能整文件恢复开工副本。无后续修改也先对增量patch执行 `git apply --reverse --check`，取得单独授权后才反向应用；只删除确认为本轮新建且未被后续修改的两个模块/专项/新Golden。保留实现记录1–9节、两份PREP、全部开工44项、B5 Migration和旧Golden/生成契约/固定引用，不用reset/clean/stash/整文件覆盖。没有数据库变更，不需要降级或重发Snapshot。

受影响专题没有对应英文副本；无首页/API变更，不更新中英文README。交接层级：**受限离线复权算法与固定fixture字节已验收；真实来源、生产接入及端到端B3仍待新证据和明确授权。**

## 12. 2026-10-11 B3 N2：版本化执行收据到 DERIVED 血缘桥接

### 12.1 范围与实现

本轮仅完成 `WP-0303-B3-VERSIONED-EXECUTION-RECEIPT-BRIDGE` 的 fixture-only 子目标，不关闭 B3 或 WP-0303。新增 `FixtureExecutionLineageBridge@1.0.0`，由已验证的 `FixtureExecutionReceipt`/`FixtureFactorResult` 绑定现有 `AdjustmentLineage`、`AdjustmentCoverageReceipt`、质量证据和选中事件引用；不注册生产 Dataset、Provider、API、FeatureStore、Repository 或公开 OpenAPI。

- `calculate_fixture()` 显式区分 `TRUE_NO_ACTION`、`SELECTED_ACTIONS`、`ALL_CANCELLED`、`ALL_OUT_OF_RANGE` 和 `PARTIAL_SELECTION`；receipt 保存结果内容 Hash 与实际 `result.result_bytes()` Hash。
- `bridge_fixture_execution()` 先从真实输入字节重算执行，再要求七类 graph 根（lineage、methods、snapshots、partitions、provider_runs、raw_objects、quality_reports）齐全并通过既有 `validate_adjustment_references()`。
- 桥接绑定 Method contract/formula/algorithm/implementation 指纹、raw/semantic input Hash、selection/coverage/quality、cutoff/availability/materialization 和结果 Hash；非空取消、全范围外、部分选择、缺图、未来时钟和不一致引用 fail-closed。
- `verify_fixture_execution_bridge()` 重新 model validate、重新执行 fixture、重新构造 bridge 并做完整对象比较，不能通过重新 seal 隐藏篡改。
- `bridge_lineage_hash` 只表达版本化执行与输入/选择/覆盖/质量/结果语义证据；`materialized_at` 不改变该 lineage identity，但会进入 `bridge_hash`。既有 `AdjustmentMethod@1.0.0`、DERIVED contract、F1/F2 payload/hash 和固定 Golden 未注册或改写。

### 12.2 本轮验证

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest tests/platform/test_adjustment_calculation.py tests/platform/test_adjustment_derived_contract.py -q --tb=short` | **195 passed, 1 warning, exit 0** |
| 受影响 Contract/Golden/Registry/Schema/Snapshot/Feature/Indicator/Market/Hash/Canonical 回归套件 | **301 passed, 1 warning, exit 0** |
| `python -m py_compile src/schemas/platform/adjustment_calculation.py src/services/platform/adjustment_calculation.py tests/platform/test_adjustment_calculation.py tests/platform/test_adjustment_derived_contract.py` | exit 0 |
| `python scripts/export_platform_contracts.py --check` | exit 0；生成 Contract 与前端类型无漂移 |
| `git diff --check` | exit 0 |

完整 `scripts/ci_gate.sh`、真实 PostgreSQL/Provider/`/data`、远端 CI、部署、调度和生产恢复未在本轮执行；本轮证据仅为本地 fixture 与内存 graph 验证。

### 12.3 状态与回滚

N2 技术切片可在当前隔离工作树本地复现，但 `WP-0303` 仍保持 **IN_PROGRESS、15/45**；`market_breadth`/`market_emotion` 继续 missing，Formal/Paper 继续拒绝，生产 **NOT CERTIFIED、RELEASED=false**。本轮不创建 commit、tag、branch、PR，不 push、merge、部署或写生产资源。

回滚只能按本轮开工证据目录 `C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-N2-versioned-receipt-20261011` 保存的 opening 状态和本轮对应 hunk 逐文件人工反向合并；先核对后续修改，不得 `reset`、`clean`、`stash`、整文件恢复或覆盖累计 B3/N1/B5 dirty 成果。


## 11. 2026-10-09 B3 N1：Dataset Catalog 精确版本查找验收

### 11.1 结论、实现与边界

**`WP-0303-B3-CATALOG-EXACT-VERSION` 技术切片完成；只完成 [SOURCE-EVIDENCE-PREP](WP-0303-B3-SOURCE-EVIDENCE-PREP.md) 的 N1，不关闭 D2、B3、WP-0303 或生产门禁。**

- 内部 Dataset Catalog 身份收敛为精确 `(dataset_id, schema_version)`；查询必须同时提供两个值，不提供 latest、最大版本、插入顺序或 `1.0.0` fallback。同一 Dataset 的 `1.0.0` 与隔离测试 `2.0.0` 可并存，相同精确键重复时以 `INDICATOR_CATALOG_DRIFT` fail-closed。
- `validate_dataset_projection()`、`validate_definition_inputs()` 与 `FeatureDependencyResolver` 的输入、投影和 capability 收集均使用输入引用中的精确版本；未知版本从查找入口以 `INDICATOR_UNREGISTERED_INPUT` 拒绝，错误 details 保留 `dataset_id` 与 `schema_version`。字段、frequency、domain、PIT 或 capability 投影漂移仍拒绝。
- `market_sentiment` 的直接 Catalog 查询及内部 `DatasetInputRef` 显式使用 `1.0.0`。旧显式 `1.0.0` Definition、Definition Hash、Plan Hash、固定 Golden 及 Partition/Snapshot/Bundle 引用保持不变。
- 未修改公共 `DatasetInputRef` Schema、生产 `DatasetDefinition`/Registry/Capability、Migration、Provider、数据库、Adjustment Method、DERIVED Lineage、计划规范化或任一身份/Hash 算法；没有新增依赖或生成契约差异。

### 11.2 实际验证与环境缺口

| 命令 | 实际结果与证明范围 |
| --- | --- |
| `python -m pytest -q tests/platform/test_indicator_registry.py tests/platform/test_market_sentiment.py` | 旧实现 RED：**13 failed / 64 passed，exit 1**；最终 GREEN：**77 passed，exit 0**。覆盖多版本共存、强制版本参数、精确选择、未知版本、重复键、六类投影漂移、旧 `1.0.0` Hash/required-fields 与 market sentiment 直接调用方 |
| `python -m pytest -q tests/platform/test_indicator_registry.py tests/platform/test_market_sentiment.py tests/platform/test_feature_store_contracts.py tests/platform/test_provider_registry_contract_hardening.py tests/platform/test_feature_partition_golden_bytes.py` | **126 passed，exit 0**；覆盖 FeatureStore 合同、Provider Registry hardening 与固定 Partition Golden |
| `python -m pytest -q -m "not network" tests/platform` | **exit 2**；3 个 API 文件收集时因当前 Python 缺 `markdown2` 中止，未把该命令记为通过 |
| 上述平台命令排除 3 个同源 API import blocker | **886 passed / 5 skipped，exit 0**；只作为其余平台离线回归，不能替代原始完整命令 |
| `python scripts/export_platform_contracts.py --check`、`python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | 均 **exit 0**；生成契约当前一致，治理和基线检查通过 |
| `python -m py_compile` 本 Goal 4 个 Python/测试文件 | **exit 0** |
| `python -m flake8` 本 Goal 4 个文件 | **exit 1**；3 个错误在 opening 备份中逐项相同，属于既有 F841/E303，不是本 Goal 新增；未修改无关历史代码 |
| `bash scripts/ci_gate.sh` 及 Git Bash 对齐 Python 3.12 的重试 | 完整 gate 未通过：默认 WSL bash 不可用；Git Bash 默认 Python 3.14 缺 `pandas`；一次性 shim 对齐 Python 3.12 后 syntax、critical flake8 与 export 通过，但 `scripts/test.sh code` 因既有环境缺 `tenacity` 中止，未执行完整 offline suite |
| `git diff --check`（文档写入前） | **exit 0**；收尾后再次执行并单独记录 |

验证均在固定 `f468` 工作树执行，未安装、升级或下载依赖。完整输出、退出码、opening 49 项字节备份与逐文件 Hash 位于仓库外临时证据目录 `Visory-WP0303-B3-catalog-exact-version-20261009-121038`。

### 11.3 当前状态、剩余事项与撤销边界

- N1 完成不改变 D2 真实来源证据 `NO_GO`；N2、N3、N4、生产 Dataset/Mapping/质量、真实 Provider/PIT 历史、F1/F2 正式接入、持久化和完整 Correction 传播均未完成，不描述为本轮成果。
- B3 仍未关闭；WP-0303 保持 **`IN_PROGRESS`、15/45**；`market_breadth/market_emotion` 继续 missing，Formal/Paper 继续拒绝；生产保持 **`NOT CERTIFIED`、`RELEASED=false`**。
- 本轮未创建或切换 branch，未 commit/tag/push/PR/merge，未访问真实数据库或 Provider，未部署或发布。
- 撤销时只能反向合并本节及四个代码/测试文件相对 opening 字节的对应 hunk；不得 `reset/restore/stash/clean`，不得整文件覆盖累计 WP-0303 成果。若文件已有后续编辑，先核对 opening/final Hash，再人工逐 hunk 反向合并。

## 13. 2026-10-13 FULL-INPUT-TO-FEATURE-CLOSEOUT：部分推进与阻断

### 13.1 当前结论与开工保护

**本 Goal 为 PARTIAL，完整真实输入与正式派生链路 NO_GO；WP-0303 仍 IN_PROGRESS、15/45，NOT CERTIFIED、RELEASED=false。** 本次只闭合 B4 的停牌 F1 新版字段引用，并补充独立进程的技术消费验收；没有关闭 B1、B2、B3 或 B4 全部残余。未以缺证据的候选字段注册生产 Dataset/Raw Schema/Mapping/质量或提升市场能力。

- 唯一累计工作目录：`C:\Users\lzq11\.codex\worktrees\f468\Visory`；detached HEAD，`efe8e9b362cba13eca183c55be57bbbbc832b60b`。
- 开工只读 `git ls-remote origin refs/heads/main` exit 0，实时 main 为同一 SHA；缓存 `origin/main` 亦为此 SHA。未 fetch/pull、移动 refs、切换分支或修改主 checkout。
- 开工 **24 tracked modified + 25 untracked = 49 项既有成果**，全数保存原始字节、SHA256、status、index/working/HEAD binary diff；另保存 1561 个 Git 可见既有文件 Hash，不能把 opening dirty 字节当作 HEAD。
- 仓库外证据目录：`C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-FULL-CLOSEOUT-20261013-174930`。`opening-inventory.json`、`opening-files/`、`all-opening-hashes.json`、`steps.json` 与逐命令 JSON/log 是开工及执行证据；增量 patch 和收尾保护核验也保存在该目录。
- 按输入契约、派生发布、消费验证、综合验收四步推进。输入证据未满足的正式派生步骤不启动；B5/N1/N2 仅复用及回归，不重做，不改变 FixtureExecutionLineageBridge 的名称、模式或证明等级。

### 13.2 输入矩阵与必须补充的证据

本次未收到新的真实脱敏样本/归档包。核对范围为开工成果、现有 Dataset/Raw/Mapping/质量声明、PREP/SOURCE-EVIDENCE-PREP、相关测试/Golden 及 `references/manifest.yaml`；不声称审计了用户机器上所有外部归档。参考源码版本仅为既有历史快照：a-stock-data `f90d67853b8108f13d286e1df20b357e2c5198a9`，Financial-API `2ec779c94e798ea941befb2d1c951c9420fdadd0`；2026-10-09 公开材料的部分语义结论是历史审核，本轮未重新访问 Provider 文档或业务接口，不能作为当前接口/真实响应认证。

| 项目 | 本次可核验事实与判定 | 继续推进的具体材料/决策 |
| --- | --- | --- |
| B1 PIT 流通市值 | 当前八个 Dataset 无该输入，也无对应 Raw/Mapping/质量；**NO_GO，未关闭** | 明确 A 股可流通市值与 free-float-adjusted 市值的口径差异；固定源版本、单位/股本及同价基、历史身份、范围/退市覆盖、修订与真实可用时间；真实跨 cutoff 脱敏样本及完整 Manifest。未经确认不自行采用股本乘价格的派生替代 |
| B2 换手率股本 | security_master@1.0.0 无 shares_outstanding；旧 turnover_ratio@1.0.0 继续拒绝；**NO_GO，未关闭** | 明确换手率分母是何种可交易/流通股本，不能用总股本；提供股本生效及可用时间、单位、公司行动引起变化、身份/覆盖/修订、源版本与真实样本。不得向旧 security_master 虚填字段 |
| B3 公司行动/因子 | corporate_action@1.0.0 仅泛化 ratio/cash_amount；DERIVED 模型标签不是正式 factor Dataset。已完成 Method/算法/N2 仍为契约或 FIXTURE_ONLY；**NO_GO，未关闭** | 补齐税前旧股共同基数、BONUS 增量/SPLIT 总量、经济事件及组件身份、完整 revision/cancel、全类型/分页/零行动覆盖、实际 P 行/价格基准、披露/首次观察/available_at 时钟及历史回放。来源与版本收敛后才注册正式 factor 行/Mapping/质量并接通存储 |
| B4 停牌引用 | **字段引用子项闭合**：追加 trading_halt_state@2.0.0，显式引用 instrument_status_daily@1.0.0 的 entity_key/status_date/instrument_status/is_tradable/available_at，复用既有单列状态投影 Builtin；PROVISIONAL，不认证历史来源 | 新调用必须明确指定 2.0.0；旧 1.0.0 完整载荷/Hash 保留并继续 fail-closed。未填写版本的既有调用仍固定旧 1.0.0，不自动取新版 |
| B4 原始指标残余 | early_seal_ratio、benchmark_realized_vol_20、market_drawdown_20 继续 FIXTURE_ONLY；**B4 整体未关闭** | 首封时间需可靠事件时间源，不能用 OHLC 推断；基准需固定指数/PRICE 口径、完整日期及历史可用证据，不能仅因 return_type 已投影而解除状态。没有输入证据不改旧 Definition 或临时重加权 |

当前 37 个原始指标的契约状态为 **EXECUTABLE=16 / BLOCKED=18 / FIXTURE_ONLY=3**；其余 28 个 Definition 为 DERIVED，合计旧 F2 65 个。EXECUTABLE 只表示本地契约路径可执行，不表示真实历史股票池、行情覆盖或生产能力已认证。

### 13.3 本次增量文件与实际链路

下表以 opening 字节为边界；所有路径均在唯一累计工作目录。未列出的 45 项开工 dirty 成果不归本次变更，包括 B5 两个 Migration、N1、N2、旧 Schema/Golden、市场计算和 Repository/FeatureStore 实现。

| 完整绝对路径 | 本次职责与原因；与既有成果的区别 |
| --- | --- |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\src\services\platform\indicator_registry.py` | 在既有 F1/F2 注册上追加停牌 2.0.0；Definition builder 可明确传版本；默认版本映射防止旧无版本调用静默升级，未知默认键拒绝。既有 14 F1、65 F2 和 Builtin 不改写 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\tests\platform\test_wp0303_input_closeout.py` | 本次新增 4 项：新旧引用/Hash、投影漂移与未来输入、缺能力/上游缺口、非法默认版本及旧调用兼容 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\tests\integration\platform\test_wp0303_closeout_postgres.py` | 本次新增 2 项真实隔离 DB 测试；新 Python PID 读回受限计算与完整评分 fixture 的固定 Bundle/Snapshot/Parquet，Correction 后同时读旧/新引用并拒绝 Formal/Paper。没有 mock DB、skip 或来源认证 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\WP-0303-IMPLEMENTATION.md` | 在已有记录上追加本节与最新路由；原各轮事实、计数和回滚原文保留 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\IMPLEMENTATION-STATUS.md` | 追加本次 PARTIAL/NO_GO 与当前 WP 行的增量路由，不提升 WP 状态或计数 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\CHANGELOG.md` | Unreleased 扁平条目记录版本化引用、进程级验证及未关闭边界，不重写旧条目 |

完成的中文子任务：**修复停牌特征的版本化 Canonical 引用，保护旧默认解析，并验证累计市场特征成果在真实隔离 PostgreSQL 和独立 Python 进程中的固定读取、失败回收及合成 Correction 技术路径。**

实际执行链分三层，不能混为一条已认证链：

1. 合成且符合已闭合字段的 MarketDay 行 → 每日冻结范围/分母/涨跌停及审计计算 → 既有 FeatureStore → 真实临时 Parquet/Manifest + PostgreSQL → 新 Python PID 固定 Preview Bundle 消费 → 合成输入变化后的同逻辑 Correction → 另一新 PID 同时验证旧/新引用及实际字节 Hash。原始输入是测试内存行，不是已认证 Raw/Canonical 文件。
2. 显式 FIXTURE_ONLY 原始分量 → 严格 T-1 标准化、五维/总分、平滑/状态 → 既有评分 fixture 发布 → 独立进程读回 → 从第 60 个历史位置开始的合成修正传播到全部后续平滑和状态；旧字节保留。该路径没有证明 37 个真实原始指标或 Provider revision 已闭合。
3. B3 固定 fixture 原始字节 → 已有复权算法/执行收据 → N2 内存血缘重算校验通过定向回归；**尚未贯通合法真实输入 → 正式 DERIVED 发布/Repository 重启 → 固定 F1/F2 消费**，不将 N2 改名或改标签替代生产执行证据。

### 13.4 实际验证、命令与阻断

所有仓库命令工作目录均为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`，Python 为已有 `C:\Users\lzq11\AppData\Local\Programs\Python\Python312\python.exe`（3.12.9）。以下套件有重叠，计数**不相加**。仓库外 `run_checks.py`/`run_postgres.py` 保存完整 argv、cwd、退出码、时长与日志，不是产品运行依赖。

定向命令的实际文件参数：

```powershell
$targeted = @(
  'tests/platform/test_wp0303_input_closeout.py',
  'tests/platform/test_adjustment_calculation.py',
  'tests/platform/test_adjustment_derived_contract.py',
  'tests/platform/test_market_sentiment.py',
  'tests/platform/test_indicator_registry.py',
  'tests/platform/test_feature_indicator_id_contract.py',
  'tests/platform/test_feature_store_contracts.py',
  'tests/platform/test_feature_partition_golden_bytes.py',
  'tests/platform/test_snapshot_foundation.py',
  'tests/platform/test_snapshot_lineage_gate.py',
  'tests/platform/test_contract_golden_payloads.py',
  'tests/platform/test_hashing.py'
)
python -m pytest @targeted -q --tb=short -rs

$postgres = @(
  'tests/integration/platform/test_wp0303_closeout_postgres.py',
  'tests/integration/platform/test_feature_indicator_id_postgres.py',
  'tests/integration/platform/test_feature_partition_key_postgres.py',
  'tests/integration/platform/test_market_sentiment_postgres.py',
  'tests/integration/platform/test_feature_store_postgres.py',
  'tests/integration/platform/test_feature_repository.py',
  'tests/integration/platform/test_postgres_foundation.py'
)
# 环境只由仓库外 helper 绑定至自己的随机 loopback 端口、密码文件和临时库。
python -m pytest @postgres -q --tb=short -rs
```

| 实际命令 | 退出码 / 结果与证明范围 |
| --- | --- |
| 上述 targeted 命令 | **0；500 passed / 0 skipped / 1 warning**；包含 Market/Adjustment/N2/Registry-DAG/FeatureStore/Snapshot/Golden/Hash 与新增 4 项引用回归 |
| 上述 postgres 命令 | **0；66 passed / 0 skipped / 1 warning**；复用 B5 64 项并追加 2 项独立 PID 验收，覆盖真实迁移、原子发布、单连接、COMMIT 失败回收、旧/新固定消费、合成 Correction 与安全降级。没有改变历史迁移 |
| `python -m pytest tests/platform --ignore=tests/platform/api -q --tb=short -rs` | **0；899 passed / 5 skipped / 2 warnings**；只为核心回归，不是完整平台/API通过 |
| `python -m pytest tests/platform -m "not network" -q --tb=short -rs` | **2；3 collection errors**，三个 API 文件的既有导入链缺 markdown2，未执行完整平台套件 |
| `bash scripts/ci_gate.sh all`（Git Bash 一次性绑定 python/python3/flake8 到已有 3.12） | **1**；syntax、critical flake8、export 通过，scripts/test.sh code 导入既有 efinance_fetcher 缺 tenacity 后中止，完整 offline suite 未到达。不安装依赖、不加 stub |
| `python scripts/export_platform_contracts.py --check` | **0**；生成 Schema/OpenAPI/客户端当前一致，本次未生成或编辑它们 |
| `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | **各 0**；治理、外部源码边界、许可证/链接检查通过，不等于安全/生产认证 |
| `python -m py_compile src/services/platform/indicator_registry.py tests/platform/test_wp0303_input_closeout.py tests/integration/platform/test_wp0303_closeout_postgres.py` | **0**；本次三个 Python 文件语法通过 |
| `python -m flake8 --select=E9,F63,F7,F82,F401,F821` 后接上述三个 Python 文件 | **0**；定向相关 lint，不声称全规则风格检查 |
| `python -m alembic heads` | **0**；仍为唯一 0015_wp0303_partition_key，0014/0015 原字节不变 |
| `git diff --check` | **0**；保留既有 LF/CRLF 提示；未跟踪新文件另检查行尾/冲突标记 |

5 项 skip 为既有 Windows 非必需市场路径限制：namespace_resolver.py:38 三项和 orphan_sweeper.py:92 一项无 symlink 权限（WinError 1314），settings_and_secrets.py:172 一项 POSIX mode bits 不适用。Market/Adjustment/本次 PostgreSQL 必需路径没有 skip。warnings 为既有 Starlette/httpx 弃用提示和测试辅助类 collection warning，不修改依赖。

早期失败不删除：`b4-red.log` 为 3 failed（缺新版）；`b4-green.log` 为 96 passed/3 failed（默认自动升级、实际错误码及测试对 Formal Definition 的错误假设），随后保留旧默认并按实际契约修正新测试。`postgres-new.log` 为 2 failed，原因是新增独立进程测试构造 Formal requirement 时漏必需 backtest_core；补全合法 requirement 后仍验证实际市场能力拒绝，最终 66 项全部通过。没有修改旧测试/Golden或删除失败断言。

隔离 DB 使用本机已有 `postgres:16`、`--pull=never`、tmpfs、随机 `127.0.0.1` 端口及每测试随机 `visory_test_<20hex>` 数据库；末轮随机测试库剩余 0，两个本次容器均 stop/自动删除，临时密码/env 文件已删除。不连接其他容器/业务库，不操作真实 /data。

### 13.5 逐项验收与风险

对照实施路线 WP-0303、PREP 第 9 节及本 Goal 的完整条件：

| 验收项 | 判定 | 未满足范围 / 分级 |
| --- | --- | --- |
| 开工备份、唯一目录、旧成果保护 | 本地通过 | 原字节/Hash及主 checkout核验；不代表远程合入 |
| B1/B2 合法历史输入与版本/质量 | 未满足 | **BLOCKER**：来源/口径/真实样本/覆盖/PIT 不充分 |
| B3 来源、正式因子 Dataset、固定字节派生发布 | 未满足 | **BLOCKER**：缺合法输入与正式持久执行闭包；N2 仅 fixture 内存桥接 |
| B4 版本化停牌引用 | 子项通过 | 旧载荷/默认保持拒绝，新 2.0.0 显式可解析；不是生产来源认证 |
| B4 基准与首封时间残余 | 未满足 | **BLOCKER**：三项原始指标仍 FIXTURE_ONLY，不提升历史认证 |
| 历史冻结股票池/分母/覆盖率 | 技术路径通过、真实历史未满足 | **BLOCKER**：合成小股票池不能认证真实全市场覆盖 |
| 上涨/下跌、新高/新低、量价/风险偏好及 37 原始指标 | 未满足完整真实输入计算 | **BLOCKER**：18 个 BLOCKED、3 个 FIXTURE_ONLY 保留缺失 |
| T-1/warmup/标准化/五维/总分/平滑/状态 | 本地算法回归通过 | **BLOCKER**：完整实际输入链未满足；不重加权/补零/沿用昨日值 |
| 固定 FeatureBundle、实际 Parquet/Manifest、独立 PID恢复 | 隔离技术通过 | **BLOCKER**：真实来源→正式 DERIVED→全部 F1/F2 消费仍未验收 |
| 原子发布/失败回收/B5 | 本地真实 DB 技术通过 | 复用既有 B5，不推进新 Migration或运行环境升级 |
| Correction 窗口、平滑、状态和旧引用保护 | 合成技术通过 | **BLOCKER**：未认证真实来源 revision/cancel 全链；新 cutoff/输入身份不是同逻辑 Correction |
| 旧 14 F1/65 F2、Golden/Hash/生成客户端 | 本地通过 | 完整载荷集合 Hash仍为 e65941d7... / 02875876...；仅追加停牌版本，不改旧引用 |
| 完整 backend/platform/API gate | 平台/API 通过，all gate 未通过 | **BLOCKER**：现有环境解除缺依赖后，完整 gate 实际运行仍有 80 failed；见 13.7，不安装依赖或规避测试 |
| 两市场能力、Formal/Paper | 正确保持拒绝 | **BLOCKER**：未满足认证条件；缺失不是成功认证 |
| 远端本次 CI/合入、生产认证/发布 | 未执行 | 本次未经 Git/生产授权；不得用 baseline CI替代；NOT CERTIFIED、RELEASED=false |

FOLLOW-UP：获单独授权后执行当前增量远端 CI/review/合入、真实环境运行/性能/备份恢复验收；特殊行动/配股及相邻 WP 不进入本次实现。NOTE：源码中的无版本 get 对其他既有指标保留原行为；本次新增停牌版本及新测试全部显式 pin，不把默认映射当作 latest fallback。

剩余最大风险是将本地合成技术证据误读为来源/PIT认证。当前仍缺 Raw/Canonical 实际输入字节及完整行集、来源可用性、正式 DERIVED持久证据和真实修订传播；本轮明确不声明这些路径通过。未运行 Web/Desktop 构建、UI、生产调度、Provider API、生产 DB、灾备或覆盖率测量。定点检索 API/客户端未发现 default_indicator_registry 消费入口，公共 Schema/生成客户端字节不变，故无需本次客户端构建；这是兼容性范围判断，不是构建通过。

### 13.6 基线、CI、增量回滚与交接

- 只读 `gh api repos/yutianlzq/Visory/actions/runs?head_sha=efe8e9b362cba13eca183c55be57bbbbc832b60b&per_page=10` exit 0：Run [37645716721](https://github.com/yutianlzq/Visory/actions/runs/37645716721)，main / workflow_dispatch / completed / success，所属提交为 **efe8e9b...**，创建于 2026-10-07。它仅是基线 CI，不覆盖累计 dirty 成果或本次增量。
- branch/HEAD仍 detached / efe8e9b...；实时 main 开工查询成功，收尾观测另保存在证据目录。**本次未执行 commit/tag/branch/push/PR/merge/fetch/pull、生产调度、部署或生产发布**。
- 兼容性保护采用旧完整载荷及 Hash回归、所有开工可见文件 SHA256、旧 Golden/Schema/迁移/客户端字节与主 checkout状态/diff。只把表中六个路径的 opening→final 增量计为本次成果，不把现有 F2注册、N1/N2、B5及既有 untracked文件计为新增。
- 本次不增加持久化结构，无数据库迁移回滚。撤销仅限证据目录 `incremental.patch` 的本次 hunk：先核对 final Hash和后续编辑，再人工反向合并 indicator_registry 的 builder参数、新版 Definition、默认版本映射及装载增量；三份文档只撤销本次插入/当前路由；两个新测试确认无后续修改后才撤销。不整文件恢复，不删除既有 untracked成果，不改0014/0015、不 reset/clean/stash，不删除已固定 Partition/Snapshot/Bundle或重绑 latest。
- 输入认证不能靠增量代码补出：继续推进需提供 B1/B2/B3 的固定版本真实脱敏归档及上述口径/覆盖/时间/修订证据，并明确 B4基准/首封时间历史来源。完整 gate 已用现有环境实际执行，当前失败与可用 Linux 环境缺口见 13.7；本次没有为绿色结果安装或替换任何依赖。
- 双语评估：本 WP无受影响的英文专题副本，仅同步中文实施记录/状态及 CHANGELOG，不修改 README或上游英文资料。

### 13.7 现有环境补充验收：完整平台通过，all gate 失败

本次自动续跑完成了新的本地验收证据，完整 Goal 仍为 **PARTIAL**。B1/B2/B3 与 B4 残余没有收到新的真实来源归档，来源/PIT 判定仍为 **NO_GO**；不得把测试环境补齐等同于输入认证。13.4 中基础 Python 的缺依赖失败日志保留为历史执行事实，当前环境与完整 gate 判定以本节为准。

发现主 checkout 内已有 `E:\Personal Manager\Visory\.venv\Scripts\python.exe`（3.12.9），仅复用解释器和已安装依赖，全部命令 cwd 仍为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。确认 `src`/`api` 实际加载自该累计目录；`PYTHONDONTWRITEBYTECODE=1` 防止常规导入写字节码。已有 pyarrow=18.1.0、psycopg=3.3.4 与受控声明一致；tenacity=9.1.2、markdown2=2.5.4 存在。未 pip install、升级、下载依赖，未修改主 checkout 的 Git 状态/diff。

| 实际命令与工作目录 | 退出码 / 结果 |
| --- | --- |
| 上述解释器 `-m pytest tests/platform -m "not network" -q --tb=short -rs`；cwd 为累计目录 | **0；944 passed、5 skipped、7 warnings**，包括三个原先收集失败的 API 文件；5 skip 仍为原有 Windows symlink/POSIX mode 限制 |
| Git Bash 将 python/python3/flake8 一次性绑定到上述解释器后 `bash scripts/ci_gate.sh all`；cwd 为累计目录 | **1；7358 passed、80 failed、10 skipped、4 deselected、68 warnings、572 subtests passed**；完整 gate 523.59 秒，pytest 497.00 秒。syntax、critical flake8、export、code/yfinance 代码转换均通过，离线全套实际执行完毕，没有将失败结果改成绿色 |

完整 gate 的实际包装 argv：

```text
C:\Program Files\Git\bin\bash.exe -c
python() { "$VISORY_CLOSEOUT_PYTHON" "$@"; }; python3() { "$VISORY_CLOSEOUT_PYTHON" "$@"; }; flake8() { python -m flake8 "$@"; }; export -f python python3 flake8; bash scripts/ci_gate.sh all
```

环境中的 `VISORY_CLOSEOUT_PYTHON=E:/Personal Manager/Visory/.venv/Scripts/python.exe`。离线 pytest 实际参数为 `-m "not network" --timeout=120 -o timeout_method=thread -o faulthandler_timeout=300 --durations=30 --durations-min=0.5`，不删除断言、不新增 skip、不 mock 数据库或必需执行路径。

从完整 gate 的逐项日志核验，本 Goal 的 **12 个定向文件共 500 项全部 PASSED**，**7 个 PostgreSQL 文件共 66 项全部 PASSED**，包含本次 4 项输入回归及 2 项独立进程消费测试，没有 FAILED/SKIPPED。这些计数是完整套件的子集，不相加。10 skip 中 5 项为上述平台限制，其余 5 项是既有 Codex/运行调度的 POSIX 进程组限制；4 deselected 为 network marker 排除项，不属于本 Goal 的必需市场/Adjustment/数据库路径。

完整 gate 失败分布：

| 未修改的测试文件 | failed |
| --- | ---: |
| tests/test_agent_backend_status_service.py | 14 |
| tests/test_codex_app_server_gate_a.py | 31 |
| tests/test_codex_tool_process.py | 12 |
| tests/test_intelligence_service.py | 1 |
| tests/test_llm_usage.py | 5 |
| tests/test_local_cli_backend.py | 10 |
| tests/test_screening_api.py | 1 |
| tests/test_storage.py | 5 |
| tests/test_system_config_api.py | 1 |

失败日志可观察到原生 Windows 的 `platform_unsupported`、进程/CLI 平台行为、权限位/中文编码，以及 SQLite 临时文件释放的 WinError 32；情报和热点路径的失败尚未继续诊断。九个测试文件及相关 status/transport/tool-process/local-cli/storage/intelligence/screening 源文件均与 opening Hash 相同，保存在 `gate-failure-opening-file-hashes.json`。这只证明本次未改这些文件，**没有逐项执行 opening 基线对照，不能将全部 80 项断定为既有问题或认定与增量完全无关**。

**BLOCKER**：完整 gate 未通过，当前原生 Windows 全套不能作为完整验收。现有 Docker 镜像无 Python/CI 依赖环境；本机 WSL Ubuntu-22.04 的 `/usr/bin/python3` 为 3.10.12，缺 pytest、pydantic、sqlalchemy、psycopg、pyarrow、flake8、tenacity、markdown2 等，不能直接执行 Linux 全套。本次未安装 WSL/Docker 依赖、未跨到远端机器，也未修改 CLI/Legacy SQLite 等无关模块。兼容 Linux 环境验证或这些模块的修复范围须另行明确，未以模拟 POSIX、跳过失败项或移除断言替代验收。

完整 gate 复用本机 `postgres:16`，`--pull=never`、tmpfs、随机 loopback 端口和 `visory_test_<20hex>` 测试库。临时容器 `visory-wp0303-closeout-337069a687cb` 已停止并自动删除，测试库剩余 0，`gate-postgres-password`/`gate-postgres.env` 已删除；未连接生产数据库、真实 Provider API 或真实 `/data`。终止后再次核验保护，既有 1561 个文件中 1557 个原字节不变、45 个开工 dirty 文件不变，HEAD/index/主 checkout Git 状态和 diff 不变。

本次续跑仅更新实施记录、状态入口和 CHANGELOG，不新增代码、测试、Dataset、Mapping、Migration 或公共契约。仓库外新增环境审计、完整平台/all gate 的 JSON/log、失败分组与必需路径证明，位于原证据目录；这些脚本不是产品依赖。文档同步后治理、基线、契约导出和 diff/保护检查均退出 0，656 个相对链接无断链；完整 argv/退出码写入命令索引。收尾实时 main 查询退出 0，仍为 efe8e9b362cba13eca183c55be57bbbbc832b60b。

当前结果：完整平台/API 检查的环境阻断已关闭；完整 gate 从未到达离线套件变为实际执行并失败。来源/正式派生/真实 Correction 等验收矩阵不变，**WP-0303=IN_PROGRESS、15/45、两市场 missing、Formal 拒绝、NOT CERTIFIED、RELEASED=false**。未 commit/tag/branch/push/PR/merge/fetch/pull、生产调度或部署。新增文档仍按 opening→final 的 `incremental.patch` 逐 hunk 回滚，不整文件恢复。

<a id="reference-development"></a>
## 14. 2026-10-13 参考源码下载与消费反例开发

### 14.1 授权、开工保护与采用范围

用户明确授权“将参考项目下载到 E:\Personal Manager\参考项目中，然后引用参考项目做开发”。本次范围为上轮列出的 a-stock-data、AKShare、LEAN、Financial-API；仅推进 WP-0303。源码放在指定仓库外目录，Visory 开发仍只在 `C:\Users\lzq11\.codex\worktrees\f468\Visory`，主 checkout 不编辑，不安装依赖、不执行上游脚本/示例，不访问 Provider 业务 API、业务 dump、生产数据库或真实 `/data`。

开工为 detached HEAD `efe8e9b362cba13eca183c55be57bbbbc832b60b`，实时 `git ls-remote origin refs/heads/main` exit 0 返回相同 SHA。开工 **24 tracked modified + 27 untracked = 51 项**，保存原始字节、SHA256、index/working/HEAD binary diff；另保存累计目录 1563 个和主 checkout 1509 个 Git 可见文件 Hash。证据目录为 `C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-REFERENCE-DEV-20261013-214519`，`opening-inventory.json` 与 `opening-files/` 定义增量边界，不能用 HEAD 覆盖开工 dirty 成果。

`references/manifest.yaml` 的十个历史项目和历史 SHA 不改写。新增来源只用于本节的离线公式/反例核对，不注册新 Provider，不把 AKShare 或 LEAN 变成运行依赖。参考目录中原有十个 `*-main`/`*-master` 副本保留；新 checkout 与这些历史副本分开。

### 14.2 固定来源与下载结果

| 项目与绝对路径 | 来源版本、许可证与状态 |
| --- | --- |
| `E:\Personal Manager\参考项目\a-stock-data` | `https://github.com/simonlin1212/a-stock-data.git`；commit `29b07d2e37005b9fd568bca1262f6e572b5f9407`，tree `0207d3ec35593524a7fe9870413ac5ddaf6f282a`；Apache-2.0；新下载的 depth=1 detached checkout，16 个文件 Hash，0 LFS pointer |
| `E:\Personal Manager\参考项目\akshare` | `https://github.com/akfamily/akshare.git`；commit `fe10d1decb705e5f43cc8ca3339ca39e580fb8f4`，tree `44e915e9af48bf918d8e4706f7c9a365365caff7`；MIT；新下载的 depth=1 detached checkout，498 个文件 Hash，0 LFS pointer |
| `E:\Personal Manager\参考项目\Lean-80e7843f6456` | `https://github.com/QuantConnect/Lean`；commit `80e7843f645673bcbeaab963049f76f20f6785e1`，提交时间 2026-10-06T17:34:53Z；Apache-2.0；完整 clone exit 128、稀疏 clone 300 秒超时，随后从固定 commit 的官方 codeload 下载完整 ZIP、校验 CRC 并安全解压；6353 个文件 Hash，0 symlink、0 LFS pointer |
| `E:\Personal Manager\参考项目\Financial-API-main` | 原有历史副本；`https://github.com/HiThink-Tech/Financial-API.git` 本次 clone exit 128、Repository not found。仅复用本地 401 个文件的 Hash 固定副本及 MIT LICENSE；历史 manifest 声明 SHA `2ec779c94e798ea941befb2d1c951c9420fdadd0`，本次无法从远端重验，不宣称当前版下载完成或仓库已经删除 |

下载命令、cwd、退出码分别在 `download-*.json`；逐文件 Hash 在 `reference-hashes-*.json`，Financial-API 历史副本在 `financial-historical-hashes.json`。指定目录的 `REFERENCE-PROJECTS-*.json` 保留每次下载结果和来源，不作为生产 Dataset/Mapping 或历史可用性凭证。LICENSE 原字节及 Hash 一并保留；没有复制外部函数或 SDK 进入产品，也没有运行 C# 上游测试。

最终外部来源清单为 `E:\Personal Manager\参考项目\REFERENCE-PROJECTS-20261013-221519-FINAL.json`，开发采用说明为同目录 `Visory-WP0303-REFERENCE-USAGE-20261013.md`。LEAN 原始包为 `E:\Personal Manager\参考项目\Lean-80e7843f6456.zip`，227553836 bytes，SHA256 `108aeddc78694a396532b7a4227c9ac4d409b888ea78b101a5a5ea84506dd6ee`；源下载 URL 固定为 `https://codeload.github.com/QuantConnect/Lean/zip/80e7843f645673bcbeaab963049f76f20f6785e1`。Financial-API 错误仍保留，不将本地历史副本写成新下载当前版。LEAN 重试异常日志保存在证据目录，不复用失败目标或覆盖原参考副本。

### 14.3 实际采用的语义、反例与输入判定

| 来源及可定位代码 | 核对结果与本次开发用途 |
| --- | --- |
| a-stock-data `SKILL.md:4451`，`limit_up_sentiment` | 炸板率输出为百分数且空分母返回 0；Visory 仍使用 ratio、空分母缺失。回归验证 1/3 的 Parquet 值为 `0.333333333333`，不误用 `33.3`；有完整规则但无人触板时，已知家数为 0、炸板率为空 |
| a-stock-data `SKILL.md:4470`，晋级率说明 | `pct >= 9.8` 不能适用于 ST/创业板，也不能代替 T-1 连板候选。新增混合规则反例：ST 5% 封板、主板 9.9% 炸板、创业板 20% 封板；晋级分母由 T-1 两个合成规则候选固定，T 日结果为 1/2 |
| AKShare `akshare/stock/stock_zh_a_sina.py:205` | 源 `outstanding_share` 与行情 outer join 后执行全表 ffill，再乘 10000 转股并计算 volume/share。没有披露/观察时钟的变更表和 ffill 不能证明 PIT；不将该字段或 shares_outstanding 注入旧 security_master |
| AKShare `akshare/stock_feature/stock_ztb_em.py:1`、`:39`、`:96` | 源码注释排除 ST/科创板；first-seal 原始 fbt 格式化为六位时钟。涨停池不是全市场 scope、空返回不证明合法零行。与 a-stock-data `SKILL.md:4446` 的同花顺 Unix 秒时钟分别记录，原始字段不得直接混入 bar_1d_raw 或由 OHLC 推断首封 |
| Financial-API 历史 `docs/api/endpoints-prices.md:130`、`:175` | 原始事件流；ex_date_ms 是上海零点毫秒，现金为税前每股原币种、送股为增量比例；不返回 event_type/record_date/adjust_factor。没有稳定事件/revision/cancel/旧股共同基数与覆盖证明，不把隐式数值分类或当前事件流当正式每日因子 |
| LEAN `Indicators/AdvanceDeclineDifference.cs:29`、`AdvanceDeclineRatio.cs:29`、`ArmsIndex.cs:70`、`AdvanceDeclineIndicator.cs:100` | 涨跌家数差、涨跌比及 TRIN 的公式和前收方向核对；ADR 在 decline=0 时返回 advance、TRIN 在 ADVRatio=0 时返回 0，不采用这些边界 fallback。新增反例保留 raw close 正负方向下的 PIT 宽度缺失；外部公式不证明复权/股票池/历史覆盖，不新增 TRIN 或运行 LEAN |

来源字节 SHA256：a-stock-data `SKILL.md=d30aa90edb881a45168c397a6ca1ccfebc440a8d4c93b3d94d3123d27b260a1d`；AKShare 股本源码 `aa60721af3f7bdec29e1e5f59ff6770b54fc919fc6867706d16d36b3a7ee07a2`、涨停池源码 `6d0fbd5aa084e1ffc698f794c3b2d97271530f5d4f1f2674dad58b2e92bc35c2`；Financial-API 历史价格/公司行动文档 `ba5d28a3078c63c7bbc46e8c96e84befbb9be720c1d0673aa5dfefc1ed6eaff9`。这些是参考文件 Hash，不是真实行情或源响应的 Hash。

本次新增 `tests/platform/test_wp0303_reference_semantics.py` 的 10 项确定性回归；复用原 `market_day`/MarketDay、固定 scope、实际 `evaluate_market_days`、FeatureStore 字节读取与 Parquet 解码，不 import/exec 外部源码、不 mock 必需链路、不修改旧测试/Golden。

实际链路为：**明确合成的 ST/主板/创业板 Canonical 形状行 → 冻结 scope/实际涨停价/触板分母 → 既有 1.0.0 市场计算 → 既有 FeatureStore 的实际 Parquet/固定 Partition/Snapshot/Bundle → Preview 固定消费，Formal 拒绝**。外部源码仅为公式与错误处理的核对证据，未成为行情输入。B5/N1/N2 只回归复用；N2 名称、FIXTURE_ONLY 证明等级和算法不变。

### 14.4 本轮实际验证

所有仓库命令 cwd 为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。只复用已有 `E:\Personal Manager\Visory\.venv\Scripts\python.exe`（3.12.9）及现有依赖，设置 `PYTHONDONTWRITEBYTECODE=1`；日志/精确 argv/退出码在本次证据目录，汇总索引为 `final-command-index.json`。

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest tests/platform/test_wp0303_reference_semantics.py -q --tb=short -rs`，首轮 | exit 1；9 passed / 1 failed；新增测试误用了不存在的 read_partition_rows，改为现有 read_partition_payload 后真实解码 Parquet。保留失败日志，不放宽断言 |
| `python run_checks.py targeted`，脚本在证据目录；13 个定向文件列表保存在 reference-targeted.json | exit 0；510 passed / 0 skipped，包含本次 10 项与既有 Market/Adjustment/N2/Registry/DAG/Store/Snapshot/Golden/Hash |
| `python -m pytest tests/platform -m "not network" -q --tb=short -rs` | exit 0；954 passed / 5 skipped / 7 warnings；skip 为已有 Windows symlink 权限四项、POSIX mode bits 一项，不属于必需市场/因子链路 |
| 七个 PostgreSQL 定向文件，精确列表保存在 postgres-required.json | exit 0；66 passed / 0 skipped，60.20 秒；实际执行隔离 DB 发布/回收/重启/固定引用/合成 Correction；不冒充真实来源修订认证 |
| Git Bash 一次性绑定现有解释器后 `bash scripts/ci_gate.sh all` | exit 1；7368 passed / 80 failed / 10 skipped / 4 deselected / 68 warnings / 572 subtests passed；离线套件 496.99 秒。syntax、critical flake8、export、code/yfinance 检查通过，完整 gate 未通过，不新增 skip/mock 或删除断言 |
| `python scripts/export_platform_contracts.py --check` | exit 0；生成契约无漂移 |
| `python scripts/check_ai_assets.py` | exit 0；AI 资产治理通过 |
| `python scripts/check_visory_baseline.py` | exit 0；收尾 658 个相对链接、0 断链，历史参考仍为 10 项；此前 657 项检查保留 |
| `python -m py_compile tests/platform/test_wp0303_reference_semantics.py` | exit 0 |
| `python -m flake8 --select=E9,F63,F7,F82,F401,F821 tests/platform/test_wp0303_reference_semantics.py` | exit 0；本次新测试定向 critical lint |
| `git diff --check` | exit 0；仅现有 LF/CRLF 提示 |
| 仓库外 `verify_protection.py`、`git apply --reverse --check <证据目录>/incremental.patch` | 最终 exit 0；仅三份既有文档的本次增量与一个新测试，回滚 patch 可反向应用；未执行回滚 |
| 收尾 `git ls-remote origin refs/heads/main` | exit 128；GitHub 443 连接失败，收尾重试未取得远程 SHA，不能宣称收尾远程仍与 HEAD 相同。开工成功查询保留 |

完整 gate 失败分布为 agent_backend_status_service 14、codex_app_server_gate_a 31、codex_tool_process 12、intelligence_service 1、llm_usage 5、local_cli_backend 9、runtime_scheduler_service 1、screening_api 1、storage 5、system_config_api 1。十个失败测试文件与 opening Hash 相同；本次没有重跑 opening 基线全套，因此不能把全部失败断言为既有问题或与增量完全无关。Windows 进程/CLI/权限位/编码、SQLite 临时文件释放等错误仍需兼容环境或另授范围诊断，未扩到这些模块。10 skip 为既有 Windows symlink/POSIX mode/进程组限制；4 deselected 是 network 排除项。

`gate-failure-summary.json` 保存失败分组与 Hash 对照；完整 gate 的 262 条本次新增/市场/Adjustment/进程消费关键路径记录均为 PASSED，没有 FAILED/SKIPPED。定向 510 与 DB 66 是有重叠的独立验证计数，不累加为独立总覆盖。

隔离数据库复用本机已有 `postgres:16`（未 pull），容器 `visory-wp0303-reference-08e34f8df2d7` 使用 tmpfs、随机 loopback 端口和 `visory_test_<20hex>` 临时库。收尾剩余测试库为 0，docker stop exit 0，容器自动删除，临时密码/env 文件删除；未访问其他容器/业务库/生产存储。此前第 13.7 节证据保留，不替代本次实际执行。

最终保护核验：开工 1563 个文件中 1560 个原字节不变，仅 CHANGELOG、IMPLEMENTATION-STATUS、WP-0303-IMPLEMENTATION 三份文档有本次增量；新文件只有本节的测试。主 checkout 的 1509 个文件和 Git status 不变，累计 HEAD 与 staged diff 不变；a-stock-data 16、AKShare 498、LEAN 6353、Financial-API 历史 401 个文件均与下载/开工 Hash 一致。opening→final 的 `incremental.patch` 单独保存，不以 HEAD diff 代表本次改动。

证据脚本曾将检查结果写入同名 baseline.json，覆盖开工元数据文件，导致首次保护脚本 exit 1、KeyError: 'head'。原始字节、Hash 清单和三个 diff 均未受影响；按本轮开工命令输出恢复为 `opening-baseline-recovered.json` 并注明来源，检查结果改用 `baseline-check.json`。`baseline-check-first.json` 与 `protection-first-failure.json` 保留错误事实，最终保护核验 exit 0；这是本次证据命名错误，不描述成仓库漂移。

### 14.5 验收矩阵、兼容与回滚

| 项目 | 本次判定与剩余条件 |
| --- | --- |
| 来源版本与公式参考 | 两个新完整 Git checkout 和一个完整固定 ZIP 已下载；Financial-API 当前下载 BLOCKER，历史副本独立标记 |
| B1 | NO_GO；当前/涨停池流通市值不足以证明全市场历史身份、完整覆盖、口径和 PIT；不追加不确定 Dataset/Mapping |
| B2 | NO_GO；历史股本原始记录、生效/观察/可用时钟、正确分母与单位仍缺；外部 ffill 与字段名不解除阻断 |
| B3 | NO_GO；原始事件流的共同旧股基数、身份/修订/取消/覆盖/PIT 不足，正式因子 Dataset→DERIVED 持久执行→F1/F2 链仍未满足 |
| B4 | 既有停牌 2.0.0 引用子项保留；首封时间与基准两项仍 FIXTURE_ONLY，不因出现外部字段解除；B4 整体未关闭 |
| 五维、分母、固定权重、窗口和 Correction | 本次补外部语义反例及既有技术链回归；完整真实 37 项、真实历史股票池和来源 Correction 未认证 |
| 本地发布/消费与 B5/N1/N2 | 定向与隔离 DB 通过；保留旧 payload/Hash/版本/文件/引用，0014/0015 未修改 |
| 完整 gate | BLOCKER；实际执行退出 1、80 failed，未以本次定向通过或历史 CI 替代 |
| 本次 CI/合入/生产 | 未执行；历史基线 CI 仅覆盖 efe8e9b...，不覆盖本次 dirty 增量；收尾远程复查连接失败，当前远程 SHA 未确认；NOT CERTIFIED、RELEASED=false |

当前只新增测试及三个文档的增量，没有运行模块、公共 API/Schema/客户端、Dataset/Raw/Mapping、Definition、Migration、依赖或配置变化。API/客户端未受影响，未运行 Web/Desktop 构建，不把该判断写成构建通过。没有英文对应专题需同步；原历史参考 manifest 不改写。

BLOCKER：Financial-API 当前源码无法下载，需可访问来源或可核验离线导出；B1–B3/B4 残余真实脱敏归档、历史可用时钟及完整覆盖未提供；完整 gate 失败。FOLLOW-UP：经单独授权的远端 CI/合入及生产运行验收；不扩大到 WP-0304/0305、Hikyuu、页面或 Paper Portfolio。参考下载与消费反例切片已推进，完整 Goal 仍 PARTIAL/BLOCKED，WP-0303=IN_PROGRESS。

回滚仅限本证据目录 opening→final 的本次 patch hunk；核对 `final-incremental-hashes.json` 的 final Hash 和后续编辑后，撤销三个文档增量及本次新测试。`git apply --reverse --check` 只检查 patch，不实施回滚。外部新下载目录/清单与既有十个参考副本分开；若撤销下载，先核对其路径、Hash、引用及是否有后续工作，再仅处理本次新目录，不批量删除参考根。不得整文件 restore、reset/clean/stash、改旧迁移/Golden或删除固定分区。未执行 commit/tag/push/PR/merge、生产调度/部署/发布。

<a id="github-input-resume"></a>
## 15. 2026-10-14 GitHub 实际样本门禁与目标续跑

### 15.1 范围、开工保护和推进步骤

用户已授权继续 FULL-INPUT-TO-FEATURE-CLOSEOUT。本次仍只推进 WP-0303，唯一累计目录为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`，不修改主 checkout 或外部参考源码，不安装依赖，不访问真实 Provider 业务 API、生产数据库或真实 `/data`，不执行远端写入/生产调度/部署。

开工 detached HEAD 为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`；实时 `git ls-remote origin refs/heads/main` exit 0 返回同一 SHA。**24 tracked modified + 28 untracked = 52 项既有成果**保存原始字节、SHA256 和 working/staged/HEAD binary diff；另保存累计目录 1564 个、主 checkout 1509 个 Git 可见文件 Hash 和 index/status。主 checkout 仍为 `codex/wp-0207-backfill@528baa072d32f0242cfdcfa8bb7b1314de19db78`，其 3 项既有文档修改不归本次成果。

仓库外证据目录：`C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-INPUT-RESUME-20261014-100626`。`opening-metadata.json`、`opening-inventory.json`、`opening-files/`、`opening-all-hashes.json` 和主 checkout 对照清单定义本次增量边界，不使用 HEAD 覆盖 dirty 字节。

步骤：①实际输入证据/契约门禁；②通过后才启动正式派生发布；③固定消费与 Correction；④综合验收。第①步实际重新校验 19 个固定 GitHub 源文件和 8 个 CSV 的 18,616 行，全部候选正式输入 NO_GO，第②步未启动。第③步仅复验既有隔离技术链，复用 B5/N1/N2，不改 FixtureExecutionLineageBridge 的名称、模式或证明等级。

### 15.2 新输入证据及版本决定

固定来源、完整行数/日期、重复冲突、单位/身份/覆盖/PIT 缺口及具体决策问题的权威矩阵在[来源门禁第 9 节](WP-0303-B3-SOURCE-EVIDENCE-PREP.md#github-sample-admission)，原下载目录和源文件 Hash 也绑定在本次 `source-admission-current.json`。这批材料包含历史数值和真实仓库文件，未证明它们是完整原始采集归档或合法历史 PIT。

关键拒绝证据：浦发样本 32 行股本/流通市值为 0，固定采集代码有 fillna(0)；比亚迪分红/股本各键重复 3 次，价格 2000 个键重复且 2026-08-18 一键有两组冲突值；首封未取得合格事件包，证券名单缺历史状态/退市/观察时间。没有把字段名、乘法自洽、当前下载时间或 Git 提交时间提升为历史证据。

补充读取当前 Tushare `daily_basic` 第一方静态字典，实际 HTML/Hash 和获取时钟已固定；它部分确认当前市值/股本单位及两种换手率分母，不能认证历史 CSV、Baostock 的 `turn` 或 G4 单位。详细边界见上述权威来源矩阵，8 个 CSV 的正式输入 NO_GO 不变。

**输入/版本决策仍未收敛，因此本次不追加 Dataset/Raw Schema/Mapping/质量/新 Definition 或 Migration。** 旧 14 F1/65 F2 的完整载荷、Hash、Golden、固定引用和 0014/0015 均保留。停牌 2.0.0 是既有已关闭引用子项，不计本次新增；18 个 BLOCKED、3 个 FIXTURE_ONLY 不解除，不用总市值、总可交易股本、未知行动补零/因子补 1 或 broad fallback。

### 15.3 本次增量路径与实际链路

| 完整绝对路径 | 本次职责及原因 |
| --- | --- |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\WP-0303-B3-SOURCE-EVIDENCE-PREP.md` | 追加第 9 节：实际 GitHub 样本、固定版本/字节、质量拒绝、具体决策问题及各输入最小证据；不改旧 Provider 历史语义结论 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\WP-0303-IMPLEMENTATION.md` | 追加本节：开工保护、步骤状态、当前命令/验收、兼容与增量回滚 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\IMPLEMENTATION-STATUS.md` | 追加当前日期入口，并将 WP-0303 当前证据路由指向本节；旧计数作为历史保留 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\CHANGELOG.md` | Unreleased 追加一条扁平文档记录，明确样本 NO_GO、真实链未认证 |

只有上述四份既有 dirty/untracked 文档的本次增量；运行代码、测试、生成契约、迁移、客户端、依赖、配置和其他开工成果不计为本次修改。没有对应英文专题副本需同步，不修改 README 或上游英文资料。

实际样本链路：固定 GitHub commit/文件树 → 原始文件实际字节及 SHA256/Git blob → 完整 CSV 行、重复、零值和冲突复核 → 来源/PIT/覆盖门禁 NO_GO。**该链路停在正式 Raw/Canonical/Snapshot 输入前，没有源样本 → 正式因子/37 原始指标 → DERIVED/FeatureStore → 固定 Bundle 的生产闭包。**

隔离技术链复验使用现有明确合成 Canonical 形状输入 → 16 个受限原始量/完整评分 fixture → 实际 Parquet/Manifest/固定 Partition/Snapshot/Bundle → Repository 读回与独立 Python PID 恢复 → 合成 Correction 的统计/平滑/状态后续传播与旧文件保留。该路径不认证 G1—G4 或真实 Provider revision。

两项独立进程用例分别覆盖受限合成输入和完整评分 fixture；前者使用正常 FeatureStore 存储模式，后者显式 `fixture_only=True`。前者的 `fixture_only=False` 只证明正常持久化路径可以恢复，不把合成输入提升为真实 Raw/PIT 归档。完整评分用例验证修订点之前结果不变、其后五个 session 平滑值变化、修订点状态变化，并保留旧 Partition 字节；这些属于合成技术传播证据。

### 15.4 当前执行与综合验收

只复用已有 `E:\Personal Manager\Visory\.venv\Scripts\python.exe` 及已安装依赖，以下仓库命令 cwd 均为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。数据库复用已有 `postgres:16`，`--pull=never`、tmpfs、随机 loopback 端口和 `visory_test_<20hex>` 临时库；没有连接业务库或拉取镜像。完整 argv、cwd、退出码、日志与 XML 保存于本节证据目录，各次运行是重叠的独立验证，不能相加为独立测试覆盖。

定向 runner 首次 preflight exit 1、测试数 0：误填不存在的 `tests/platform/test_feature_dependency.py`。检索确认 DAG/Resolver 反例就在仍保留的 `test_indicator_registry.py`，仅修正仓库外命令列表，未删测试/断言或加 skip。失败事实保存为 `targeted-preflight-failure.json`。

| 实际命令/范围 | 本轮结果 | 证据与限制 |
| --- | --- | --- |
| `audit_source_admission.py`，19 个固定源文件/8 个 CSV 的字节、完整行、旧输入拒绝及 Definition 载荷核验 | exit 0；18,616 行；8 个 CSV 正式输入 NO_GO | `source-admission-current.json`；没有新增正式输入 |
| `python -m pytest`，13 个 Market/Adjustment/N2/Registry/DAG/FeatureStore/Snapshot/Golden/Hash/消费定向文件 | **exit 0；510 passed / 0 skipped**；pytest 25.53 秒 | `targeted.json/log`、`targeted-junit.xml`，完整文件/参数在 argv |
| `python -m pytest`，7 个独立 PostgreSQL 文件 | **exit 0；66 passed / 0 skipped**；pytest 103.26 秒 | `postgres-required.json/log`、XML；包括两项独立 Python PID 的固定消费/合成 Correction |
| `python scripts/export_platform_contracts.py --check` | 首次及文档收尾均 exit 0 | `contract-export.json/log`、`contract-export-final.json/log`；无生成契约变化 |
| `python scripts/check_ai_assets.py` | 首次及文档收尾均 exit 0 | `governance.json/log`、`governance-final.json/log` |
| `python scripts/check_visory_baseline.py` | 首次及文档收尾均 exit 0；首次 663/最终 664 个相对链接，0 断链 | `baseline-check.json/log`、`baseline-final.json/log` |
| `python -m py_compile`，六个相关运行模块 | exit 0 | `py-compile.json/log`；字节码前缀在仓库外 |
| `python -m flake8 --select=E9,F63,F7,F82,F401,F821`，同六个模块 | exit 0 | `critical-lint.json/log`；无代码修改，不用删断言或 broad fallback 通过 |
| `bash scripts/ci_gate.sh all`，修正临时路径后的完整 gate | **pytest 7363 passed / 85 failed / 10 skipped / 4 deselected / 76 warnings / 572 subtests passed**，747.19 秒；外层 runner exit 1（KeyboardInterrupt），**Bash 退出码未取得** | `full-gate-corrected.log`、XML、`full-gate-corrected-interrupted.json`；完整 gate 未通过 |
| `git diff --check` | 首次及文档收尾均 exit 0 | `diff-check-final.json/log`；untracked 文档增量还由 `incremental.patch` 反向检查覆盖，不用 HEAD diff 冒充本次增量 |
| `git -c http.connectTimeout=10 -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 ls-remote origin refs/heads/main` | **收尾 exit 0**，仍返回 `efe8e9b362cba13eca183c55be57bbbbc832b60b` | `remote-closing.json/log`；仅 ref 读取，不 fetch/pull，不证明 dirty 增量的 CI 或生产就绪 |

完整 gate 使用 Git Bash，并导出 `python/python3` 函数指向上述已有解释器，`flake8` 调用该解释器的 `-m flake8`。`PYTEST_ADDOPTS` 的最终 cache/basetemp/XML 路径使用正斜杠并经 `shlex.join/split` 往返断言，均在仓库外；没有 shard 或新 skip。

保留首轮 gate 的执行问题：Windows 反斜杠在 `PYTEST_ADDOPTS` 的解析中丢失，临时产物落在累计目录的本轮专属新路径；完整行/文件清单及 **1663 个文件 Hash** 先保存，再用核验过绝对范围的 PowerShell `Move-Item -LiteralPath` 移到仓库外 `first-gate-artifacts/`。未删除或移动任何开工成果、旧参考验收缓存或真实 `/data`。首轮日志为 7364 passed / 84 failed / 10 skipped / 4 deselected / 76 warnings / 572 subtests passed，838.77 秒；外层也在 subprocess wait 出现 KeyboardInterrupt，Bash 退出码未捕获。`first-gate-path-incident.json`、`first-gate-results-and-repair.json` 和 `full-gate-interrupted.json` 保留原问题；不以该轮替代修正后的结果。

修正后 85 个失败的实际分布：agent backend status 14、Codex App Server 31、Codex tool process 12、local CLI 10、LLM usage 5、storage 6、runtime scheduler 2；intelligence/provider cache/screening/search concurrency/system config 各 1。可见反例包括 native Windows 的 `platform_unsupported`、`os.killpg/getpgid` 不存在、POSIX 权限断言、WinError 32 和超时/服务断言；完整节点/消息保存在 `verification-results-analysis.json`。涉及文件本轮原字节未改，但未执行开工全套对照，不据此断言每项失败必为既有问题。没有为绿灯修改这些模块、断言、Golden 或依赖。

10 个 skip 均来自既有 Windows 边界：4 个 symlink 权限、1 个 POSIX mode、2 个 Codex native Windows、3 个 POSIX 进程组/会话隔离。4 个 deselected 是原 gate 的 `not network` 选择。本 WP 的 13 个定向模块和 7 个 PostgreSQL 模块在修正后完整 XML 中合计 **576 个测试全部 passed，0 failed/0 skipped**；`required_module_coverage` 列出每个模块，未把 10 个 skip 算入必需路径通过证据。

两个本轮隔离容器分别为 `visory-wp0303-input-resume-7d26cefc55b6` 与 `visory-wp0303-input-corrected-95315b8bc112`，finally 的 docker stop 分别 exit 0；`--rm` 容器和 tmpfs 已回收，两个密码/env 文件组已删除。`local-resource-reclamation.json` 通过 docker ps exit 0 确认二者不存在，本轮路径/命令过滤未找到遗留测试进程。**中断使停库前的剩余测试库计数未执行**，不伪造 `remaining_test_databases=0`；容器删除证明资源已回收，不替代该计数查询。API/客户端字节没有本次增量，未补客户端构建；真实源修订、历史 PIT 和生产运行验收仍未执行。

### 15.5 当前判定、阻断和回滚

| WP-0303 验收项 | 本次判定 |
| --- | --- |
| 开工保护、唯一目录、实际样本字节/完整行 | 19 个固定源文件/8 个 CSV 已核验；1560/1509 个非本次文件与 HEAD/index/status 不变；四文档 allowlist/原字节前缀、旧载荷与反向检查均通过，见 `final-protection.json` |
| B1 PIT 流通市值 | BLOCKER：32 行零资本字段及单位/口径/历史覆盖/可用性不足；NO_GO |
| B2 正确历史股本 | BLOCKER：A/H 分母、单位、生效/观察时钟及重复/revision 未闭合；NO_GO |
| B3 正式行动/因子 Dataset 与存储派生闭包 | BLOCKER：税/旧股基数、身份、revision/cancel、全类型/覆盖/时间及 P 未证明；NO_GO |
| B4 停牌引用 | 保留既有 2.0.0 子项，不重复实现；整体未关闭 |
| B4 基准/首封 | BLOCKER：两基准指标和首封仍 FIXTURE_ONLY |
| 历史冻结股票池、37 个实际原始量及五维完整计算 | BLOCKER：16 EXECUTABLE / 18 BLOCKED / 3 FIXTURE_ONLY 保持；实际全市场未认证 |
| T-1/warmup/断点、参数/权重/方向/Hash | 既有技术定向回归通过、旧载荷 Hash 不变；完整实际输入区间仍未认证，不重加权或补零 |
| B5/N1/N2、固定发布/重启/失败回收/Correction | 510/66 定向通过且无 skip；仅复用隔离技术链，不认证真实来源修订；数据库资源回收已核验，停库前计数因中断未执行 |
| 生成契约/治理/编译/lint/diff | 已执行且 exit 0；文档收尾契约/治理/664 个链接/diff 亦 exit 0；增量反向检查 exit 0 |
| 完整 gate | BLOCKER：85 failed，Bash 退出码未捕获；必需 576 个测试 passed/0 skipped，不能代替完整 gate 通过 |
| 远程 CI/合入、生产 | 未执行；本轮本地命令基于 detached HEAD 加 dirty 成果，远端历史 CI 不覆盖该增量；实时 main 收尾仍为同 SHA |

**完整 Goal 仍 PARTIAL，真实输入步骤 BLOCKED，WP-0303=IN_PROGRESS、15/45，market_breadth/market_emotion=missing，Formal 拒绝，NOT CERTIFIED、RELEASED=false。** B1—B4 本轮新增整体关闭项为 0；B4 停牌 2.0.0、B5、N1/N2 是既有成果。来源 gate 不满足时不能用新增代码量或局部测试关闭 WP；必须取得第 9.1 节具体材料后才继续正式输入与派生接入。前三个已结束回合与本轮均未取得历史版本/身份/覆盖/可用性证据，记录于 `goal-history-blocked-audit-confirmed.json`；后续推进依赖真实材料或来源证据变化，不重复搜索或构造 fixture 冒充历史归档。FOLLOW-UP 是来源通过及本地验收闭合后的远端合入和生产运行验收，均需独立授权，不扩展相邻 WP。

回滚只针对本次四份文档 opening→final 的增量 hunk；独立 `incremental.patch`、final Hash、`git apply --reverse --check` 的 exit 0 和 52 项旧成果清单保存于本节仓库外证据目录。来源/实施记录原字节前缀保留，累计目录除四文档外的 1560 个、主 checkout 的 1509 个 Git 可见文件与开工逐字节一致，两边 HEAD/index/status 不变；完整载荷和源文件核验见 `final-protection.json`，忽略环境/cache 文件不在该清单内。先核对后续编辑/引用再手工合并反向 hunk，不整文件 restore、不删除原有 untracked 成果，不 reset/clean/stash，不改 0014/0015/Golden/旧固定分区，不批量清理参考目录。没有执行回滚、commit/tag/branch/push/PR/merge/fetch/pull、生产调度/部署/发布；无本轮远程 CI，历史提交证据不能覆盖未提交增量。

<a id="github-new-source-resume"></a>
## 16. 2026-10-14 第二批 GitHub 检索与续跑：PARTIAL

### 16.1 当前范围与保护

用户再次授权通过 GitHub 查找相关资料并继续 Goal。本轮实际进行了新的定向搜索、7 个新候选仓库的固定 commit/完整树检索和新文件下载，没有重复旧 8 CSV 作为新成果。只在 `C:\Users\lzq11\.codex\worktrees\f468\Visory` 追加来源与实现记录、状态路由和 CHANGELOG；独立参考归档为 `E:\Personal Manager\参考项目\WP0303-GITHUB-EVIDENCE-20261014-121647`。

新开工证据目录：`C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-GITHUB-RESUME-20261014-121443`。`worktree-opening.json`/`main-worktree-opening.json`、原字节 `opening-files/` 和两份 binary diff 重新绑定本轮基线：累计目录 **24 tracked modified + 28 untracked = 52 项旧成果、1,564 个 Git 可见文件**；主目录 **1,509 个 Git 可见文件**，仍 `codex/wp-0207-backfill@528baa072d32f0242cfdcfa8bb7b1314de19db78`，3 个旧文档修改。上一轮四文档增量属于本轮既有成果，不能借本轮回滚撤销。

HEAD 仍为 detached `efe8e9b362cba13eca183c55be57bbbbc832b60b`；本轮开工 `git ls-remote --heads origin refs/heads/main` exit 0，实时 main 同 SHA。只读取 refs，没有 fetch/pull 或修改主 checkout。

步骤保持可回滚：①来源/输入门禁（实际推进）；②正式派生发布（等待①）；③固定消费/真实 Correction（等待①②）；④完整综合验收（尚未满足）。缺来源证据时只修改步骤①需要的文件，不通过改标签/构造 fixture 进入②③。

### 16.2 新发现及采用决定

来源、固定 commit/文件、字段/数值反例、具体决策与最小材料只在[来源记录第 10 节](WP-0303-B3-SOURCE-EVIDENCE-PREP.md#github-new-source-search)维护。本轮 **154 来源文件、102 CSV、208,612 行**实际核验；Git blob/SHA256/大小均匹配，0 下载失败。CNEquity/TDX 的代码可参考不同口径与时间/质量约束，不认证其未随仓库交付的数据湖/GBBQ 历史。

quant-data 的 103,735 个行情诊断配对全部有 CN/US 标签冲突；90,628 个换手率值只匹配总股本分母，ext 另有 16 个无 raw 对应日期键。LUEIG 为昨日涨停池/昨日封板时钟，其 15 行 baseline 不是固定 PRICE 指数。KPL-post 的 66/56 个请求均无保存响应。A_stock 与 free-data 的实际原始库在作者外部目录而非所查 GitHub 树中。新增公告号/PDF Hash 索引只是可追索声明，原 PDF/初版/观察日志未取得，不称真实修订认证。

因此 **没有新增正式放行或 B1—B4 整体关闭项**。不追加未收敛 Dataset/Raw Schema/Mapping/质量/引用/Definition 或 Migration；不修写样本标签、用总股本换手、反推股本、补因子 1、补未知行动 0 或使用 latest。旧 14 F1、65 F2、旧版本/Hash/Golden/固定引用、0014/0015、B5/N1/N2 原成果保持。N2 仍明确 fixture-only，不改名称、模式或证据等级。

### 16.3 本轮增量职责与实际链路

| 本轮修改的完整绝对路径 | 职责 / 原因 |
| --- | --- |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\WP-0303-B3-SOURCE-EVIDENCE-PREP.md` | 追加第 10 节：7 个新来源、实际样本门禁、公告索引与具体最小材料，不重写前轮来源结论 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\WP-0303-IMPLEMENTATION.md` | 追加本节：本轮基线、步骤、实际命令/验收、风险与独立增量回滚 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\architecture\a-share-platform\IMPLEMENTATION-STATUS.md` | 增加当前摘要与 WP-0303 第 16 节路由，不提升 WP 计数/认证 |
| `C:\Users\lzq11\.codex\worktrees\f468\Visory\docs\CHANGELOG.md` | Unreleased 追加一条扁平记录，明确新数据反例与真实链停点 |

这些文件本来就在 52 项旧成果中；其余代码/Schema/迁移/测试都是既有修改，不计本轮新增实现。参考目录中来源文件的完整绝对路径/职责通过下载 Manifest 与审计包逐一保存；仓库外 helper 只读下载文件、执行校验和保存结果，不是运行时依赖。中文 WP 记录没有对应英文副本；没有公共 API/客户端/README 增量。

本轮实际链路：**GitHub 定向搜索 → 固定 commit/tree/blob → 下载文件实际字节/Hash → 完整 CSV 行、显式日期键配对、身份/分母/覆盖/时钟门禁 → NO_GO**。链路尚未进入正式 Raw/Canonical/Snapshot，因此没有“真实输入 → 复权/37 原始指标 → 正式 DERIVED/FeatureStore → 固定 FeatureBundle”的完整新执行。B5 的真实隔离 PostgreSQL 技术闭包与 N1/N2 既有验证保留；本轮不将它们重新计作生产输入认证。

### 16.4 本轮实际命令与结果

命令均以累计目录为工作目录，解释器复用 `E:\Personal Manager\Visory\.venv\Scripts\python.exe`。命令参数数组、时钟、cwd、退出码和完整日志在 `checks-index.json` 与各 `.result.json/.log`；下载脚本和 raw GitHub 请求仅访问 GitHub 公开文件/API。

| 实际命令 / 过程 | 本轮结果 |
| --- | --- |
| 仓库外 `download_references.py`、`download_ext_samples.py` 和补充下载 | exit 0；分别 101/50/3 文件，固定 commit/blob/大小/SHA256；154 个文件合计 18,969,958 bytes |
| 仓库外 `audit_new_sources.py` | exit 0；102 CSV/208,612 行完整检查，7 个候选包均无正式放行；报告 `source-admission-new.json` |
| `python -m pytest -q tests/platform/test_wp0303_input_closeout.py tests/platform/test_wp0303_reference_semantics.py`（cache/basetemp/XML 全在仓库外） | **exit 0；14 passed / 0 failed / 0 skipped**；复验旧输入拒绝、显式停牌版本、参考字段拒绝与固定消费门禁，不代替全 WP 验收 |
| `python scripts/export_platform_contracts.py --check` | exit 0；没有新生成契约 |
| `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | 各 exit 0 |
| `python -m py_compile`，market_sentiment / adjustment_calculation / indicator_registry / feature_store / feature_dependency / adjustment 六模块 | exit 0；pycache 在仓库外，无运行代码变更 |
| `gh api repos/yutianlzq/Visory/actions/runs?head_sha=efe8e9b362cba13eca183c55be57bbbbc832b60b&per_page=10`，只读投影 | exit 0；Run 37645716721 为 main / efe8e9b… / workflow_dispatch / completed / success，创建于 2026-10-07T15:39:45Z；只覆盖旧提交 |

本轮没有代码增量，未新增测试、重复创建 PostgreSQL 或重跑十余分钟 all gate/客户端构建；相关 lint、文档链接、diff 和增量反向检查的最终结果单独保存在收尾证据。第 15 节 **510/66 passed** 与完整 gate **7363 passed / 85 failed / 10 skipped / 4 deselected、外层中断未取得 Bash 退出码**仍是上一轮结果，不能写作本轮通过。全量 gate 未通过的 BLOCKER 保留；不以本轮 14 个测试替代必需全套路径或改动失败断言。

收尾 critical flake8（六模块，E9/F63/F7/F82）、生成契约/治理/baseline、`git diff --check` 与 `git apply --reverse --check` 均 exit 0；四份文档相对路径检查 **78 个、断链 0**，新手工锚点亦核验。旧 14 F1/65 F2 的版本、Definition Hash 和 canonical 完整 payload SHA256 与前轮 final 基线逐项一致。兼容性辅助脚本首次误用 `.items()` 集合求并触发 `TypeError: unhashable type: 'dict'`（exit 1）；修正为字典合并并使用既有 `canonical_json_bytes` 后 exit 0、79 项一致，未修改运行代码或断言；错误及修正结果保留在本轮仓库外记录。

### 16.5 验收矩阵、风险、回滚与 Git 状态

| 验收项 | 当前判定 / 本轮边界 |
| --- | --- |
| 工作区保护、来源字节、完整行集合 | 新基线、154 文件 Hash/大小、102 CSV/208,612 行已实际核验；收尾逐文件与增量 hunk 检查见 `final-protection.json` |
| B1 PIT 流通市值 | **BLOCKER / NO_GO**：新增历史数值仍缺正确身份、口径、历史覆盖/观察可用性；不采用估算或替代 |
| B2 正确历史股本与换手率 | **BLOCKER / NO_GO**：总股本分母数值反例、流通/自由流通与 A/B/H、迟到/修订时钟未闭合 |
| B3 事件/原始覆盖/正式因子/派生持久化 | **BLOCKER / NO_GO**：只有契约/案例索引，原 PDF、真实 revision/cancel、全类型/无行动/全页/时钟与 P 仍缺；不冒充已取得源修订 |
| B4 剩余 F1、两基准/首封 | **BLOCKER**：整体未关闭，三原始量仍 FIXTURE_ONLY；已完成停牌 2.0.0 子项保留 |
| 历史冻结池、37 真实原始量、五维/总分/平滑/状态 | **BLOCKER**：16 EXECUTABLE / 18 BLOCKED / 3 FIXTURE_ONLY 保持；真实完整计算和区间未认证，缺必需值仍缺失 |
| T-1/warmup/断点、版本/权重/方向/Hash | 既有代码/参数保留，14 项入口回归通过；全真实输入路径仍未验收，不临时重加权 |
| 固定 Raw/Canonical → DERIVED → Repository 重启 → F1/F2 → Bundle | **BLOCKER**：新来源被输入门禁拒绝，正式计算/发布/重启消费未启动；B5/N1/N2 隔离技术结果不扩大证明范围 |
| 原子发布/失败回收/同身份 Correction / 新 cutoff / 后续窗口与状态传播 | 复用既有隔离证据；**真实来源修订 E2E 未验证**，不称合成输入或 Git 文件变化为 Provider Correction |
| 生成/治理/编译/入口回归 | 本轮命令 exit 0，14 passed/0 skipped；完整 gate 阻断保留，API/客户端无增量 |
| 本地完整验收 / 远端合入 / 生产认证与发布 | 本地 **PARTIAL**；未执行新远端 CI/合入或生产操作；**NOT CERTIFIED、RELEASED=false** |

FOLLOW-UP：来源/本地验收满足后，经独立授权再执行远端 CI/review/合入与生产运行/恢复验收。本 WP 不包括外部数据采集服务搭建、相邻 WP、Hikyuu、市场页面或 Paper Portfolio；不因参考项目包含这些功能扩大范围。

回滚只合并本轮四文档 `opening → final` 增量的反向 hunk；前轮四文档、52 项旧成果、0014/0015/旧 Golden 和固定引用均须保留。`incremental.patch`、源/实施记录旧字节前缀校验、四文件 allowlist、主目录/其他文件 Hash、HEAD/status/index 与 reverse check 的收尾结果保存在本轮证据目录；没有实际执行回滚。参考目录是独立新归档，可保留作审计，不能批量删除原参考项目。完整 Goal 仍 **PARTIAL，WP-0303=IN_PROGRESS、15/45、两市场 missing、Formal 拒绝**；未 commit/tag/创建 branch/push/PR/merge/fetch/pull、真实 Provider/生产数据库/真实 `/data`、生产调度、部署或发布。基线 CI 不覆盖 dirty 成果或本轮增量。

<a id="issuer-static-evidence-resume"></a>
## 17. 2026-10-14 固定 GitHub 索引到发行人更正原文：PARTIAL

### 17.1 本轮动作、开工保护和实际链路

只读复用第 16 节 `rootSunc/CNEquity` 的固定代码索引，继续检索公开发行人原文，实际取得 CNINFO 两份初版/更正版 PDF、每份 5 页，合计 **1,222,359 bytes**。首次下载与再次定时读取所得 PDF 字节完全一致，初版 SHA256 与 GitHub 索引精确匹配。两个 SSE 静态镜像均返回非 PDF HTML，已保留拒绝响应和 Hash，不执行页面脚本、不绕过校验。四个关键页面实际渲染并视觉核对，所有 10 页文本已抽取检查。来源语义、参考规则反例、具体 Method 决策及拒绝原因以[来源第 11 节](WP-0303-B3-SOURCE-EVIDENCE-PREP.md#issuer-static-correction-evidence)为权威记录。

公开资料与审计文件：`E:\Personal Manager\参考项目\WP0303-ISSUER-EVIDENCE-20261014-125938`；新开工保护、辅助命令、结果和日志：`C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-ISSUER-EVIDENCE-20261014-125938`。本轮修改前保存 f468 **1,564** 个、主目录 **1,509** 个 Git 可见文件的原始字节和逐文件 Hash，以及完整 binary diff、HEAD/branch/status/index listing。忽略的环境/缓存不计入；主工作树未写入。本轮开工与上一轮 final 的全部 Git 可见字节一致，未发现他人改动；回滚基线使用本轮开工字节，不使用前轮 opening。

当前四个可回滚步骤：输入契约/来源 gate 为 **PARTIAL / NO_GO**；正式派生发布、固定消费、真实 Correction 综合验收均被上一步阻断。本轮只修改来源记录、本实现记录、IMPLEMENTATION-STATUS 和 CHANGELOG，不新增正式 Dataset/Raw Schema/Mapping/质量或 Method/Definition 版本。

实际新增链路：“固定 GitHub 索引 → 当前获取的发行人初版/更正版 → 实际 Hash、税/基数/日期与版本差核验 → **正式来源 gate 拒绝**”。没有将当前下载时间回填为 2024 年 `available_at`，未进入合法 Raw/Canonical/Snapshot 或 DERIVED/FeatureBundle，未把发行人静态更正样本描述为 Provider 真实 Correction 传播认证。

### 17.2 实际命令、结果和错误范围

下表命令工作目录均为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`；辅助脚本在本轮仓库外保护目录，参数、cwd、时钟、退出码和原日志保存于 `checks-index.json`、`validation.log`、`source-audit.log` 和 `compatibility-final.log`。产品 Python 复用 `E:\Personal Manager\Visory\.venv\Scripts\python.exe`；PDF 审计使用桌面内置 Python/pypdf/pdfplumber。没有安装/升级依赖，pycache、pytest cache/basetemp/XML 均在仓库外。

| 实际命令 / 过程 | 本轮结果与限制 |
| --- | --- |
| `git status --porcelain=v1 -uall`、`git rev-parse HEAD`、`git branch --show-current`、`git ls-remote --heads origin refs/heads/main`、`git ls-files --cached --others --exclude-standard -z`、`git diff --binary HEAD --` | 开工读取及保护成功；f468 detached `efe8e9b362cba13eca183c55be57bbbbc832b60b`，实时远程 main 同 SHA；主目录 `codex/wp-0207-backfill@528baa072d32f0242cfdcfa8bb7b1314de19db78` |
| 四 URL `Invoke-WebRequest`，随后内置 Python `audit_issuer_sources.py` 重新定时读取及 pypdf/pdfplumber 审计 | 审计脚本 **exit 0**；两 PDF Hash/实际字节/5 页/语义断言通过，4 页渲染视觉通过；两镜像 **REJECTED_NON_PDF**，不计为输入。Manifest 的本次 acquired_at 不等于历史可用时间 |
| `python -m pytest -q tests/platform/test_wp0303_input_closeout.py tests/platform/test_wp0303_reference_semantics.py`（仓库外 cache/basetemp/XML） | **exit 0；14 passed / 0 failed / 0 skipped**；只复验旧输入拒绝、显式停牌版本及参考/固定消费门禁，不认证新 PDF 的生产来源 |
| `python scripts/export_platform_contracts.py --check` | **exit 0**；没有新生成契约 |
| `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | 各 **exit 0** |
| `python -m py_compile`：market_sentiment、adjustment_calculation、indicator_registry、feature_store、feature_dependency、adjustment 六模块 | **exit 0** |
| `python -m flake8` 上述六模块 `--select=E9,F63,F7,F82 --show-source` | **exit 0** |
| `gh api repos/yutianlzq/Visory/actions/runs/37645716721 --jq '{id,head_sha,head_branch,status,conclusion,created_at}'` | **exit 0**；run completed/success，创建于 2026-10-07T15:39:45Z，head 为 efe8e9b…；只覆盖旧提交，不覆盖全部 dirty 成果或本轮文档 |
| 仓库外 `run_validation.py --compatibility-only` | **exit 0**；旧 14 F1/65 F2 版本、Definition Hash、canonical 完整 payload SHA256 与上一轮 final 逐项一致 |

失败保留：首次 PowerShell 把 SSE HTML 当字节传给 WriteAllBytes 的转换错误被捕获，没有写成 PDF；随后用原始响应字节、Content-Type 和 `%PDF-` 联合核验，两个非 PDF 均保留为 `.rejected-response.bin`。一次 `Get-FileHash -LiteralPath ...\*.pdf` 辅助读取因 LiteralPath 不展开通配符退出 1，后续逐实际路径核验成功。两次 apply_patch 调用分别因上下文尾句不完全匹配、传入 JSON 而拒绝，没有写入仓库；改为精确上下文和工具 freeform 后成功。首轮 `run_validation.py` 的七个实际检查均通过，但辅助兼容性比较误用 `model_dump(mode="python")`，与原 `mode="json"` 基线不一致，包装脚本最终 exit 1；对齐原序列化后仅重跑兼容性比较并通过，保留初版比较和日志，不改旧断言/Golden/产品代码。一次定点 rg 指定了不存在的 hash.py/common.py 和 Literal 通配路径，补正为实际 hashing.py/目录后读取成功。这些是辅助操作问题，不描述为产品回归失败，也不隐藏原错误。

本轮没有重新创建隔离 PostgreSQL、运行完整 Market/Adjustment/Registry/FeatureStore 套件、all gate 或客户端构建：没有运行代码/接口/生成客户端增量，且来源仍 NO_GO。第 15 节的 **510/66 passed** 与 **7363 passed / 85 failed / 10 skipped / 4 deselected（外层中断，Bash 退出码未知）**是历史结果；完整 gate 未通过仍为 BLOCKER，不以本轮 14 项替代全套验收。

收尾辅助脚本首轮把换行分隔的 `git ls-files --stage` 与前轮 NUL 分隔的 `--stage -z` 原日志直接比较，触发断言/exit 1；两边分隔形式不同，不能据此推断 index 被修改。改为原 `-z` 命令后核对实际字节；首轮日志保留于 `closeout-validation-initial.log`，最终结果以 `final-protection.json` 为准。

### 17.3 逐项验收、兼容性与本轮增量回滚

| 验收项 | 当前结论 / 本轮增量 |
| --- | --- |
| B1 PIT 流通市值、真实单位/价格基准/历史覆盖 | **BLOCKER / NO_GO**；本次公告不提供合格流通市值 Raw，不使用总市值或估算替代 |
| B2 A 股正确历史股本与换手率分母 | **BLOCKER / NO_GO**；参与分配股本不是逐日换手率流通分母；不向旧 security_master 填 shares_outstanding |
| B3 事件、税/共同旧股基数、revision/cancel、覆盖与时间 | **PARTIAL EVIDENCE / NO_GO**；新获一个初版→更正版发行人案例；Provider Raw、历史 observed/available_at、全类型/全页/合法零行动/取消及固定 P 仍缺；差异化分红 Method 决策尚未收敛 |
| B4 旧 F1 引用残余及三 FIXTURE_ONLY 原始量 | **BLOCKER**；无新合法首封/基准/冻结池来源；保留已完成停牌 2.0.0 子项 |
| 37 原始量、分母/覆盖、五维/总分/平滑/状态的实际输入计算 | **BLOCKER**；仍 16 EXECUTABLE / 18 BLOCKED / 3 FIXTURE_ONLY；EXECUTABLE 不代表历史认证；28 DERIVED 与固定参数/权重/方向/Hash 保留 |
| T-1、warmup、缺失断点与状态迁移 | 既有算法和入口回归保留；全真实输入区间 **未认证**，不补零、前值延用或临时重加权 |
| Raw/Canonical/Snapshot 实际字节 → DERIVED 发布 → Repository 重启 → F1/F2 → 固定 Bundle | **BLOCKER / 新来源未启动**；B5/N1/N2 既有技术证据保留，FixtureExecutionLineageBridge 不改标签 |
| 真实 PostgreSQL 原子发布/失败回收/固定消费与 Correction 后续传播 | 本轮 **未重跑**；既有隔离/合成 Correction 结果不认证发行人/Provider 真实修订传播 |
| 旧 14 F1/65 F2、0014/0015、Golden/Hash/固定引用 | **保留**；完整载荷逐项比较通过，实际存储/运行文件无本轮增量 |
| 生成/治理/编译/lint/入口回归 / 完整 gate | 本轮定向通过；历史完整 gate **BLOCKER 未解除**；未改 API/客户端，无新构建 |
| 本地完整验收 / 远程合入 / 生产认证与发布 | **PARTIAL / 未合入 / NOT CERTIFIED**；WP-0303=IN_PROGRESS、15/45，两市场 missing，Formal/Paper 拒绝，RELEASED=false |

B1—B4 本轮新增整体关闭项仍为 **0**；仅来源发现/初版 Hash/发行人版本差这一子证据完成。FOLLOW-UP 为来源和本地完整验收通过后的远端 CI/合入与生产运行认证，须独立授权；不扩展相邻 WP、Hikyuu、市场页面或 Paper Portfolio。没有英文对应专题页，本轮只更新中文内部验收记录，不修改英文产品文档。

主要风险：把当前取得的静态原文当历史 PIT；把初版 Hash 匹配当版本选择充分证明；混用实际现金/虚拟除息值/税后值；将单事件参与股本当 B1/B2 全市场历史输入。收尾文件 Hash、文档链接、四文件 allowlist、HEAD/status/index、增量反向检查及主目录字节保护见本轮仓库外 `final-protection.json` 和 `incremental.patch`。仅反向合并本轮四文档的 hunk；有后续改动时人工合并，不整文件 restore，不删除前轮 dirty/untracked 成果，不触碰主目录。参考归档单独保留，不是可执行运行依赖。

本轮未 commit/tag/创建 branch/push/PR/merge/fetch/pull，未访问真实 Provider 业务 API、生产数据库或真实 `/data`，未执行调度、部署、发布或回滚。完整 Goal 仍 PARTIAL，不标 complete。

<a id="public-history-evidence-resume"></a>
## 18. 2026-10-14 公开历史材料、覆盖和股本更正增量

用户授权继续 GitHub/公开来源检索、下载到参考目录及有条件推进 WP-0303。唯一修改目录仍为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`；本轮开工保护目录为 `C:\Users\lzq11\AppData\Local\Temp\Visory-WP0303-PUBLIC-HISTORY-20261014-150613`，参考资料目录为 `E:\Personal Manager\参考项目\WP0303-PUBLIC-HISTORY-20261014-150613`。主目录只读、参考源码不执行、不安装依赖；不访问 Provider 业务 API、生产 DB 或真实 `/data`。

### 18.1 实际增量与来源门禁

来源事实的权威记录为[来源证据第 12 节](WP-0303-B3-SOURCE-EVIDENCE-PREP.md#public-history-coverage-evidence)。本轮新取得 201 个固定 GitHub 文件和 3 份官方 PDF；完成逐文件字节/Hash、9 证券完整系列/同键配对、全目录 cohort 对齐、79 个日期首封榜截断、官方 301061 初版/更正的核验。没有将月频因子、处理榜单、当前历史下载、公告落款或 Git/Actions 时钟提升为 PIT。

B1/B2 新材料支持在声明单位假设下的数值核验；B3 支持一个实施前/后股本更正案例；B4 新取得首封和指数历史样本，但范围/时钟/固定 PRICE 仍未闭合。全部正式来源继续 **NO_GO**，整体新增关闭项 **0**。未追加 Dataset/Raw Schema/Mapping/质量/Definition、Method、Migration、派生或消费者代码；保留停牌 2.0.0、旧 14 F1/65 F2 完整载荷/版本/Hash/Golden/固定引用、0014/0015 和全部 B5/N1/N2。

本次四份既有文档最小同步：来源证据本节所链第 12 节、实现记录本节、IMPLEMENTATION-STATUS 顶部摘要和 CHANGELOG 扁平 Unreleased 一条。其他既有 dirty/untracked 不是本轮修改，没有对应英文内部专题页，未改英文产品文档。

### 18.2 命令、证据和验收边界

开工保存 f468 1,564 个、主目录 1,509 个 Git 跟踪/非忽略未跟踪文件的原始字节/Hash，以及 HEAD/branch/status/index/binary diff。首次 ls-remote exit 128 的错误保留；随后实时重试 exit 0，远程 main 与 detached HEAD 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。主目录为 `codex/wp-0207-backfill@528baa072d32f0242cfdcfa8bb7b1314de19db78`，未更改。

实际下载/失败/重试由参考目录各 Manifest 记录：选中文件最终 201/201 取得；单份 CDN 失败经 Git Blob API 正常读回，Hash 匹配；公开源码的一项凭证样式字面量脱敏，源与本地 Hash 区分。GitHub Actions 日志 403 和两个元数据访问失败保留，不绕过或归为“没有历史”。官方 PDF 8 个文件页提取、5 个独立关键页渲染/视觉检查；镜像字节相同，只计 2 个内容版本。

本轮验收使用主目录既有 `.venv\Scripts\python.exe`，工作目录为 f468，未运行参考源码：

| 实际检查 | 结果与用途 |
| --- | --- |
| 仓库外 `verify_protection.py ... preedit` | exit 0；修改前两目录全部文件/HEAD/branch/status/index 与开工一致 |
| 仓库外 `audit_public_history.py <参考目录>` | exit 0；201 文件完整性、完整键集合与样本数值/覆盖审计；不是市场计算测试 |
| `python scripts/export_platform_contracts.py --check` | 检查生成契约无漂移；实际退出码/日志见本轮 `commands-final.json` |
| `python scripts/check_ai_assets.py`、`python scripts/check_visory_baseline.py` | 治理/基线检查；实际退出码/日志见本轮 `commands-final.json` |
| `python -m py_compile <本轮仓库外审计脚本>` | 仅审计脚本语法验证；未改产品 Python，无产品 lint 增量 |
| 文档相对链接/锚点、旧载荷字节与增量反向验证、`git diff --check` | 实际结果见 `commands-final.json`、`document-links.json`、`incremental.patch`、`rollback-check.json`、`final-protection.json` |
| 产品定向 pytest / 独立 PostgreSQL E2E / `bash scripts/ci_gate.sh all` / 客户端构建 | 本轮运行数量 **0**；只有来源/文档增量且没有合格正式输入，不重复前轮测试；完整 Goal 必需验收仍未满足，历史 85 failed 阻断不解除 |

命令的完整 argv、绝对工作目录、退出码与 stdout/stderr 保存于本轮仓库外日志；参考目录 `RESEARCH-REPORT.md` 汇总。本轮不将前轮 14/510/66 通过数计为新执行，也不通过 skip/mock/删除断言/修改 Golden 替代真实来源验收。

### 18.3 逐项判定与本轮回滚

| WP-0303 验收项 | 当前判定 |
| --- | --- |
| B1 PIT 流通市值 | **BLOCKER/NO_GO**；真实固定单位/口径/逐日观察与修订覆盖仍缺，样本数值相符不足放行 |
| B2 历史股本与换手分母 | **BLOCKER/NO_GO**；float/free 生效/观察区间、历史状态与正式口径仍缺 |
| B3 单位/税/旧股/事件/revision/cancel/P/覆盖/时钟 | **PARTIAL EVIDENCE/NO_GO**；官方初版→更正已取得，Provider 修订链、取消、全覆盖、历史 PIT 和固定 P 未闭合 |
| B4 旧 F1 残余及首封/两基准原始量 | **BLOCKER**；保留停牌 2.0.0；榜单截断、日期/触板范围和 PRICE 契约不足，仍 FIXTURE_ONLY |
| 冻结池、各分母/覆盖、37 原始量及五维/总分/平滑/状态 | **BLOCKER**；16 EXECUTABLE/18 BLOCKED/3 FIXTURE_ONLY 与 28 DERIVED 保留，实际历史完整计算未认证 |
| T-1/warmup、缺失断点、状态迁移与固定参数/权重/方向/Hash | 既有算法保留；全真实历史申请区间 **未验证**，不补零/延用/临时重加权 |
| 固定输入字节→正式 DERIVED→Repository 重启→固定 F1/F2/Bundle | **BLOCKER/新来源未启动**；当前链路止于来源审计，N2 fixture 收据不提升标签 |
| PostgreSQL 原子发布/失败回收/重启/真实源 Correction 后续传播 | 本轮 **未验证**；B5 和前轮隔离合成 Correction 技术证据保留，不认证发行人真实更正传播 |
| 兼容、Migration/Golden/Hash/固定引用保护 | 本轮代码/数据结构无增量，按文件 Hash 保留；0014/0015 不改 |
| 生成/治理/相对链接/增量保护 vs 完整验收 | 本轮按日志核验；完整 gate 和来源/端到端 **BLOCKER** 保留 |
| 本地/远程/生产 | **本地 PARTIAL、未合入、NOT CERTIFIED、RELEASED=false**；CI run 37645716721 success 属于 HEAD 基线，不覆盖 dirty 或本轮材料 |

风险集中在把静态历史包当 PIT、把当前 cohort 当冻结池、混用流通/自由流通分母或公告实施前/后股数、把截断榜当触板全集、把发行人更正当 Provider Correction。FOLLOW-UP 为来源和本地完整验收通过后的远端 CI/合入与生产认证，需独立授权；不推进相邻 WP/市场页面/Paper Portfolio。

收尾对比主目录全部字节、f468 四文件 allowlist 外全部字节和 HEAD/branch/status/index。只允许反向合并本轮 `incremental.patch` 的四文档 hunk；先 check，有后续改动时人工合并，不整文件 restore/reset/clean/stash、不删除既有成果。参考归档保留为仓库外证据，不成为可执行依赖。本轮未 commit/tag/建 branch/push/PR/merge/fetch/pull、调度、部署或生产操作；WP-0303=IN_PROGRESS、15/45，两市场 missing，Formal/Paper 拒绝，Goal 未 complete。

<a id="a-stock-data-architecture-adjustment"></a>
## 19. 2026-10-15 基于 a-stock-data 的 Provider/Adapter 架构调整：PARTIAL

用户要求基于 `simonlin1212/a-stock-data` 调整架构。唯一累计成果目录仍为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`；开工保护包 `E:\Personal Manager\参考项目\WP0303-PIT-TRACE-20261014-172547\architecture-adjustment-protection-20261015-152141` 已保存 52 项 dirty/untracked 的原始字节/Hash、tracked HEAD 字节、binary diff、状态和远程 ref。开工 detached HEAD 与当时实时 `origin/main` 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`。本轮不 reset/clean/stash/restore，不修改主工作树。

### 19.1 固定来源与架构决定

外部只读 clone 为 `E:\Personal Manager\参考项目\a-stock-data`，clean，固定 `29b07d2e37005b9fd568bca1262f6e572b5f9407` / V3.10.2 / Apache-2.0。GitHub API 同日确认默认分支仍指向该提交；一次直接 `git ls-remote` 因 443 连接失败退出 128，不据此声称远程变化。未执行外部仓库脚本、安装依赖或调用其 Provider 业务 API。

架构决定记录在 [a-stock-data Adapter Bundle 分层架构](WP-0303-A-STOCK-DATA-ADAPTER-ARCHITECTURE.md)：

```text
a-stock-data fixed commit = Adapter Bundle / implementation fingerprint
actual upstream + endpoint contract = Provider identity
Provider/Endpoint -> separate ProviderRun -> RawObject
  -> CanonicalPartition/Quality/Coverage -> DataSnapshot
  -> DERIVED -> Resolver/F1/F2 -> fixed FeatureBundle
```

现有 `a_stock_data@1.0.0` 及其 Golden/Policy/Schema/Mapping 只保留兼容，不原地改名或提升认证。腾讯、通达信、东财、巨潮、BaoStock、新浪、同花顺和交易所等来源后续分别注册 Provider/Endpoint；Bundle commit 只固定实现字节，不能充当数据 `available_at` 或 revision 证据。来源 fallback 必须拆独立 Run/Raw/Partition，`except -> []` 不能把失败变成零事件。

### 19.2 本次文件职责与链路停点

| 本次修改 | 职责 |
| --- | --- |
| `WP-0303-A-STOCK-DATA-ADAPTER-ARCHITECTURE.md` | 新增固定版本、Provider/Endpoint/实现指纹、fallback、能力等级、B1—B4 映射、最小材料和实施顺序 |
| `data-platform-and-canonical-contract.md` | 将 a-stock-data 明确为 Adapter Bundle，补实际 Provider/Endpoint 和兼容迁移边界 |
| `data-ingestion-and-snapshot-sla.md` | 要求换源拆分 ProviderRun/Raw/Partition/质量证据，拒绝异常空数组 |
| `reference-adoption-matrix.md` | 将参考角色从统一主 Provider 收敛为 Adapter Bundle reference |
| `market-sentiment-and-capital-flow-architecture.md` | 市场输入改为实际 Provider/Endpoint 独立认证，链接本次门禁 |
| `WP-0303-B3-SOURCE-EVIDENCE-PREP.md` | 追加固定仓库/函数证据、B1—B4 能力与缺口 |
| `WP-0303-IMPLEMENTATION.md`、`IMPLEMENTATION-STATUS.md`、`docs/INDEX.md`、`docs/CHANGELOG.md` | 同步实现记录、状态、路由和扁平变更记录 |

实际链路只推进到“固定 Adapter Bundle 字节 → 识别实际来源/Endpoint → 审核错误、覆盖、PIT 和 revision 语义 → 架构 gate”。因为没有 Endpoint 达到 `PIT_CERTIFIED`，未进入合法 Raw/Canonical/Snapshot、正式 DERIVED、FeatureStore 发布或真实输入消费；不新增公共 Schema、Dataset、Mapping、Definition、Migration 或产品代码。

### 19.3 B1—B4 与验收判定

| 验收项 | 本轮结果 |
| --- | --- |
| B1 PIT 流通市值 | 腾讯/东财当前字段和 BaoStock 历史序列仅为候选；历史流通市值版本/观察/修订/全覆盖缺失，`NO_GO` |
| B2 正确历史股本 | 当前股本和历史换手率不证明分母；A/B/H、限售/自由流通、生效/披露/PIT/revision 缺失，`NO_GO` |
| B3 公司行动/因子 | 东财/新浪/巨潮/mootdx 可用于字段、公告和对拍参考；事件/组件身份、revision/cancel、全页/零行动、PIT/P 缺失，`NO_GO` |
| B4 行情/状态/首封/基准 | 通达信包、BaoStock 状态、东财/同花顺首封和深交所日历是候选；历史逐日覆盖、零行/错误区分、榜单完整性和固定 PRICE PIT 缺失。停牌 2.0.0 既有子项保留，整体未关闭 |
| Provider→Raw→Canonical→Snapshot→Feature | **未启动正式新链路**；旧 B5/N1/N2 技术成果复用但不提升 fixture 标签 |
| 兼容性 | 旧 14 F1、65 F2、Hash、Golden、固定引用、0014/0015、B5/N1/N2 均保留 |

本轮新增整体关闭项为 **0**。市场宽度、37 原始量、五维/总分/平滑/状态的实际历史完整计算，真实 Source Correction 传播和正式 PostgreSQL 发布/重启消费均未因本次架构文档获得认证。

### 19.4 验证、风险与回滚

工作目录均为 f468，除 GitHub/参考仓库只读命令外：

| 实际命令 | 退出码 / 结果 | 说明 |
| --- | --- | --- |
| `gh api repos/simonlin1212/a-stock-data` 与 `.../commits/main` | 0；main=`29b07d2e...`，Apache-2.0 | 当前 GitHub 元数据读取，不是数据 API/PIT 证明 |
| `git ls-remote https://github.com/simonlin1212/a-stock-data.git refs/heads/main` | 128；443 连接失败 | 保留失败；GitHub API 和本地 fixed clone 提供替代只读证据 |
| `python scripts/check_ai_assets.py` | 0；`[ai-assets] OK` | 治理检查 |
| `python scripts/check_visory_baseline.py` | 0；685 个相对链接、broken=0、imported_secrets=0 | 仓库边界/链接/许可证检查 |
| `python scripts/export_platform_contracts.py --check` | 0；generated exports current | 证明本轮未引入生成契约漂移 |
| `git diff --check` | 0；只有既有 Windows LF→CRLF 提示 | tracked diff 空白检查；未跟踪文档另做原始字节检查 |
| 产品 pytest / PostgreSQL E2E / `bash scripts/ci_gate.sh all` / 客户端构建 | 运行数 0 | Docs-only 架构增量，没有合格输入或运行时代码；不重复前轮测试，不据此关闭完整 Goal |

主要风险是继续把 `a_stock_data` 聚合身份误当生产来源、把 Git commit/当前历史下载当历史 PIT、把内部 fallback 或空列表当合法零行、把当前股本/市值回填历史。后续实现必须通过追加版本完成，不能原地修改旧 Provider/Definition/Hash。

回滚只反向合并本轮十份文档的增量 hunk，并在操作前核对保护包和收尾 Hash；新文档只有在没有后续引用/编辑时才删除。不得整文件 restore、reset、clean、stash 或撤销开工 52 项成果。本轮未执行回滚、commit、tag、建 branch、push、PR、merge、fetch/pull、真实 Provider API、生产数据库、真实 `/data`、调度、部署或发布。

**完整 Goal 仍 PARTIAL/BLOCKED：WP-0303=IN_PROGRESS、15/45，market_breadth/market_emotion=missing，Formal/Paper 拒绝，NOT CERTIFIED、RELEASED=false。**

<a id="goal-realignment"></a>
## 20. 2026-10-15 完整 Goal 重排与 C-004 Endpoint Admission 下一任务：PARTIAL

### 20.1 开工保护与范围

唯一累计成果目录仍为 `C:\Users\lzq11\.codex\worktrees\f468\Visory`。本轮开工保护包为 `E:\Personal Manager\参考项目\WP0303-PIT-TRACE-20261014-172547\goal-realignment-protection-20261015-155324`：保存开工 56 项 dirty/untracked 的当前字节、tracked HEAD 字节、逐文件 SHA256、NUL 状态、binary diff 和实时远程读取结果。开工 detached HEAD 与实时远程 main 均为 `efe8e9b362cba13eca183c55be57bbbbc832b60b`；开工 diff 为 155,397 bytes，SHA256 `685d9d7dfde0e0f476d22f519f69b2e665efe3a7cf69a70b4fea7f742a937a81`。

本轮只调整架构、PREP、实现状态、索引和 CHANGELOG，并新增完整 Goal v2 文档。未修改产品 Python、JSON Schema、生成 Registry、Migration、测试或来源证据；不重复 B5/N1/N2，不修改主工作树。

### 20.2 架构调整

完整 Goal 的最终验收不变，只将后续执行重排为 A—E：A 为已完成的 Adapter Bundle/实际 Provider 分层；B 为下一可执行的 C-004 Endpoint Admission；C 为逐 Endpoint 真实来源准入；D 为 WP-0303 输入和派生；E 为固定消费、真实 Correction 和综合验收。

为保持旧字节和引用不变，阶段 B 不注册同名 `ProviderRun@2.0.0`，而纯追加：

```text
ProviderEndpointDefinition
AdapterImplementationFingerprint
SourceAdmissionReceipt
ProviderEndpointRunBinding
```

`ProviderEndpointRunBinding` 把旧 `ProviderRun`/`RawObject` 与实际 Endpoint、实现指纹和 Admission Receipt 绑定。未来 Formal 输入必须有相同 Dataset/schema/范围的有效 `PIT_CERTIFIED` Receipt；缺 Binding、Endpoint/Hash/范围不一致或换源复用 Run 均拒绝。设计详见 [完整 Goal v2](WP-0303-FULL-INPUT-TO-FEATURE-CLOSEOUT-GOAL.md)、[Adapter Bundle 分层架构](WP-0303-A-STOCK-DATA-ADAPTER-ARCHITECTURE.md)和[实现契约目录 C-004](platform-implementation-contract-catalog-v1.md#36-endpoint-admission-纯追加契约)。

### 20.3 当前验收和下一任务边界

| 项目 | 本轮结论 |
| --- | --- |
| B1—B4 | 新增整体关闭项 0；真实来源证据未变化，全部保持 `NO_GO` |
| C-004 Endpoint Admission | 架构 `Design Approved / Not Implemented`；下一独立 Goal 实现四对象、持久化和 fail-closed 门禁 |
| 真实输入→计算→发布→消费 | 未启动新链路；必须等单 Endpoint `PIT_CERTIFIED`，不得用 fixture/current history/fallback 解锁 |
| 旧兼容性 | 14 F1、65 F2、0014/0015、旧 C-004 Schema/Golden/Hash、B5/N1/N2 和固定引用均保留 |
| 市场能力与 WP 状态 | `market_breadth/market_emotion=missing`，Formal/Paper 拒绝；`WP-0303=IN_PROGRESS`、15/45、`NOT CERTIFIED`、`RELEASED=false` |

下一任务只能建立来源准入基础设施，不访问真实 Provider API，不认证具体 Endpoint，不关闭 B1—B4，不执行正式 DERIVED/F1/F2/FeatureBundle 发布。四类对象确需持久化时只追加 0015 之后的后继 Migration；不得修改历史迁移。

### 20.4 验证、风险和回滚

本轮是 docs-only 架构调整。实际日志和收尾证据保存在 `E:\Personal Manager\参考项目\WP0303-PIT-TRACE-20261014-172547\goal-realignment-protection-20261015-155324\result-20261015-160214`。

| 实际命令 | 退出码 / 结果 |
| --- | --- |
| `python scripts/check_ai_assets.py` | 0；`[ai-assets] OK` |
| `python scripts/check_visory_baseline.py` | 0；694 个相对链接、broken=0、imported_secrets=0 |
| `python scripts/export_platform_contracts.py --check` | 0；generated exports current，证明本轮未引入生成契约漂移 |
| `git diff --check` | 0；仅输出既有 Windows LF→CRLF 提示 |
| 产品 pytest / 隔离 PostgreSQL E2E / `bash scripts/ci_gate.sh all` / 客户端构建 | 运行数 0；没有运行代码、Schema、API 或客户端增量，不能据此写为通过 |

首次收尾包装命令因把含中文的结果目录写成 ASCII，路径字符被替换为 `?`，`Tee-Object` 无法解析而 exit 1；该次未写仓库。改用 UTF-8 路径后完整重跑，五项最终检查均 exit 0。最终保护核对开工 56 项中的 49 个非本轮文件逐字节不变，状态集合仅新增契约目录修改和 Goal 文档，共 58 项；详细 Hash、最终字节和增量 patch 见结果目录 `final-protection.json`、`final-bytes/`、`incremental.patch`。

下一 C-004 实现 Goal 必须实际运行定向测试、Migration/rollback/重启 PostgreSQL E2E、generated/governance/py_compile/lint、`ci_gate.sh all` 和受影响客户端构建；不得把本轮文档检查写成产品通过。

主要风险：实现时原地扩展旧 Run/Raw 导致 Golden/Hash 漂移；将 Admission 基础设施误报为具体来源认证；用 Bundle commit、`actual_upstream` 或当前历史下载构造 `PIT_CERTIFIED` Receipt；无 Binding 的旧运行进入 Formal。回滚只反向合并本轮文档 hunk并删除没有后续编辑/引用的新 Goal 文档；不得整文件 restore、reset、clean、stash 或覆盖开工 56 项成果。

本轮未 commit/tag/建 branch/push/PR/merge、未访问 Provider 业务 API、生产数据库或真实 `/data`，未执行调度、部署、发布或生产认证。完整 Goal 仍 `PARTIAL/BLOCKED`。

## 21. 2026-10-15 C-004 Provider Endpoint Admission：本地基础设施完成 / 来源未准入

### 21.1 范围、保护与结论

`WP-0303-C004-PROVIDER-ENDPOINT-ADMISSION-CONTRACT` 只在累计工作树 `C:\Users\lzq11\.codex\worktrees\f468\Visory` 实现。开工为 detached HEAD `efe8e9b362cba13eca183c55be57bbbbc832b60b`，实时 `origin/main` 同 SHA；开工 28 个 tracked change、30 个 untracked，共 58 个文件已按原始字节、SHA256、Git index 和 binary patch 保存到仓库外 `C:\Users\lzq11\.codex\worktree-protections\WP-0303-C004-20261015-161325`。接手时又将累计 83 个 dirty/untracked 文件保存到 `C:\Users\lzq11\.codex\worktree-protections\WP-0303-C004-HANDOFF-20261015-182952`，与前序结束字节逐项核对为 0 mismatch。主检出未写入，不执行 reset、clean、stash 或整文件 restore。

本 Goal 完成的是 C-004 来源身份、证据、持久化和 Formal fail-closed 基础设施，不是任何真实来源的准入结论。未访问真实 Provider API、生产数据库或真实 `/data`，未注册 B1—B4 新 Dataset/Raw Schema/Mapping/Definition，未执行正式 DERIVED、F1/F2、FeatureSnapshot 或 FeatureBundle 发布。

### 21.2 四对象、持久化与引用

| 对象 | 稳定身份 | 持久化与引用 |
| --- | --- | --- |
| `ProviderEndpointDefinition@1.0.0` | `provider_endpoint_id + provider_id + endpoint_contract_version` | 固定 method、脱敏 origin allowlist/path family、请求/响应 Schema Hash、Dataset/schema/market、分页/total/terminal、零行/无数据/错误、revision/cancel、发布时间、rate limit/retry/license、有效区间和 `definition_hash` |
| `AdapterImplementationFingerprint@1.0.0` | `adapter_implementation_fingerprint_id` | 外键绑定精确 Endpoint triple；固定 Bundle/version、repository/commit、源文件 blob/实际字节 Hash、函数符号、Visory wrapper、Mapping、质量规则和 `implementation_fingerprint` |
| `SourceAdmissionReceipt@1.0.0` | `source_admission_receipt_id` | 外键绑定精确 Endpoint triple 与 Dataset/schema；保存 market/date 申请范围、八类来源证据 Hash、coverage summary、显式 admission level/status、有效区间和 `receipt_hash`；builder 不默认生成 `PIT_CERTIFIED` |
| `ProviderEndpointRunBinding@1.0.0` | `provider_endpoint_run_binding_id`，且 `provider_run_id` 唯一 | 绑定旧 Run、全部 Raw refs、精确 Endpoint、实现指纹、Receipt、Dataset/schema/market、request/observed schema Hash 与脱敏 actual origin；Binding→Raw 以独立关联表保存并形成 `binding_hash` |

后继 Migration `0016_wp0303_provider_endpoint_admission` 新增上述四张主表及一张 Binding→RawObject 关联表，0005—0015 不变。Repository 只提供精确 ID/version 查询，不提供 latest 或模糊 Endpoint 选择；`ProviderAdmissionService.publish_package()` 在一个数据库事务内发布完整包，失败不保留部分 Endpoint/Receipt/Binding。同一 Endpoint/Fingerprint/Receipt 以及同一 Binding 的逐字段相同重放会复用既有不可变记录，不同 Run 可引用相同前置对象；同身份内容漂移仍拒绝。发布事务按 downgrade 相同顺序取得五表 `SHARE ROW EXCLUSIVE` 锁，避免并发首次发布在 read-before-insert 窗口发生主键竞争；downgrade 以 `ACCESS EXCLUSIVE` 锁定五表，任一新记录存在时在任何 DROP/ALTER 前拒绝，五表为空时可安全退回 0015 再升级。

### 21.3 Formal fail-closed 接线与反例

Snapshot `backtest_core` build、Formal consumer 和 backtest current pointer 都调用 `ProviderEndpointAdmissionVerifier`。来源证据 resolver 或实现观察 resolver 缺失也拒绝，不以持久化 Hash 自证当前字节。定向单元和真实 PostgreSQL 测试覆盖：

| 门禁 | 测试证据 |
| --- | --- |
| 旧 Run 或 Formal 输入缺 Binding | `test_legacy_run_without_binding_is_rejected`、Snapshot PostgreSQL `missing_binding` |
| Provider/Endpoint/version/market/actual origin 不一致 | `test_endpoint_version_mismatch_fails_closed`、Snapshot PostgreSQL `internal_source_switch` |
| Receipt 非 `PIT_CERTIFIED` | 模型测试参数化三个非 PIT 等级；Snapshot PostgreSQL `current_snapshot`、`historical_series`、`versioned_archive` |
| Receipt REVOKED、非 ACCEPTED、失效或 market/date 范围不覆盖 | `test_revoked_expired_and_out_of_scope_receipts_are_rejected`；Snapshot PostgreSQL `revoked`、`expired`、`date_scope` |
| Receipt 的来源证据 Hash 漂移 | `test_evidence_and_implementation_drift_are_rejected`、真实 Repository PostgreSQL evidence drift、Snapshot PostgreSQL `evidence_drift` |
| commit/文件字节/符号/wrapper/Mapping/质量规则漂移 | 模型与真实 Repository PostgreSQL implementation drift、Snapshot PostgreSQL `implementation_drift` |
| Binding 遗漏 Raw、Raw 不属于 Run 或 Raw 契约漂移 | `test_run_raw_request_schema_and_source_switch_mismatches_fail_closed`、Snapshot PostgreSQL `raw_omission` |
| Dataset/schema/request fingerprint/observed schema 不一致 | Repository 约束测试、模型漂移测试、Snapshot PostgreSQL `request_mismatch` |
| Adapter 内部换源后复用原 Run/Raw/Binding | 模型与真实 Repository PostgreSQL source-switch drift、Snapshot PostgreSQL `internal_source_switch` |
| 通配 Endpoint 路径以 `..`、编码点段或过度多层编码越界 | `test_run_raw_request_schema_and_source_switch_mismatches_fail_closed` 对明文、`%2e%2e` 和三轮后仍可继续解码的点段均拒绝 |
| Preview/历史兼容读取误升为 Formal | Snapshot 单元明确拒绝 legacy Run；只给显式合成 `PIT_CERTIFIED` 包的成功 fixture 注入两个 resolver |

### 21.4 实际验证与未通过项

以下计数相互有重叠，不相加；全部成功套件为 0 skipped：

| 实际命令/套件 | 结果 |
| --- | --- |
| C-004 Contract/Registry/Schema/Golden 首轮 | **152 passed / 1 warning** |
| `test_provider_endpoint_admission_postgres.py` | **8 passed**；migration、重启读回、FK/唯一约束、事务回滚、精确不可变前置对象的多 Run/并发首次发布复用、同身份漂移拒绝、真实 Repository Formal 漂移与 downgrade |
| Snapshot 定向单元 | **32 passed** |
| Snapshot 实际 PostgreSQL | **17 passed**；成功路径及 12 类 Admission fail-closed 反例 |
| Provider Admission + Snapshot + PostgreSQL foundation | **31 passed** |
| 受影响 Contract/Golden/Snapshot/Adjustment/F1/F2 保护套件 | **505 passed** |
| Provider/Raw/Canonical/Snapshot/Backfill 实际 PostgreSQL 组 | **63 passed** |
| `python -m alembic heads` | exit 0；唯一 head 为 `0016_wp0303_provider_endpoint_admission` |
| export / AI assets / baseline / goal Python `py_compile` | 均 exit 0；694 个相对链接、broken=0、imported_secrets=0 |
| C-004 默认 flake8、受影响文件 critical flake8 | 均 exit 0；扩大到开工前历史测试文件的默认 flake8 为 exit 1，命中既有 `test_adjustment_derived_contract.py` 风格项及 HEAD 已有空行项，不把该扩大命令记为通过 |
| `git diff --check` | exit 0；仅既有 Windows LF→CRLF 提示 |
| 字面 `bash scripts/ci_gate.sh all` | WSL bash 无 `python`，exit 127；未进入测试 |
| Git Bash 环境对齐尝试 | 系统 Python 3.12 因缺 `tenacity` 中止；仅复制既有 venv 的 `tenacity` 到临时 overlay 后继续因缺 `fake_useragent` 中止；改为只读复用既有 venv 全部 site-packages 后，未设置 UTF-8 的首次执行因 Windows GBK 无法输出 `✅` 中止。以上均 exit 1，未安装或下载依赖，不记为完整 gate 结果 |
| Git Bash + 既有 Python 3.12 venv site-packages + UTF-8 `./scripts/ci_gate.sh all` | 首次复跑未固定 `python3`，Git Bash 命中 WindowsApps Python 3.14 与 cp312 NumPy 不兼容，exit 1 且未进入 offline pytest；修正为 `python3 -> Python 3.12.9` 后完整执行，**exit 1；7249 passed / 82 failed / 167 skipped / 4 deselected / 62 warnings，572 subtests passed，343.85s**。当前 82 项是既有 83 项归因矩阵的严格子集，0 项新增、`C004_ATTRIBUTABLE=0`；分类为环境不兼容 58、既有测试缺陷 21、flaky 2、越界 Storage 产品缺陷 1，原第三项 flaky 本轮通过。完整 gate 仍未通过且本 Goal 不修复越界项。offline gate 无隔离数据库环境，PostgreSQL 测试被 skip，另由实际 PostgreSQL 63 passed / 0 skipped 覆盖。组合环境只读复用既有 venv、未安装依赖；其中 Alembic 1.20.0、psycopg 3.3.5 与声明 pin 1.19.1、3.3.4 存在环境偏差 |
| 临时 PostgreSQL 资源回收 | 两轮停库前 `visory_test_*` 数据库计数均为 0；仅删除容器 `visory-wp0303-c004-4b9f6d963c4e`、接手复验容器 `visory-wp0303-c004-handoff-fd0a064e66d8` 及对应临时密码/环境文件，未触碰其他容器 |

### 21.5 状态、风险与独立回滚

- **BLOCKER**：真实 Source Admission 包仍不存在；逐 Endpoint 的固定 Provider/version、脱敏原始响应、全页/全区间覆盖、合法零行、历史 `available_at`、revision/cancel、单位/身份、质量和许可证据未提交。B1—B4 全部继续 `NO_GO`。
- **BLOCKER**：完整 `ci_gate.sh all` 已执行到 offline pytest 结束，但为 exit 1（7249 passed / 82 failed / 167 skipped / 4 deselected，572 subtests passed），因此不能声明完整 gate 通过。当前 82 项全部包含于已独立归因的既有 83 项且 `C004_ATTRIBUTABLE=0`，与本 Goal changed paths 和 Platform 测试范围无交集；当前授权也不允许顺手修改 Agent/Codex transport、本地 CLI、SQLite/Storage、调度/搜索等越界模块。定向 505/63 与静态检查不能替代完整 gate 或远端 CI。
- **FOLLOW-UP**：当前 `REVOKED` 只能表达 Binding 所引用 Receipt 自身的状态；不可变 `ACCEPTED` Receipt 的后续撤销尚无显式 supersession/status-event 链。阶段 C 在接入任何真实 Endpoint 前必须先收敛撤销身份、先后关系和 Formal 查询规则，不得原地更新旧 Receipt 或把新 ID 的无关联 `REVOKED` Receipt 当成已传播撤销。
- **FOLLOW-UP**：阶段 C 只能选一个证据完备的真实 Endpoint 单独审核；通过后才可追加其 Dataset/Raw Schema/Mapping/质量/Policy，不得从测试合成 `PIT_CERTIFIED` Receipt 或使用当前历史重下载替代 PIT。
- 当前保持 `WP-0303=IN_PROGRESS`、15/45；`market_breadth/market_emotion=missing`，Formal/Paper 真实来源路径继续拒绝，生产 `NOT CERTIFIED`、`RELEASED=false`。
- 代码回滚只反向合并本 Goal 对四对象、Repository/Service、Snapshot Formal 接线、0016、四份 Schema、八份 Golden、Registry、测试和文档的增量 hunk；不得整文件 restore、reset、clean、stash 或覆盖开工成果。数据库仅在五张 Admission 表为空时降级到 0015；有记录必须保留数据并停止。

本轮未 commit、tag、建 branch、push、PR、merge、fetch/pull、部署或发布；本地 dirty 增量没有远端 CI 所属提交。
<a id="mainline-convergence"></a>

## 22. 2026-10-19 mainline convergence 与候选验收

本轮结论：**PR-ready（本地候选）**。范围内实现与验收 BLOCKER 已关闭；最终冻结候选通过完整 backend gate，并非引用 main CI 或 f468 历史结果。此结论只表示可提交独立审查，不表示已创建 PR、已合入、WP-0303 完成、真实来源准入或生产认证。

### 22.1 基线、范围与保护

本轮 `WP-0303-MAINLINE-CONVERGENCE-AND-PR-READINESS` 不以真实输入闭合、整个 WP 完成或生产认证为完成条件。候选在原本干净的 detached worktree `C:\Users\lzq11\.codex\worktrees\2cb1\Visory` 收敛；不在 f468 原地 pull/rebase，不创建分支或提交。

- 开工与收尾多次实时 GitHub 只读 `branches/main` 核验均为 `0d4d5bb6b67c391a5c6b18ff6480d61eaffedc47`，即 PR #42 合入点。`git fetch --all --prune`、`git ls-remote` 因 GitHub 443 连接失败，均 exit 128；不能把它们描述为同步成功。
- 开工保存主 checkout、WP-0207、f468 的 HEAD、逐文件 status/SHA256，共 1509/1551/1585 文件；f468 的 83 个改动另存原始字节 zip/patch。证据目录为仓库外 `C:\Users\lzq11\.codex\tmp\wp0303-mainline-20261019`。
- 原 83 路径分为 68 项 WP-0303、14 项生成物、1 项独立状态治理。排除 `WP-0302-IMPLEMENTATION.md`，CHANGELOG/status 只取 WP-0303 hunks；生成物不复制源文件，只由既有 exporter 生成。
- 候选新增 merge revision、联合门禁回归、三起点迁移回归三个路径；另为固定历史 SHA 的兼容测试，仅在 backend CI checkout 加 `fetch-depth: 0`，并把 main 的旧回滚测试限定到其原 0014 历史前缀。合计 87 路径，不含依赖、客户端页面或其他 WP 实现。

### 22.2 八个重叠路径与 PR #42 语义

| 重叠路径 | 收敛方式 |
| --- | --- |
| `docs/CHANGELOG.md` | 保留 main 条目，仅追加本 WP 扁平条目 |
| `IMPLEMENTATION-STATUS.md` | 保留 WP-0207/main 历史，追加本 WP 当前与历史路由，按 45 行重新计数 |
| `schemas/platform/C-010.openapi.json` | 既有 exporter 重建，保留 main 的公开诊断与 SourceRoute schema |
| `schemas/platform/contract-registry.json` | 保留 main 74 个注册，纯追加本 WP 7 个对象，总数 81 |
| `src/schemas/platform/__init__.py` | 同时保留 main ProviderSource 与 WP Adjustment/Admission exports |
| `src/schemas/platform/registry.py` | 不覆盖 main 的旧注册语义，追加 Adjustment/Admission 注册 |
| `src/services/platform/snapshot.py` | 保留 main 的来源绑定及 OSError/PlatformDatabaseError 任务失败路径，接入 Admission |
| `tests/integration/platform/test_postgres_foundation.py` | 保留 main 来源列断言，扩展统一 head 和本 WP 表断言 |

main 的 public sanitizer、API error/router、SourceRoute、Raw ingestion、Backfill、Canonical normalization、来源列迁移、Web sanitizer/TS 与依赖声明保持 main 内容。修复联合门禁反例：有效 `PIT_CERTIFIED` Receipt 不能绕过缺失、BLOCKED/UNAVAILABLE、FIXTURE、Hash 漂移或身份不一致的 SourceRoute；SourceRoute 与完整 EndpointAdmission 必须同时通过。有效 route 缺 Binding 仍拒绝。正向 fixture 显式提供合成 AVAILABLE route，不修改真实 registry 默认拒绝状态。

### 22.3 单一迁移 head 与旧证据

追加无 DDL 的 `0017_wp0303_mainline_merge`，父节点为 `0014_wp0207_source_binding` 与 `0016_wp0303_provider_endpoint_admission`。保留原 0014/0015/0016 的文件、revision、长度合同和危险降级保护，不重排或重写迁移。空库、main 已升级且有非空来源证据的库、WP-0303 已升级且有 Admission 证据的库均升级至统一 head；逐值读回及幂等升级均有真实 PostgreSQL 测试。

只在可销毁随机测试库演练 downgrade：有 Admission 记录时原 0016 guard 在任何 DDL 前拒绝；空 Admission 表退回 WP 分支 0015 时保留 main 的 `source_route_evidence` 列，再升级到 0017。没有业务库 downgrade/stamp 或来源证据删除。

旧 14 F1/65 F2 的版本、完整 payload/Hash、序列化和固定引用保持不变；原兼容 baseline/Golden 不改。main 已验收的两份旧 Golden 变更、新增 BackfillCoverageProjection Golden 及相关生成 schema 均保留，不倒退为 f468 旧版。兼容测试先逐项验证 main 原文，再投影其固定、已审查的历史 delta；旧 Windows CRLF 封存与 Linux LF checkout 使用明确的历史换行视图，LF/CRLF 两组均覆盖全部 119 份旧 Golden 的内容漂移拒绝，不重写旧预期 Hash。收尾扩大到开工 `migrations/versions/` 与 `tests/golden/platform/` 全清单：排除两份已由 main 改变的旧 Golden 后，153 份原文件逐项原始字节一致；三份 main Golden delta 另与 main 逐项核对一致，记录在 `invariant-review-final.json`。初始较窄 139 项检查仍保留，不替代本次扩大范围的复核。

### 22.4 当前候选验证，不复用历史通过结论

环境：缓存 `python:3.11.17-slim`、`postgres:16-alpine`，按仓库原 `.github/requirements-ci.txt` 安装，无 manifest/lockfile 或依赖版本调整。记录完整 pip freeze、镜像与工具版本；复用已有真实 Linux git/procps 二进制，不用替身返回伪造结果。Python/PG 只共享 loopback namespace，无外网、published port、持久化卷、生产挂载或真实 `/data`；PostgreSQL 为 tmpfs 和随机 `visory_test_*` 库。

| 检查 | 当前实际结果 | 证据 |
| --- | --- | --- |
| 最初定向联合回归 | 799 passed / 0 skipped | `linux-directed.log`；随后新增换行回归 |
| 第一轮 Git tree LF 归档定向回归 | 801 passed / 0 skipped | `linux-directed-git-tree.log`，13 个受影响测试文件 |
| 最终冻结 Git tree 定向复验 | 802 passed / 0 skipped | `linux-directed-final.log`，14 个测试文件，含 main 回滚历史保留契约 |
| 最初全部 PostgreSQL | 251 passed / 5 failed | `linux-postgres-all.log`，中间失败保留，不计入最终通过 |
| 五个失败相关组复验 | 35 passed / 0 skipped | `linux-postgres-convergence-retest.log` |
| 全部真实 PostgreSQL 最终复验 | 256 passed / 0 skipped | `linux-postgres-final.log` |
| 第一轮原样 `bash scripts/ci_gate.sh` | exit 1；8177 passed / 1 failed / 0 skipped / 4 deselected，572 subtests passed | `linux-full-gate.log` 与同名 JSON；唯一失败为旧 0014 回滚测试 head 假设 |
| 最终冻结树原样 `bash scripts/ci_gate.sh` | exit 0；8178 passed / 0 failed / 0 skipped / 4 deselected，56 warnings，572 subtests passed | `linux-full-gate-final.log` 与同名 JSON；全部四阶段执行，未使用 shard/额外 skip 参数 |
| 测试后冻结源文件完整性 | 1603 项 / 0 mismatch | `linux-runtime-source-integrity.log`，含真实 symlink |
| Linux 契约、AI 治理、基线 | 全部 exit 0；724 links / 0 broken / 0 imported secrets，启用 workflow 仍为 1 | `linux-final-contract-check.log`、`linux-final-governance-check.log`、`linux-final-baseline-check.log` |

四项 deselected 来自仓库原 gate 的 `-m "not network"`，不是本轮新增排除；56 项 warning 不计为失败，也不宣称已清理依赖弃用或既有测试收集提示。各测试集有重叠，不将 802、256、8178 相加为独立覆盖数。最终记录仅追加验收文档，再执行静态与完整 87 路径 diff 检查，不改变通过 gate 的代码、测试、配置或生成契约。

PG 证据覆盖三起点迁移、非空来源/Admission 数据保留、SourceRoute/Admission 联合拒绝、Feature 发布、长 ID/partition key、独立进程固定消费、合成 Correction 及旧字节/引用保留。中间五项失败分别为旧 head 假设、merge 回退目标、重复 bootstrap 覆盖合成状态，以及两项 Parquet Dataset 后台线程退出异常。测试修复保留原断言；固定 PyArrow 的独立进程最小实验中原 reader 8 次失败 7 次，同步 ParquetFile reader 8 次均成功，验收进程显式关闭文件后两条完整消费/Correction 测试通过。没有绕过退出码、跳测试或改依赖。

第一轮完整 gate 与定向 LF 测试使用 `candidate-code-bundle.json` 固定的 Git tree/归档，不把 Windows 原字节拷贝当作 Linux checkout。该轮唯一失败是 main 旧回滚测试将全图 head 等同于 0014；修复仅将其原断言限定到 0014 历史前缀，不放宽删除已应用迁移必须失败的契约。两次冻结树的生产代码完全相同，迭代差异仅为该测试、CI checkout 与四份当前验收文档，记录于 `gate-iteration-review.json`。最终定向与完整 gate 使用 `candidate-validation-bundle.json` 的 `60d5f73b290e29bed245d8808c5a86ca7eb095f8`，已包含该修正和 backend CI 完整历史 checkout；最终验收记录的纯文档差异单独封存，并核验代码/测试/配置与冻结树一致。收尾重新核验 exporter/governance/baseline/diff、allowlist、旧证据与受保护工作树。远程 Actions、Web/Desktop 构建、真实 Provider/生产链路未执行；无客户端运行时变更，不把这些检查写成通过。

### 22.5 状态、后续与回滚

`WP-0303=IN_PROGRESS`；`VERIFIED=15/45`；45 行中 `IN_PROGRESS=2`、`NOT_STARTED=28`、`RELEASED=0`。`market_breadth/market_emotion=missing`，B1–B4 真实输入仍 `NO_GO`，真实来源 Formal/Paper 继续拒绝；`NOT CERTIFIED`、`RELEASED=false`。第 1–21 节的旧 Windows/PG/gate 数字仅为历史，不替代本节候选结果。

Receipt 撤销生命周期是**真实 Endpoint 准入前必须另行设计/验收的 FOLLOW-UP**。本轮没有新增 supersession/status-event 或撤销传播；当前 `REVOKED` 检查只拒绝 Binding 直接引用的 Receipt 自身状态，不能撤销传播到既有 ACCEPTED Receipt/Binding。

仓库外最终 bundle 保存 allowlist、原始逐文件 Hash、完整可审查 binary patch、Git tree 和归档 Hash；使用独立外部 index 演练 reverse/apply，回退树必须等于 main tree，再应用必须等于候选 tree。该演练不改真实 index、工作树、分支或数据库。实际回滚须先核验对应 manifest，仅撤销本候选 hunks，不 reset/clean/stash、整文件覆盖原树或降级有数据的业务库。没有 commit/tag/push/PR/merge/部署；原三个工作树保持原成果。

完整代码逆补丁仅适用于未部署、未应用本候选迁移的本地候选。若某环境已经应用本 WP 迁移，必须保留已应用 revision 文件及其导入依赖，不得用整包代码回退删除版本历史；数据保全后另行授权前滚修复。本轮空测试库降级不证明已部署环境可以回退到旧代码，也不提供业务库逆向迁移许可。

本轮只更新中文专题及既有状态/CHANGELOG；没有对应英文专题要同步，未扩写 README。没有报告格式或页面改动，不需要页面截图。

## 23. 2026-10-20 独立候选交付与当前证据入口

本节承接第 22 节的本地候选，不改写第 1–22 节的历史执行结果。交付授权覆盖独立 `codex/` 分支及工作树、commit、push、候选 PR 和当前 head CI；不覆盖 merge、tag、release、部署或生产操作。

- 本次开工 `git fetch --all --prune` exit 0，`origin/main` 与独立 GitHub API 核验均为 `0d4d5bb6b67c391a5c6b18ff6480d61eaffedc47`。PR #42 已于 `2026-10-19T08:57:04Z` 合入该基线；状态文件中旧 OPEN/未提交叙述只属于其当时快照。
- 交付分支为 `codex/wp-0303-mainline-delivery`，使用新建独立工作树。封存的 87 路径候选导入后，Git tree 精确等于 `030738e50e0e779d355c3f21fb5085e8c7f592d3`；之后只校准本实现记录、IMPLEMENTATION-STATUS 和 CHANGELOG。代码、测试、配置、迁移与生成契约保持封存候选内容。
- 注册表由 main 的 74 个对象追加至 81 个；第 22.2 节原 76/83 计数是文档错误，本节只更正计数，不改变任何注册对象。原 14 F1、65 F2 的版本、payload、Hash、Golden 和固定引用继续保留。
- 第 22.4 节的 802 定向、256 真实隔离 PostgreSQL、8178 完整 gate 是已封存 Linux 验证树的本地证据，不是本次 PR head 的远端 CI。本次不重复搭建已清理的临时环境，也不将历史结果冒充当前 head 运行。
- 远端验证以候选 PR 当前 head 关联的 `Governance and repository boundaries`、`Python deterministic gate`、`Web lint and build` 三项阻断检查为准；具体提交、run/job URL 与实际结论记录在 PR 描述及外部交付审计中，本节不预记成功。backend CI 原样执行 `scripts/ci_gate.sh`，含真实临时 PostgreSQL；不引用 main 或旧 head CI 替代。
- 主 checkout、原 WP-0207、f468、2cb1 候选与 01be 审查树在开工逐文件核验共 7784 个 Git 可见文件，HEAD/status/Hash 全部匹配原保护快照；不包含 ignored 文件承诺。原树不 pull/rebase/reset/clean/stash，不覆盖原成果。原始 manifest、传输记录与导入核验保存在仓库外交付审计目录，不成为运行时依赖。

当前交付只供独立审查，仍为 `WP-0303=IN_PROGRESS`、`VERIFIED=15/45`、B1–B4 `NO_GO`、`market_breadth/market_emotion=missing`，真实来源 Formal/Paper 拒绝，`NOT CERTIFIED`、`RELEASED=false`。Receipt 完整撤销生命周期仍是第 22.5 节的真实 Endpoint 准入前 FOLLOW-UP，不在本 PR 新增。

回滚沿用第 22.5 节：未部署且未应用迁移时可按封存清单精确逆向候选 hunks；已应用迁移的环境必须保留 revision 历史、导入依赖、Schema 与数据，只能在另行授权下前滚修复，不自动 downgrade/stamp 或整包删除迁移。
