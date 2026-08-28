# Visory Fleur-Lite 回测运行与结果一致性架构

状态：已确认（Design Approved）

最后更新：2026-08-28

## 1. 决策摘要

平台采用 Fleur-Lite 五阶段回测模式：吸收 Fleur 的策略草稿/已应用边界、股池预览、同步校验、异步正式回测、结果账本和模拟组合发布检查；不引入 Fleur 的完整运行栈。

正式计算边界固定为：

- Hikyuu 是唯一正式策略回测和组合模拟内核；
- DuckDB 负责预览、因子评价和轻量研究筛选，不生成正式组合业绩；
- Parquet 是大规模行情、快照和回测明细的权威落点；
- PostgreSQL 保存策略版本、任务、运行、Attempt、结果索引和审批元数据；
- Hikyuu HDF5 仅作为指定数据快照生成的可重建缓存；
- 初期采用模块化单体 API 和一个 Hikyuu Worker，不部署 ClickHouse、NATS、RustFS 或另一套组合模拟器。

轻量化只能改变等待时间、并发量和读取方式，不能静默改变正式回测语义。任何不能证明等价的优化必须留在研究层，不能标记为正式结果。

## 2. 设计目标与非目标

### 2.1 目标

1. 在当前 ARM64 四核服务器上稳定运行，不以升级服务器为前提；
2. 创建正式回测后立即返回任务标识，Web 请求不等待 Hikyuu 完成；
3. 预览、研究和正式回测具有清晰且不可混淆的结果等级；
4. 相同不可变输入重复执行可复现；
5. 失败重试不覆盖旧结果，任务可取消、可诊断、可审计；
6. 正式回测和 Paper Portfolio 使用不同事实表族，通过显式发布流程衔接；
7. 后续可以替换任务队列或分析存储，不改变 StrategySpec 和回测结果契约。

### 2.2 非目标

- 不复制 Fleur 的 ClickHouse、NATS JetStream、RustFS、Dagster 和 Rust Portfolio Worker；
- 不要求 DuckDB 近似研究结果与 Hikyuu 成交结果相同；
- 不把浏览器预览缓存直接作为正式回测输入；
- 不把回测成功等同于策略获批或允许进入模拟组合；
- 不在 v1 支持多台服务器分布式回测和高并发用户队列。

## 3. 三种结果等级

| 等级 | 引擎与用途 | 是否正式业绩 | 是否可发布到 Paper Portfolio |
| --- | --- | --- | --- |
| `PREVIEW` | Resolver/Compiler + DuckDB，检查指定日期股池、评分、排名、解释和依赖 | 否 | 否 |
| `RESEARCH` | 因子评价、向量化近似模拟和参数初筛 | 否 | 否 |
| `FORMAL` | 冻结 RunBundle 后由 Hikyuu 完成交易与组合仿真 | 是 | 通过发布检查后可以 |

### 3.1 Preview 的一致性边界

Preview 不是正式业绩，但不能成为另一套选股逻辑。同一 `ResolvedStrategySpec`、同一日期、同一 Data/Feature Snapshot 和同一股票池范围下，Preview 与正式编译阶段必须得到相同的：

- 候选证券；
- 原始分数、标准化分数和稳定排序；
- TopN 选择；
- 策略信号和原因码。

Preview 可以限制日期范围、仅返回摘要和解释，也可以使用短期缓存；这些差异必须写入 `preview_scope`。Preview 不生成订单、成交、持仓、现金账本或正式绩效。

### 3.2 Research 的近似边界

Research 可以使用向量化近似成交、简化费用或缩短区间加速筛选，但必须：

- 写明 `approximation_profile_id/version`；
- 在页面标记为“研究筛选”，不显示为正式回测；
- 不覆盖正式回测结果；
- 只把候选配置交给 Hikyuu，不能把近似成交明细直接升级为正式结果。

### 3.3 Formal 的权威边界

以下内容只认 Hikyuu Adapter 归一后的结果：

- OrderIntent、ExecutionResult 和 Trade；
- PositionSnapshot、CashLedger 和 PortfolioNav；
- 费用、滑点、涨跌停、停牌、T+1 和容量约束；
- 收益、回撤、换手、风险和基准比较指标。

## 4. Fleur-Lite 五阶段流程

