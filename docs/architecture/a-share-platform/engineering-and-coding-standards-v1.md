# Visory 工程与编码规范 v1

状态：Implementation Baseline

最后更新：2026-08-28

## 1. 适用范围与优先级

本文约束Visory目标能力的Python、FastAPI、PostgreSQL、Parquet/DuckDB、Hikyuu、React/TypeScript、任务Worker、Docker和测试实现。仓库通用规则仍以根目录`AGENTS.md`为最高工程规则；跨模块业务字段以[Visory契约收敛总纲](platform-contract-convergence-v1.md)和[实现契约目录](platform-implementation-contract-catalog-v1.md)为准。

发生冲突时：

1. `AGENTS.md`安全和协作规则；
2. 已确认平台契约；
3. 本文工程规范；
4. 领域架构文档；
5. 现有Legacy实现。

现有代码中的SQLite、UTC-naive时间、裸`status`、内存Task Queue和六码`code`属于迁移输入，不是新平台契约范例。

## 2. 架构边界

### 2.1 模块化单体

```text
API Router
  → Application Service
      → Domain Policy / Contract
          → Repository Port
              → PostgreSQL / Parquet / DuckDB / Artifact Adapter

Scheduler
  → Durable Task Service
      → Worker Handler
          → 同一Application/Domain能力
```

规则：

- Router只负责认证、请求Schema、调用Service和响应映射；
- Service负责用例、权限、事务和领域编排；
- Repository负责持久化，不包含业务决策；
- Provider Adapter只获取/规范化来源数据，不发布Snapshot；
- Worker Handler只驱动Task/Attempt状态并调用Service；
- 页面只调用API，不复制指标、评分或回测公式；
- 模块之间通过Schema/Service接口，不直接查询对方私有表。

### 2.2 领域所有权

| 模块 | 唯一写入对象 |
| --- | --- |
| Identity | AssetIdentity、Alias、Sector/Taxonomy Registry |
| Data Platform | ProviderRun、RawObject、CanonicalPartition、DataSnapshot |
| Feature | IndicatorDefinition、FeaturePartition/Snapshot/Bundle |
| Observation | Market/Sector/Global ObservationSnapshot |
| Review | MarketCloseFactPack、ReviewResult/Validation/Report |
| Research | StockResearchFactPack、ResearchResult/Claim/SelfReview |
| Strategy | StrategySpec、ResolvedStrategySpec、Promotion Proposal |
| Backtest | RunBundle、BacktestRun、Prediction/Execution/Validation |
| Task | Task、Attempt、Lease、Checkpoint、Artifact索引 |
| Auth/Ops | Session、Audit、Deployment/Backup/Restore Manifest |

一个数据库表只有一个owner module。跨模块读取通过Repository Port或只读Projection；禁止双模块共同更新同一业务行。

## 3. 目标目录与增量迁移

遵循现有仓库边界，在不一次性重写旧系统的前提下采用：

```text
src/
├── schemas/platform/              # 公共枚举、Pydantic Schema、JSON Schema导出
├── core/platform/                 # 纯领域Policy、状态机、Resolver、Compiler
├── services/platform/             # Application Services
├── repositories/platform/         # Repository Ports和实现
├── workers/platform/              # 持久Task Handlers
└── artifacts/                     # StorageRef、Manifest、原子发布
data_provider/
└── platform/                      # 新Provider Adapter；保留现有Fetcher兼容层
api/v1/
├── endpoints/                     # 分域Router
└── schemas/                       # API请求/响应投影，复用公共Schema
apps/dsa-web/src/
├── api/                           # 生成客户端、请求封装
├── features/                      # market/sector/stock/review/strategy/backtest/ops
├── components/                    # 真正跨域的共享组件
├── pages/                         # 路由页面组合
└── types/generated/               # 自动生成，禁止手改
migrations/                        # PostgreSQL Alembic Migration
tests/
├── contracts/
├── integration/platform/
├── golden/platform/
└── performance/platform/
```

实施时可以按Milestone逐步创建目录。禁止为了目录美观移动全部现有模块；每次只迁移当前契约涉及的调用链，并保留显式Legacy Adapter。

## 4. Python规范

### 4.1 语言与类型

- 目标Python兼容当前项目支持版本，新增代码必须有完整类型标注；
- 公共Schema使用Pydantic，内部不可变值对象优先`dataclass(frozen=True)`；
- 金额、价格、费率、权重使用`Decimal`或明确缩放整数，不使用二进制`float`参与账本和Hash；
- 时间使用timezone-aware `datetime`，数据库使用`timestamptz`；
- 交易日使用`date`并通过市场日历解释；
- 路径使用`pathlib.Path`，Storage Contract边界使用`StorageRef`而非裸路径字符串；
- 枚举继承`str, Enum`，序列化值固定大写/小写取决于契约，不能混用。

### 4.2 命名

```text
类/Schema：PascalCase
函数/变量/字段：snake_case
常量：UPPER_SNAKE_CASE
资源字段：<resource>_id
资源引用：<resource>_ref或resource_ref
时间：*_at（timestamptz）、*_date（date）
布尔：is_*/has_*/can_*；契约已固定字段除外
```

禁止新增语义不明的`data/info/result/status/version/hash/date/time`单字段。

产品展示名统一为`Visory`，新Compose Project、Docker网络、新服务名和新产品级配置前缀统一为`visory`或`VISORY_`。已有`daily_stock_analysis`、`DSA_*`、`apps/dsa-web`和Python遗留包名只在兼容层保留；不得在业务PR中顺手全局重命名。

### 4.3 纯函数和副作用

- Identity解析、状态转换、Hash规范化、指标公式、费用和市场规则尽量写成纯函数；
- 网络、数据库、文件、时钟、随机数和LLM通过Port注入；
- 正式计算显式传入`cutoff_at`、Snapshot和随机种子；
- 禁止在领域函数内调用`datetime.now()`推断业务时点；
- 禁止Import时建立数据库连接、启动线程或读取Secret。

### 4.4 异常

领域异常至少包含稳定`error_code`、可公开message、结构化details、retryable和cause。边界层记录Cause并脱敏，API只返回公开字段。

```python
class PlatformError(Exception):
    error_code: str
    public_message: str
    retryable: bool
```

禁止：

- `except Exception: return None/[]/False`；
- 把Provider超时包装成空数据成功；
- 依赖异常字符串做状态机判断；
- 把堆栈、SQL、Token、绝对路径返回前端。

### 4.5 日志

使用结构化字段：

```text
event
request_id
task_id
attempt_id
resource_type/resource_id
entity_key
dataset_id
trade_date
duration_ms
outcome/failure_code
```

日志message描述事件，不拼接整份Payload。密码、Cookie、Authorization、Provider Key、LLM Key、Turnstile Token和新闻全文必须脱敏。

## 5. Schema与契约实现

### 5.1 单一Schema源

公共枚举和对象Schema在`src/schemas/platform`定义并导出JSON Schema；API Schema引用或投影公共Schema；前端类型从OpenAPI/JSON Schema生成。禁止Python、FastAPI和TypeScript各自维护三套枚举。

### 5.2 Schema要求

每个正式资源Schema必须：

- `extra="forbid"`或等价严格输入；
- 明确必填/可空，空字符串不等于空值；
- 对ID、版本、Hash、时区和StorageRef加验证；
- 对组合不变量使用Model Validator；
- 示例包含成功、Partial、Correction和拒绝Payload；
- 序列化稳定，Hash Profile排除运行字段；
- 破坏性变更提升Major并提供Adapter/迁移。

### 5.3 Contract Registry

代码中的Registry至少可查询：Contract ID、Schema版本、Owner、JSON Schema、Hash Profile、Storage Profile、Retention和兼容Adapter。CI检查实现对象都已登记，并检查文档目录中的Contract ID无悬空。

## 6. PostgreSQL与Migration

### 6.1 迁移原则

- 目标平台控制面使用PostgreSQL；现有SQLite继续服务Legacy功能直到对应读写完成迁移；
- 引入Alembic，每个Migration只做一种可审查变化；
- 使用Expand → Backfill → Dual-read Verify → Cutover → Contract流程；
- Migration必须可在空库和最近生产基线执行；
- 大回填由可恢复Task完成，不在锁表Migration中执行；
- 不自动删除旧列/表，Contract阶段单独批准；
- 所有时间列显式`timestamptz`，ID/Hash/状态有Check/Unique约束。