```text
Stage 1  策略选股
  draft StrategySpec
        │
Stage 2  评分、权重与 TopN
  Resolver → canonical applied spec
        │
Stage 3  股池预览
  Preview → score/rank/breakdown → applied/draft/stale
        │
Stage 4  执行参数校验与冻结
  validate → RunBundle + hashes，不创建结果
        │
Stage 5  异步正式回测
  create run(202) → durable task → Hikyuu → ledger/results
```

### 4.1 Draft、Applied 与 Stale

- `draft`：用户正在编辑，允许不完整，不可正式运行；
- `applied`：已通过 Resolver 和静态校验的不可变配置；
- `previewed`：绑定 `applied_spec_hash` 和输入快照；
- `stale`：draft 或依赖版本变化后，旧 Preview 仍可查看但不可据此创建正式 Run；
- `validated`：执行参数、数据依赖、市场规则和资源预算均通过；
- `approved/active`：通过显式审批后可用于 Paper Portfolio。

### 4.2 正式回测必须重新计算

Stage 5 不复用 Preview 的候选结果作为权威输入。Worker 必须从冻结的 RunBundle 重新执行：

```text
股票池 → 特征依赖 → 筛选 → 评分 → TopN → 目标权重
      → T/T+1 映射 → Hikyuu 撮合 → 组合账本 → 指标
```

重新计算用于发现输入漂移和缓存污染。若正式阶段的信号 Hash 与同范围 Preview 不一致，Run 进入 `consistency_failed`，不得发布结果。

## 5. 当前服务器的轻量运行架构

```text
Web / API
   │
   ├── Strategy Validate / Preview
   │        └── DuckDB + Parquet
   │
   ├── Backtest Query API
   │        └── PostgreSQL metadata + Parquet results
   │
   └── Create Backtest (HTTP 202)
              │
        PostgreSQL durable task
              │ lease/heartbeat
       Hikyuu Worker × 1
              │
     Snapshot Adapter / HDF5 cache
              │
      Hikyuu formal execution
              │
   atomic Parquet artifacts + result index
```

### 5.1 组件职责

| 组件 | 职责 | 禁止事项 |
| --- | --- | --- |
| Platform API | 校验、创建Run、查询状态、返回摘要 | 不在HTTP请求内运行长回测 |
| Preview Service | 解析策略、股池/评分预览、依赖诊断 | 不生成正式收益 |
| Task Repository | 入队、租约、心跳、取消、Attempt和幂等 | 不保存大规模时序结果 |
| Hikyuu Worker | 获取任务、重建信号、正式仿真、写结果 | 不自行抓取权威行情 |
| Result Repository | 原子发布结果清单和查询索引 | 不覆盖旧Attempt |
| Paper Portfolio Worker | 消费获批版本并做每日结算 | 不直接复用Backtest事实表 |

### 5.2 初始资源策略

建议默认值：

```yaml
backtest_runtime:
  formal_worker_concurrency: 1
  lightweight_research_concurrency: 2
  queue_poll_seconds: 3
  lease_seconds: 120
  heartbeat_seconds: 30
  max_attempts: 2
  preview_max_trading_days: 250
  worker_threads_per_run: 2
  formal_topn_only: true
  lazy_result_details: true
  cache_signal_matrix: true
```

约束：

- 同一时刻只运行一个 Hikyuu 正式回测；
- 正式回测运行时暂停重型 Research Worker，避免内存和 CPU 争抢；
- API 与 Worker 分进程，Worker 崩溃不能带走 Web；
- Worker 设置内存、CPU、运行时长和临时目录上限；
- 超过配额进入可诊断失败，不允许静默减少股票或日期继续运行。

配置是目标契约，进入实现阶段时再映射到 `.env.example` 和部署文件；本文不代表当前仓库已提供这些运行参数。

## 6. API 契约

```text
POST /api/v1/strategies/validate
POST /api/v1/strategies/preview
POST /api/v1/backtests
GET  /api/v1/backtests/{run_id}
POST /api/v1/backtests/{run_id}/cancel
POST /api/v1/backtests/{run_id}/retry
GET  /api/v1/backtests/{run_id}/overview
GET  /api/v1/backtests/{run_id}/nav
GET  /api/v1/backtests/{run_id}/trades
GET  /api/v1/backtests/{run_id}/positions
GET  /api/v1/backtests/{run_id}/diagnostics
POST /api/v1/backtests/{run_id}/publish-preview
POST /api/v1/paper-portfolios
```

### 6.1 Validate

Validate 接收临时策略和执行配置，返回：