### 6.2 表设计

- 表名/列名snake_case；
- 正式不可变资源只Insert，更新Current Pointer或控制字段使用独立表；
- 业务唯一约束显式实现，不能只靠Service去重；
- 外键按模块边界权衡：同模块强外键，跨Artifact大对象至少做应用级引用完整性和发布Gate；
- JSONB只用于真正可扩展结构，关键查询字段必须独立列；
- 金额/权重用`numeric(p,s)`；
- 索引来自实际查询，Migration说明查询和空间成本；
- Task租约和Pointer更新使用事务、条件Update和行锁，避免读后写竞态。

### 6.3 Repository

Repository方法用领域语义命名：`publish_snapshot`、`acquire_task_lease`、`append_attempt_event`，避免向Service泄露通用`save(dict)`。事务边界由Application Service控制，Repository不得悄悄提交。

## 7. Parquet、DuckDB与Artifact

- Parquet列顺序、类型、Decimal精度、时区和压缩由Dataset/Feature Schema定义；
- 默认ZSTD，行组大小通过Benchmark确定；
- 分区不按单股单日制造小文件；
- DuckDB只读取发布Manifest列出的文件；
- 不用Glob发现正式输入；
- 查询必须固定Snapshot/Partition ID，不能查询可变目录；
- Worker按C-003写`.staging`、校验、fsync、rename、数据库事务；
- API下载只接受Artifact ID；
- 文件Hash、Manifest Hash和结果Hash分别计算并保存Hash Profile版本。

## 8. Provider Adapter

Adapter接口至少拆分：

```text
capabilities()
build_request()
fetch_raw()
observe_schema()
normalize()
map_identity()
```

规则：

- Timeout、Retry、Rate Limit、分页和响应大小有硬限制；
- Retry只对幂等请求，使用指数退避和Jitter；
- 实际上游、请求指纹、响应Hash、Schema变化和时间全部记录；
- Adapter不得决定DataSnapshot是否Certified；
- Adapter不得静默调用未在ProviderPolicy声明的备源；
- 外部字段变化进入Quarantine并触发Schema Drift告警；
- 在线测试使用明确`network` marker，CI默认离线Contract Fixture。

## 9. 指标、策略与Hikyuu

### 9.1 指标

- IndicatorDefinition是公式唯一权威；
- 指标实现对输入窗口、Warmup、Null、单位和精度有测试；
- 横截面函数显式传入当日PIT股票池；
- 禁止在页面、SQL Mart和策略插件分别实现同名公式；
- 数值测试使用固定Tolerance，账本/Hash字段不使用模糊比较。

### 9.2 Strategy DSL

- DSL解析为白名单AST；
- 禁止`eval/exec`、文件、网络、数据库、动态Import；
- Compiler输出ResolvedSpec、依赖、诊断和确定性Hash；
- 受控插件有注册名、Schema、代码Hash、时间/内存限制和纯输入输出；
- Preview/Formal/Paper共用Resolver/Compiler，模式差异只来自Run Policy。

### 9.3 Hikyuu Adapter

- 只消费固定DataSnapshot/FeatureBundle和可重建Hikyuu缓存；
- 禁止运行时联网补数；
- 市场规则、费用、权重和随机种子来自RunBundle；
- Adapter输出标准Prediction/Order/Execution/Position/Trade/NAV/Validation；
- Hikyuu原生对象不直接穿透API；
- 每次升级Hikyuu或Adapter运行Golden规则和确定性对照。

## 10. Task与Worker

- API Command先在PostgreSQL创建Task再返回202；
- Worker通过能力标签和租约领取任务；
- 每个Handler声明支持的Task Type、输入Schema、阶段枚举、资源预算和重试策略；
- Phase边界持久化，进度应代表可解释的工作单元，不伪造线性百分比；
- 重试创建新Attempt；
- 取消在Provider分页、LLM角色、Feature分区、Hikyuu阶段等安全点检查；
- Worker失联由Lease Reaper处理，旧Lease不能发布；
- 任务成功必须在同一事务/协议内绑定正式Result或明确无Result的命令结果；
- Scheduler只创建幂等Task，不直接运行领域逻辑。