- 规范化配置及 Hash；
- 数据、特征和编译依赖；
- lookback/warmup 和估算资源；
- 错误、警告和可运行性；
- RunBundle 草案。

Validate 不创建 BacktestRun、结果或持久任务。

### 6.2 Preview

Preview 返回指定范围的候选、分数、排名、TopN、score breakdown、信号和 stale 状态。服务端必须限制日期、行数和解释明细，避免一次预览扫描全历史。

### 6.3 Create Backtest

创建接口只完成：

1. 校验 applied/preview 状态；
2. 冻结 RunBundle；
3. 在同一数据库事务写 `backtest_run`、`backtest_attempt` 和 `backtest_task`；
4. 返回 HTTP `202 Accepted`、`run_id`、`attempt_id` 和 `queued_at`。

接口不等待特征物化或Hikyuu运行完成。

### 6.4 结果读取

`overview` 返回首屏所需的紧凑数据：状态、核心收益风险指标、基准、区间、资金、配置摘要和诊断摘要。NAV、成交、持仓和事件分页或按区间加载，禁止把全部明细塞进首屏响应。

## 7. Run、Attempt 与 Task

### 7.1 BacktestRun

BacktestRun 表示用户请求的稳定身份，绑定不可变 RunBundle 和幂等键。业务页面以 `run_id` 为入口。

### 7.2 BacktestAttempt

每次实际执行生成新 Attempt：

```text
attempt_id
run_id
attempt_no
worker_id
engine_version
attempt_outcome / attempt_phase
started_at / finished_at
artifact_manifest_uri
result_hash
failure_code / failure_detail
```

重试不得覆盖失败或成功 Attempt。`backtest_run.current_result_attempt_id` 只指向最后一个通过完整校验的成功 Attempt。

### 7.3 BacktestTask

Task 是可租赁的队列记录，最少包含：

```text
task_id / run_id / attempt_id
task_state / priority_class / priority_value
available_at
lease_owner / lease_expires_at
heartbeat_at
cancel_requested_at
retry_count
created_at / updated_at
```

PostgreSQL 实现使用事务和 `FOR UPDATE SKIP LOCKED` 领取任务。初期只有一个 Worker，但保留租约字段以处理进程崩溃和未来扩容。

## 8. Task状态与Attempt阶段

```text
task_state: QUEUED → LEASED → RUNNING → SUCCEEDED|DEGRADED|FAILED|CANCELLED

attempt_phase:
VALIDATING_SNAPSHOT → COMPILING_SIGNALS → MATERIALIZING_DATA
→ RUNNING_HIKYUU → VALIDATING_RESULT → PUBLISHING_RESULT

一致性失败：failure_code=SIGNAL_CONSISTENCY_FAILED|RESULT_VALIDATION_FAILED
```

Task状态转换通过条件更新完成。Worker只有持有有效租约才能写入Attempt阶段；租约失效的旧Worker不得发布结果。取消请求保存在Task控制面，并在安全阶段形成`task_state=CANCELLED`。

## 9. RunBundle 与确定性

正式运行冻结：

```text
resolved_strategy_spec_hash
data_snapshot_id / feature_snapshot_id
universe_hash / calendar_version
market_rule_profile_hash
execution_model_hash / cost_model_hash
weight_policy_hash / portfolio_spec_hash
optimization_snapshot_id
ai_decision_snapshot_hash
approximation_profile_id=null
hikyuu_version / adapter_version
code_commit / dependency_lock_hash
date_range / benchmark_snapshot_id
random_seed
```

### 9.1 运行前门禁

- 所有引用可以解析到不可变版本；
- 每个特征依赖均已声明，动态列投影不存在缺列；
- 输入分区 Hash 与 DataSnapshot Manifest 一致；
- 财务、新闻、公告等数据满足 `available_at <= decision_at`；
- 日期、证券和分数排序键唯一且稳定；
- 费用、滑点、涨跌停和公司行动规则覆盖运行区间；
- AI/随机策略存在冻结输出或固定随机种子。

### 9.2 一致性 Hash

同一 RunBundle 重跑至少校验：

| 层次 | 要求 |
| --- | --- |
| `signal_hash` | 完全一致 |
| `target_weight_hash` | 完全一致 |
| 订单/成交身份与数量 | 完全一致 |
| `position_snapshot_hash` | 完全一致 |
| 金额和价格 | 按统一Decimal与最小货币单位规则一致 |
| NAV与绩效 | 在版本化数值容差内一致 |
| `result_hash` | 规范化产物完全一致 |