## 11. FastAPI规范

### 11.1 路由

资源使用复数名词：

```text
/api/v1/data-snapshots
/api/v1/feature-snapshots
/api/v1/market-observations
/api/v1/stock-research
/api/v1/strategies
/api/v1/backtests
/api/v1/tasks
/api/v1/artifacts
```

Command需要动作时使用子资源或明确命令，如`POST /backtests`、`POST /tasks/{id}/cancellations`，避免`POST /doBacktest`。

### 11.2 响应

- 使用C-010统一Envelope和错误码；
- 创建异步任务返回202、Task Resource和Location；
- Current Pointer查询返回实际资源ID；
- 列表使用Opaque Cursor；
- 大字段/文件返回Artifact链接，不嵌入Base64；
- OpenAPI描述状态、错误、示例和弃用；
- 认证和权限默认拒绝，健康检查只暴露最小信息。

### 11.3 兼容

现有`/api/v1/backtest`、`/analysis/market-review`等Legacy入口可以通过Adapter保留。新内部对象不得反向采用Legacy字段；兼容响应由边界投影生成并记录使用指标。

## 12. React与TypeScript规范

### 12.1 组件分层

```text
Page → Feature Container → Query/Command Hook → Generated API Client
     → Presentational Components
```

- Page负责路由和组合；
- Feature拥有领域查询、筛选和交互；
- 通用组件不包含股票领域公式；
- Zustand只保存跨页面UI/会话状态，不缓存正式业务真源；
- 服务端状态通过统一Query层管理，避免每组件自行Axios；
- TypeScript开启严格模式，禁止无理由`any`和类型断言掩盖接口漂移。

### 12.2 UI契约

- 每页实现页面原型文档的全部通用状态；
- URL保存trade_date、tab、filter和resource ID；
- Snapshot状态和Evidence入口不能被响应式布局隐藏；
- Command按钮防重复，使用Idempotency Key；
- 长任务跳转Task或内联显示Task，刷新后可恢复；
- 金额、百分比、日期和市场代码使用统一Formatter；
- 图表Tooltip展示单位、口径和数据时间；
- 错误显示稳定code和request_id。

### 12.3 安全

- 不把Secret、Session Token或Turnstile Secret写入LocalStorage；
- Cookie Session由浏览器安全属性管理；
- Markdown使用受控Renderer，禁用危险HTML/URL；
- Artifact下载走同源认证；
- 不将研究Prompt、用户敏感配置或完整Payload放入URL/Analytics。

## 13. AI、Prompt与Evidence

- Prompt Profile版本化，模板、输入Schema、输出Schema和模型能力要求分离；
- LLM输入只来自固定FactPack和显式External Evidence；
- 强制结构化输出，解析失败进入Repair Attempt并有限次数重试；
- Claim必须引用Evidence，缺证据使用`UNSUPPORTED/INSUFFICIENT_EVIDENCE`；
- AI不能声明修改事实、发布策略或批准资金权重；
- 模型名、Provider、参数、输入/输出Hash、Token和时延写Attempt审计；
- Prompt包含“不是投资建议”等文案不能替代系统的机械质量门禁。

## 14. 测试规范

### 14.1 测试层次

| 层 | 内容 |
| --- | --- |
| Unit | Resolver、状态机、公式、Hash、市场规则、Formatter |
| Schema/Contract | Golden Payload、JSON Schema、OpenAPI、前后端类型 |
| Repository | PostgreSQL约束、事务、租约、并发、Migration |
| Integration | Provider Fixture→Snapshot→Feature→FactPack/Run |
| Hikyuu Golden | T+1、涨跌停、费用、复权、账本和确定性 |
| API | Auth、Envelope、错误码、幂等、Cursor、Artifact权限 |
| UI | 状态、关键旅程、移动端、Evidence、任务恢复 |
| Security | 路径穿越、CSRF、Session、Turnstile、Secret泄露 |
| Performance | 16:00链路、全市场Feature、回测、页面P95、磁盘 |
| Restore | Backup/Restore Manifest、抽样读取、缓存重建 |

### 14.2 必测反例

- 无时区时间；
- 歧义Alias和冲突Provider Symbol；
- Duplicate Key、NaN/Inf、单位变化和Schema Drift；
- Correction覆盖企图；
- PIT未来数据；
- 重复Command和Lease Lost发布；
- Partial数据被Formal消费；
- 全球数据进入RunBundle；
- Preview标记Formal；
- AI Claim无Evidence；
- Artifact路径穿越；
- Turnstile客户端伪造；
- Secret出现在日志/Manifest。

### 14.3 测试数据

- `tests/golden/platform`只保存小型、脱敏、许可证允许的Fixture；
- 每个Fixture带来源说明、Schema版本、预期Hash和更新时间；
- 时间、随机和UUID生成器可注入；
- 网络测试不作为普通单元测试的成功前提；
- Snapshot/Parquet测试必须验证Schema和内容，不只判断文件存在。

## 15. 安全编码

- 密码使用Argon2id，Session Token只保存Hash；
- Secret通过文件或受控Secret机制注入；
- SQL使用参数绑定；
- StorageRef经过规范化和根目录边界检查；
- Provider URL和外部Evidence抓取防SSRF，限制协议、域名、DNS/IP和响应大小；
- 反向代理头只信任NPM/Cloudflare受控来源；
- CORS不与无认证公网模式并存；
- 容器非root、只读根文件系统优先、Capability最小化、无Docker Socket；
- 依赖固定版本/Lockfile，镜像固定Digest，定期安全扫描。

## 16. 性能与资源规范

- API请求不做全市场计算、Hikyuu回测或LLM研究；
- 页面读取日级Mart/Projection并分页；
- 盘后任务按分区增量和依赖DAG运行；
- 单重Worker默认只运行一个重任务，轻任务并发必须Benchmark；
- 使用Process隔离Hikyuu/科学计算内存，超时后可靠终止子进程；
- 每个Task记录CPU时间、峰值内存、读写字节、输出大小；
- 优化不能牺牲正式数据范围/口径；若资源不足应排队、降级非核心功能或拒绝任务。

## 17. Definition of Done

实现PR必须提供：

1. 对应FR/NFR、Contract ID和Milestone；
2. Schema/迁移/API/页面/任务影响面；
3. 成功、降级、失败和Correction/重试路径；
4. 单元、Contract、Integration及适用的UI/Hikyuu/Security测试；
5. PIT、幂等、权限、资源和回滚说明；
6. OpenAPI、`.env.example`、相关文档和`docs/CHANGELOG.md`同步；
7. 实际运行的命令和结果，未运行项明确说明；
8. 页面变化的截图或视觉证据；
9. 数据Migration和Legacy兼容指标；
10. 无新增未登记契约、裸状态、第二事实源或绝对存储路径。

## 18. Claude Code任务规则

Claude Code每次只领取一个可验收Work Package：

```text
目标FR/Contract
允许修改的模块
输入/输出Schema
迁移要求
反例和验收测试
验证命令
文档同步
回滚方式
```

执行前先搜索现有实现和测试；执行后必须对照真实Diff重新审查完整调用链。发现契约未决、数据不可得或需要扩大权限时停止实现并记录Decision，而不是猜测默认值或堆叠Fallback。

## 19. 推荐验证命令

按改动面运行，具体以`AGENTS.md`为准：

```bash
./scripts/ci_gate.sh
python -m pytest -m "not network"
python -m py_compile <changed_python_files>

cd apps/dsa-web
npm ci
npm run lint
npm run test
npm run build
npm run test:smoke
```

PostgreSQL、Hikyuu、Docker、性能和恢复测试需在后续实施方案提供对应可复现脚本；不存在脚本时不能用“人工看起来正常”替代。

## 20. 参考文档

- [需求与功能闭环 v1](product-requirements-and-feature-closure-v1.md)
- [平台实现契约目录 v1](platform-implementation-contract-catalog-v1.md)
- [页面信息架构与低保真原型 v1](page-prototypes-and-information-architecture-v1.md)
- [实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)
- [部署安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