禁止依赖数据库未指定顺序、进程Hash随机化、当前时间或未冻结的模型响应。并行计算必须在聚合前按稳定键排序。

## 10. 动态列投影和 TopN 优化

Compiler 从 StrategySpec 生成 `FeatureDependencyPlan`：

```text
required_columns
required_indicators
lookback / warmup
point_in_time_constraints
projection_hash
```

正式 Worker 只读取依赖列和正式 TopN 所需字段；详细解释和 score breakdown 在 Preview 或诊断请求中计算，不进入正式 Worker 热路径。

以下任一情况必须失败，不能用空值继续：

- DSL/插件使用了未声明字段；
- 投影列与编译依赖不一致；
- 同范围 Preview 与正式信号 Hash 不一致；
- TopN 稳定排序键缺失；
- Hikyuu Adapter 无法精确表达策略节点。

## 11. 参数研究与漏选控制

四层资源漏斗：

```text
L0 因子评价
  → L1 DuckDB/NumPy 近似研究
  → L2 Hikyuu 正式候选回测
  → L3 Paper Portfolio 样本外运行
```

初始建议：

- 一轮最多30个候选；
- 轻量研究最多并发2个；
- 每轮至少5个候选进入Hikyuu；
- 最多2个候选进入完整Walk-Forward；
- 除综合排名外，按回撤、换手、稳定性分层保留候选；
- 随机抽取至少5%的淘汰候选进入Hikyuu复核；
- 保存 `screening_recall`，监控近似筛选对正式优胜候选的漏选率。

全区间最优与同区间反推只属于 Research。Walk-Forward 必须在训练窗口寻优，在后续窗口冻结配置并生成 Formal 结果。

## 12. 结果产物与原子发布

```text
/data/daily_stock_analysis/storage/app/results/type=backtest/run_id=<run_id>/attempt_id=<attempt_id>/
├── run-bundle.json
├── artifact-manifest.json
├── predictions.parquet
├── targets.parquet
├── orders.parquet
├── executions.parquet
├── trades.parquet
├── positions.parquet
├── cash-ledger.parquet
├── nav.parquet
├── validations.parquet
├── events.parquet
├── metrics.json
└── diagnostics.json
```

Worker 先写同一文件系统内的 Attempt 临时目录，完成 Schema、行数、Hash、账本平衡和结果一致性检查后，原子重命名为最终目录，再在 PostgreSQL 发布结果索引。失败临时产物进入隔离目录并按保留策略清理，不能被查询 API 当作成功结果。

## 13. 失败、重试与取消

稳定失败码至少包括：

```text
INVALID_RUN_BUNDLE
SNAPSHOT_NOT_FOUND
SNAPSHOT_HASH_MISMATCH
FEATURE_DEPENDENCY_MISSING
SIGNAL_CONSISTENCY_FAILED
ENGINE_START_FAILED
ENGINE_TIMEOUT
ENGINE_OUT_OF_MEMORY
RESULT_VALIDATION_FAILED
RESULT_PERSIST_FAILED
LEASE_LOST
CANCELLED_BY_USER
```

- 输入、契约和一致性错误不可自动重试；
- 临时I/O或Worker崩溃最多按策略重试；
- 取消是协作式的，Worker 在阶段边界和证券/日期分块边界检查；
- 取消后保留 Attempt、日志和诊断，不发布部分绩效；
- `force` 创建新 Attempt，不覆盖原成功结果。

## 14. 可观测性

每个 Attempt 保存阶段耗时和资源：

```text
queue_wait_ms
snapshot_validate_ms
signal_compile_ms
data_materialize_ms
hikyuu_run_ms
result_validate_ms
persist_ms
rows_read / bytes_read
peak_rss_mb / cpu_seconds
prediction/order/trade/position row counts
cache_hit / cache_key
```

Web 首屏展示：当前阶段、排队时长、运行时长、失败原因、数据与策略版本、是否可复现。内部诊断可以展示资源和Hash，不向普通用户暴露主机路径、SQL或敏感配置。

## 15. Backtest 到 Paper Portfolio

正式回测成功后先执行 `publish-preview`：

- Run 是否为 `FORMAL` 且可复现；
- 是否为样本外/Walk-Forward，是否存在泄漏标记；
- 数据、策略、权重和市场规则版本是否获批；
- 风险、容量、回撤和换手是否满足阈值；
- 是否存在未解决的一致性或质量告警。

通过后创建新的 Paper Portfolio 配置快照。只复制策略和运行契约引用，不复制 Backtest 的持仓、成交和NAV；Paper Worker 从启用日开始产生独立事实。

## 16. 验收标准

1. Validate 和 Preview 不创建 BacktestRun 或正式结果；
2. Create Backtest 在短事务后返回202，不等待Hikyuu；
3. 相同 RunBundle 重跑的信号、订单、成交、持仓和结果Hash满足确定性要求；
4. 同范围 Preview 与正式阶段候选、评分、TopN和信号一致；
5. Research 结果不能进入正式业绩或Paper发布接口；
6. 动态列投影与全列基线在固定夹具上产生相同正式结果；
7. 单Worker执行时API仍可查询、取消和读取其他结果；
8. Worker崩溃后租约到期可恢复，旧Worker不能发布结果；
9. 重试创建新Attempt，不覆盖旧Attempt；
10. 任何部分产物都不能被标记为成功；
11. 正式回测和Paper Portfolio使用不同事实表族；
12. 资源超限产生稳定失败码，不静默缩小回测范围；
13. 近似筛选保存候选全集、淘汰原因和漏选率；
14. 所有结果可追溯到RunBundle、快照、代码和依赖版本。

## 17. 实施顺序

### Phase R0：确定性夹具

- 固定20只股票、3年日线和一套MarketRuleProfile；
- 建立Preview/Compile/Hikyuu结果对照；
- 固化Decimal、排序、Hash和结果Schema。

### Phase R1：同步控制面

- 实现Resolve、Validate和Preview；
- 实现RunBundle和幂等键；
- 暂不接正式队列，先完成契约测试。

### Phase R2：本地异步正式回测

- 建立Run、Attempt和Task表；
- 实现一个PostgreSQL队列Worker；
- 接入Hikyuu、原子产物发布和状态查询。

### Phase R3：研究漏斗

- 增加L0/L1轻量研究；
- 实现候选分层、抽样复核和漏选率；
- 接入Walk-Forward和自动权重Trial。

### Phase R4：模拟组合发布

- 实现publish-preview和审批；
- 创建独立Paper Portfolio事实表；
- 接入每日结算、告警和复盘FactPack。

## 18. 数据平台依赖

统一数据平台与Canonical Data Contract已经确定：a-stock-data为核心源，Financial-API为补充源；带市场前缀的规范股票代码为唯一业务标识；Canonical Parquet和DataSnapshot为正式输入，Hikyuu HDF5仅作缓存。数据契约见[A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)，三级物化、FeatureBundle、PIT门禁和缓存保留见[A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)。正式Adapter实现仍须满足：

1. 各数据集的主源、备源和冲突裁决；
2. Canonical Security、Calendar、Bar、Status、Adjustment、CorporateAction Schema；
3. Raw/Normalized Parquet分区和DataSnapshot Manifest；
4. Hikyuu HDF5缓存的构建、失效和校验规则；
5. `available_at`、修订和point-in-time查询口径。

在首个Certified DataSnapshot和HDF5等价性夹具完成前，不应让正式Hikyuu Adapter生成可发布业绩。

## 19. 参考资料

- [Fleur Step 3：股池预览、评分解释与 stale 边界](https://github.com/WackyGem/Fleur/blob/main/docs/RFC/archive/0026-racingline-strategy-pool-preview-step3.md)
- [Fleur Step 5：正式回测、TopN、T+1 与组合账本](https://github.com/WackyGem/Fleur/blob/main/docs/RFC/archive/0028-racingline-strategy-backtest-step5.md)
- [Fleur Step 4/5 回测延迟瘦身](https://github.com/WackyGem/Fleur/blob/main/docs/RFC/archive/0031-racingline-step4-step5-backtest-latency-slimming.md)
- [Fleur Rearview 回测与组合运行架构](https://github.com/WackyGem/Fleur/blob/main/docs/architecture/rearview.md)
- [Hikyuu 项目与交易系统组件](https://github.com/fasiondog/hikyuu)
- [Hikyuu Slippage 模型](https://hikyuu.org/ref-doc/group___slippage.html)
- [指标、预测与 Hikyuu 回测架构](backtest-and-indicator-architecture.md)
- [A 股回测市场规则 v1](backtest-market-rules-v1.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [评分、仓位与自动权重优化架构](weight-optimization-architecture.md)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
