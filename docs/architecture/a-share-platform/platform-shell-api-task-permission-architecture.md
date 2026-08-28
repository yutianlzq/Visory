# Visory 模块化单体、API、任务与权限架构 v1

状态：Design Approved
最后更新：2026-08-28

## 1. 决策摘要

本模块落实架构决策 **D-031**：

- 以daily_stock_analysis现有React/Vite前端、FastAPI后端、Agent运行能力和部署入口作为主平台壳；
- 采用模块化单体，不把市场、板块、个股研究、策略、回测和复盘拆成独立微服务；
- 模块化单体允许API、调度器和Worker以不同进程运行，但它们共享同一代码版本、契约和PostgreSQL控制面；
- React/Vite只保留一套页面和路由，Vibe-Research与tick-stock-panel仅作为布局、图表和交互参考；
- FastAPI统一提供`/api/v1`查询、命令、任务、历史、权限和运维接口，不新增独立API Gateway；
- PostgreSQL保存用户、会话元数据、任务、Attempt、版本、Manifest、审计和业务控制记录；
- Parquet与DuckDB承载行情、特征、观察结果和分析读取，不把大规模时序数据复制到PostgreSQL；
- 正式数据、Feature、Strategy、Hikyuu回测、DSA复盘和深度个股研究统一使用PostgreSQL持久任务；
- 当前服务器只运行一个重任务执行槽，按数据认证、正式策略、核心复盘、交互任务和研究任务顺序调度；
- MVP只启用唯一`owner`；`viewer`的只读权限契约保留作为MVP后扩展，首版不创建viewer、团队、组织、租户和复杂RBAC；
- 当前管理员密码会话平滑迁移为`owner`，已有REST、Bot和Web入口通过兼容Adapter逐步接入新权限和任务协议；
- 不引入Redis、Kafka、NATS、Kubernetes、服务网格、独立BFF或第二套前端；
- 平台页面不自行重算指标、评分和收益，只读取已经发布的Snapshot、Result和Page Projection。

## 2. 目标

主平台要把此前已经确定的数据、指标、市场、板块、研究、策略、回测和复盘模块组合为一套可运行、可理解、可追溯的个人A股工作台。

v1必须满足：

1. 用户在一套导航和身份体系中完成观察、研究、策略验证和复盘；
2. 页面、API、任务和通知引用相同Snapshot与Result，不产生第二种口径；
3. 重任务在进程重启后仍可恢复、重试、取消和审计；
4. 数据认证与正式策略在16:00至19:00的关键窗口拥有最高资源优先级；
5. 页面能够明确展示数据日期、发布状态、版本、缺失、修订和降级；
6. 查询接口与命令接口分离，刷新页面不会重复提交任务；
7. 所有正式写操作具有操作者、时间、原因和幂等键；
8. 股票入口统一解析为带市场前缀的`canonical_id`；
9. 研究观点、策略信号、回测业绩和客观事实在界面与API中明确分域；
10. 单机资源不足时通过排队、裁剪和降级保证核心链路，而不是生成不完整的正式结果；
11. 现有DSA功能能够分阶段迁移，不要求一次性替换；
12. 后续增加服务器资源时可以增加Worker，而不重写任务和领域契约。

## 3. 非目标

v1不建设：

- 面向公众的SaaS、多租户计费或团队协作平台；
- 交易所级实时行情、毫秒级推送或高频交易终端；
- 自动实盘下单和券商账户托管；
- 多区域容灾、跨机房高可用或无限水平扩缩容；
- 每个领域独立数据库、独立部署和独立技术栈；
- 由前端拼接原始表并现场计算权威指标；
- 允许任意用户上传Python并在主进程执行；
- 让LLM直接获得数据库、Shell、宿主机文件或管理接口权限；
- 用一个通用“总分”覆盖市场、板块、研究和策略的不同语义；
- 以删除历史结果的方式处理修订、失败或版本升级。

## 4. 现有DSA能力与迁移判断

### 4.1 可以直接延续

当前仓库已经具备：

- React 19、Vite、TypeScript、React Router和Recharts前端基础；
- FastAPI应用工厂和`/api/v1`聚合路由；
- 股票分析、历史、回测、组合、筛选、资讯、告警、Agent和系统配置接口；
- Web管理员密码、登录会话和受保护配置能力；
- 分析任务的提交、进度、取消、事件订阅和Run Flow诊断；
- LLM路由、通知、报告、历史数据和多种Provider；
- Web、CLI、Bot和桌面端入口。

这些能力应作为迁移基础，不新建第二个应用仓库。

### 4.2 必须升级

当前实现与目标平台的主要差距为：

1. 部分任务主要驻留进程内存，进程重启后的正式任务可靠性不足；
2. 不同端点各自定义任务状态和返回结构，缺少跨模块统一Task Contract；
3. 当前认证主要是单管理员开关，缺少只读访问和操作级权限；
4. 当前页面以分析、聊天、组合、筛选和设置为主，尚未形成市场—板块—个股—研究—策略—回测—复盘闭环；
5. 页面缺少统一Snapshot状态条、数据质量说明和证据抽屉；
6. 正式结果与交互临时结果尚未在所有模块使用统一发布语义；
7. API历史包袱中存在动词、资源和任务查询口径不一致；
8. 多种后台作业尚未统一进入资源优先级和租约管理。

升级采用兼容迁移，不中断现有REST和Web能力。

## 5. 总体逻辑架构

```text
Browser / Desktop / Bot / CLI
              │
              ▼
┌─────────────────────────────────────────────────────┐
│ React/Vite Unified Web Shell                        │
│ Dashboard / Market / Sector / Stock / Research      │
│ Strategy / Backtest / Review / Tasks / Settings     │
└────────────────────────┬────────────────────────────┘
                         │ /api/v1 + SSE
                         ▼
┌─────────────────────────────────────────────────────┐
│ FastAPI Modular Monolith                            │
│ Auth │ Query Projection │ Command │ Task │ Audit     │
│ Data │ Feature │ Market │ Sector │ Research          │
│ Strategy │ Backtest │ Review │ Portfolio │ Notify    │
└──────────────┬──────────────────────┬───────────────┘
               │                      │ submit/query
               ▼                      ▼
┌──────────────────────────┐  ┌────────────────────────┐
│ PostgreSQL Control Plane │  │ Durable Task Executor  │
│ users/session/task/run   │  │ scheduler + one heavy │
│ manifest/spec/audit      │  │ execution slot        │
└──────────────┬───────────┘  └───────────┬────────────┘
               │                          │
               ▼                          ▼
┌─────────────────────────────────────────────────────┐
│ Data Plane                                           │
│ Raw / Normalized / Feature / FactPack / Result       │
│ Parquet + DuckDB + immutable manifests               │
└─────────────────────────────────────────────────────┘
```

“模块化单体”约束的是代码和业务边界，不要求所有工作运行在同一个进程。API不得直接执行长时间Hikyuu回测或深度多Agent研究。

## 6. 模块边界

### 6.1 模块清单

| 模块 | 主要职责 | 权威输出 | 禁止事项 |
| --- | --- | --- | --- |
| Identity | Canonical股票、板块、指数和交易日身份 | Identity Record | 页面自行猜市场或裸码落库 |
| Access | 用户、登录、Session、Token、权限和安全事件 | Principal、Grant、Session | 业务模块直接验证密码 |
| Data Platform | Provider、Raw、Normalized、质量和DataSnapshot | Certified DataSnapshot | 直接向页面返回Provider私有对象 |
| Feature | Indicator Registry、Feature DAG和FeatureSnapshot | 已发布Feature | 运行时修改已发布Definition |
| Market | 市场宽度、情绪、资金行为和全球观察 | Market Observation | 把全球影响写入A股策略 |
| Sector | 板块资金、异动、热点和成员时点关系 | Sector Observation | 建立平台统一板块分数 |
| Stock | 个股事实卡和股票聚合查询 | Stock Projection | 把AI观点写成事实字段 |
| Research | L1/L2研究、证据、辩论、自查和历史 | ResearchResult | 自动转成StrategySignal |
| Strategy | StrategySpec、版本、Preview和Promotion审批 | StrategyVersion | 执行任意YAML代码 |
| Backtest | Hikyuu Run、Attempt、交易、指标和验证 | BacktestResult | 使用另一套正式收益内核 |
| Review | DSA FactPack、AI分析、报告和观察验证 | ReviewReport | 将观察验证包装成回测收益 |
| Portfolio | 自选、模拟组合、持仓观察和风险展示 | Paper Portfolio Snapshot | v1自动实盘下单 |
| Intelligence | 新闻、公告、政策、事件和证据许可 | Evidence Record | 无来源补写消息 |
| Task | 提交、租约、优先级、取消、重试和Artifact发布 | Task/Attempt | 仅以内存状态作为正式记录 |
| Notification | 报告和任务通知、渠道投递记录 | Delivery Record | 通知内容成为权威数据源 |
| Operations | 数据健康、任务、资源、审计和配置 | Ops Projection | 暴露密钥或宿主机任意文件 |

### 6.2 依赖方向

允许的主依赖方向为：

```text
Identity / Access
       ↓
Data Platform
       ↓
Feature ──────────────┐
       ↓              │
Market / Sector / Stock
       ↓              │
Research / Review     │
       │              │
Strategy ─────────────┘
       ↓
Backtest / Paper Portfolio
```

Task、Notification和Operations是横切模块，但不能反向成为业务事实来源。

### 6.3 模块通信规则

- 同进程模块通过显式Service接口调用，不跨模块读取Repository私有表；
- 长任务通过Task Payload和Artifact Reference通信；
- 页面通过Projection API读取，不直接访问DuckDB或PostgreSQL；
- 跨域引用保存不可变ID、版本和Hash，不复制可变对象；
- 一个模块不能更新另一个模块已经发布的Result；
- 需要修订时发布新版本并记录`supersedes_id`；
- 所有正式计算统一通过Identity Resolver、Snapshot Resolver和PIT Gate。

## 7. 运行单元

### 7.1 Web静态资源

- React/Vite构建为静态资源；
- 生产环境由同一站点入口提供，避免跨域和重复认证；
- Web只保存主题、布局和未提交表单等本地UI状态；
- 权威筛选、列表、任务和结果状态均来自API；
- 不在浏览器保存Provider Token、LLM Key或数据库凭据。

### 7.2 Platform API

FastAPI进程负责：

- 登录、权限、参数校验和限流；
- 同步轻查询和Page Projection；
- 长任务提交、幂等检查、取消请求和状态查询；
- SSE事件转发；
- Artifact受控下载；
- 健康检查和低成本诊断。

FastAPI进程不负责：

- 全市场数据采集；
- Feature批量计算；
- Hikyuu正式回测；
- L2多Agent深度研究；
- 大规模历史回填；
- 长时间持有数据库事务等待外部Provider或LLM。

### 7.3 Scheduler

- 只允许一个调度器持有Singleton Lease；
- 根据交易日历创建16:00盘后任务链；
- 定期检查晚到数据、Correction、失败重试和超时租约；
- Scheduler只创建任务，不直接执行重计算；
- 重启后依据PostgreSQL重新对账，不依赖内存中的下一次运行时间；
- 手工`run-now`同样生成可审计Task，不绕过优先级。

### 7.4 Durable Worker

当前服务器v1使用一个重任务执行槽：

- Worker从PostgreSQL以事务和租约领取任务；
- 同一时刻只执行一个`HEAVY`任务；
- 少量`LIGHT`任务最多双线程，但必须设置CPU、内存和超时预算；
- Hikyuu、历史回填和深度研究优先在受控子进程中执行，便于超时终止和内存回收；
- Worker心跳停止后，任务进入租约过期处理，不直接标记成功或失败；
- 增加服务器资源时可以增加同版本Worker，并按Capability领取任务。

### 7.5 Capability标签

首批Capability：

```text
DATA_IO
FEATURE_COMPUTE
HIKYUU
LLM_LIGHT
LLM_DEEP
REPORT_RENDER
NOTIFICATION
MAINTENANCE
```

Task必须声明Capability、资源等级和预计预算，不能由Worker运行时猜测。

## 8. 前端信息架构

### 8.1 一级导航

建议正式导航顺序：

1. 总览；
2. 大盘；
3. 板块；
4. 个股；
5. 个股研究；
6. 策略中心；
7. 回测实验室；
8. 收盘复盘；
9. 自选与模拟组合；
10. 数据与任务；
11. 系统设置。

聊天、告警和用量不占据主要研究路径：聊天作为全局助手入口，告警归入自选/任务，用量归入系统设置。

### 8.2 路由

| 路由 | 页面 | 主要输入 |
| --- | --- | --- |
| `/` | 总览 | 最近Certified Snapshot、Watchlist、任务和复盘摘要 |
| `/market` | A股大盘 | MarketObservationSnapshot |
| `/market/global` | 全球观察 | GlobalObservationSnapshot，仅背景 |
| `/sectors` | 板块中心 | SectorObservationSnapshot |
| `/sectors/:sector_id` | 板块详情 | PIT成员、资金、异动、事件 |
| `/stocks/:canonical_id` | 个股事实页 | StockResearchFactPack的L0投影 |
| `/research` | 研究中心 | Candidate、L1/L2任务和历史 |
| `/research/:research_id` | 研究详情 | ResearchResult与Evidence |
| `/strategies` | 策略中心 | StrategySpec与版本 |
| `/strategies/:strategy_id` | 策略详情 | Spec、Preview、Promotion和Run |
| `/backtests` | 回测实验室 | Backtest列表、比较和任务 |
| `/backtests/:run_id` | 回测详情 | Run、Attempt、绩效、交易和血缘 |
| `/reviews` | 收盘复盘 | ReviewReport列表 |
| `/reviews/:review_id` | 复盘详情 | FactPack、Analysis、Report和Validation |
| `/portfolio` | 自选与模拟组合 | Watchlist、Paper Portfolio和风险 |
| `/operations` | 数据与任务 | Snapshot、Task、资源和告警 |
| `/settings` | 系统设置 | Provider、LLM、通知、权限和备份状态 |

### 8.3 旧路由兼容

- 现有`/backtest`可重定向到`/backtests`；
- 现有`/screening`在Strategy中心完成迁移前保持可用；
- 现有`/decision-signals`在Strategy中心以“信号历史”子页呈现；
- 现有`/chat`保留为全局研究助手；
- 现有`/alerts`并入Operations和Portfolio后保留兼容重定向；
- 旧链接至少保留一个稳定版本周期，不立即删除。

### 8.4 全局页面组件

所有数据页面共用：

- `SnapshotStatusBar`：交易日、`as_of`、`available_at`、发布状态和修订号；
- `DataQualityBadge`：完整、降级、缺失、延迟和冲突；
- `EvidenceDrawer`：Fact、Provider、Raw Hash和披露时间；
- `TaskProgressPanel`：进度、队列原因、预算、取消和Artifact；
- `VersionSelector`：当前版本、历史版本和Correction差异；
- `CanonicalStockLink`：统一股票身份跳转；
- `ResearchStrategyBoundary`：研究观点与策略信号的视觉隔离；
- `GlobalObservationNotice`：全球数据仅作观察的固定提示。

### 8.5 页面展示原则

- 大盘页展示情绪各维度和资金证据，不只显示一个总分；
- 板块页展示独立榜单、资金、异动和公开排名，不显示平台统一热点分；
- 个股页默认先展示L0客观事实，再显示L1/L2研究；
- 策略页显示策略专属评分及贡献，不能复用页面观察排名冒充信号；
- 回测页分别展示预测、执行、收益验证和失败样本；
- 复盘页区分事实、AI分析、报告和T+1观察验证；
- 数据缺失使用明确空状态，禁止显示为零；
- 所有AI文本提供“查看证据”和“查看数据限制”入口。

## 9. API设计

### 9.1 分域路由

新平台逐步形成以下资源域：

```text
/api/v1/auth
/api/v1/identities
/api/v1/market
/api/v1/sectors
/api/v1/stocks
/api/v1/research
/api/v1/strategies
/api/v1/backtests
/api/v1/reviews
/api/v1/portfolio
/api/v1/intelligence
/api/v1/tasks
/api/v1/snapshots
/api/v1/operations
/api/v1/settings
```

现有`analysis`、`history`、`screening`、`decision-signals`等端点在迁移期继续服务，并通过内部Adapter调用新Service。

### 9.2 Query与Command分离

Query：

- 使用`GET`；
- 不修改服务端状态；
- 可分页、缓存、条件请求；
- 返回Projection或不可变Result；
- 不因缺少可选块而触发后台抓取。

Command：

- 使用`POST`提交研究、回测、修订、发布、取消或重试；
- 必须校验权限、版本、快照和幂等键；
- 长操作返回`202 Accepted`和`task_id`；
- 不在HTTP连接内等待长任务完成；
- 高风险命令记录原因并可要求重新认证。

### 9.3 标准响应信封

单资源查询：

```json
{
  "data": {},
  "meta": {
    "request_id": "req_...",
    "generated_at": "2026-08-27T20:30:00+08:00",
    "snapshot_id": "...",
    "data_status": "CERTIFIED",
    "warnings": []
  }
}
```

任务接受：

```json
{
  "data": {
    "task_id": "task_...",
    "task_type": "BACKTEST_FORMAL",
    "state": "QUEUED",
    "deduplicated": false
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

错误：

```json
{
  "error": {
    "code": "snapshot_not_certified",
    "message": "T日核心数据尚未认证",
    "details": {},
    "retryable": true
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

### 9.4 API通用规则

- 时间使用带时区ISO 8601，交易日另存`trade_date`；
- 金额和高精度数值不得由浮点序列化改变权威结果；
- 股票资源使用`canonical_id`，输入别名先经Identity Resolver；
- 分页采用稳定排序和Cursor，不使用不稳定的大偏移分页处理正式历史；
- 写命令支持`Idempotency-Key`；
- 版本更新使用`If-Match`或显式`expected_version`防止丢失更新；
- Artifact下载通过受控ID，不接受任意文件路径；
- 批量导出生成Task和Artifact，不在API进程拼接大文件；
- 管理接口与普通业务接口使用不同权限；
- OpenAPI是API契约产物，但不能代替领域设计文档。

### 9.5 Page Projection

前端不应为一个页面调用十几个底层接口并自行推导状态。每个核心页面可提供聚合投影：

```text
GET /api/v1/market/overview
GET /api/v1/sectors/{sector_id}/overview
GET /api/v1/stocks/{canonical_id}/overview
GET /api/v1/research/{research_id}/view
GET /api/v1/backtests/{run_id}/view
GET /api/v1/reviews/{review_id}/view
GET /api/v1/operations/overview
```

Projection只组合已经发布的数据，不生成新指标。每个字段仍保留来源资源ID或Block ID。

## 10. 统一持久任务中心

### 10.1 核心实体

#### Task

```text
task_id
task_type
task_key
requested_by
requested_at
priority
capability
resource_class
payload_ref
state
blocked_reason
deadline_at
max_attempts
cancel_requested_at
active_attempt_id
result_artifact_id
created_from_task_id
```

#### TaskAttempt

```text
attempt_id
task_id
attempt_no
worker_id
lease_token_hash
lease_expires_at
started_at
heartbeat_at
finished_at
exit_status
error_code
error_summary
checkpoint_ref
resource_usage
log_artifact_id
```

#### TaskArtifact

```text
artifact_id
artifact_type
content_hash
storage_uri
mime_type
size_bytes
created_at
producer_attempt_id
retention_class
```

#### TaskEvent

```text
event_id
task_id
attempt_id
event_type
event_at
progress
message_code
safe_message
details
```

### 10.2 状态机

```text
ACCEPTED
   │
   ▼
QUEUED ───────► BLOCKED ───────► QUEUED
   │                 │
   ▼                 └──────────► CANCELLED
LEASED
   │
   ▼
RUNNING ──────► RETRY_WAIT ─────► QUEUED
   │  │  │
   │  │  ├────► FAILED
   │  ├───────► CANCELLED
   ├──────────► DEGRADED
   └──────────► SUCCEEDED
```

规则：

- `BLOCKED`必须保存确定性原因，如等待Certified Snapshot或磁盘水位过高；
- `LEASED`尚未开始业务执行，租约丢失可安全重新领取；
- `RUNNING`租约过期后先进入对账，不能同时由两个Worker发布结果；
- `DEGRADED`仅用于契约明确允许的降级成功；
- `FAILED`与`CANCELLED`都不得发布正式Artifact为当前版本；
- 重试创建新Attempt，不能覆盖旧Attempt日志和资源统计；
- 取消是协作式请求；超时后可终止受控子进程；
- 已成功任务不能重置为运行态，重新运行生成新Task或显式Retry Task。

### 10.3 任务幂等

`task_key`由确定性输入生成，例如：

```text
task_type
trade_date / target_id
data_snapshot_id
feature_snapshot_id
strategy_version_id / research_profile_version
runtime_contract_version
request_mode
```

相同`task_key`存在活跃或成功Task时：

- 默认返回已有Task；
- 用户显式选择“重新运行”时创建新Task并记录`created_from_task_id`；
- 重新运行不得覆盖旧Result；
- Correction使用新的Snapshot ID，因此自然生成不同Task Key。

### 10.4 优先级

| 优先级 | 任务 | 调度要求 |
| --- | --- | --- |
| P0 | 核心数据采集、质量门禁、认证、Correction、正式Strategy | 可阻止低优先级新任务领取 |
| P1 | F1/F2核心Feature、市场/板块观察、主收盘复盘 | P0完成后执行，满足盘后SLA |
| P2 | 用户L0/L1、页面导出、Preview、通知 | 交互任务，设置短预算 |
| P3 | Research回测、L2深度研究、历史回填和维护 | 关键窗口排队，可暂停或续跑 |

同优先级按Deadline、创建时间和公平性排序。手工操作不能把P3伪装成P0。

### 10.5 16:00盘后资源门禁

- 16:00开始，停止领取新的P3重任务；
- 已运行P3在Checkpoint边界协作暂停；
- 16:00—19:00优先执行P0和P1；
- 19:00正式策略硬截止后，未满足数据门禁的Formal Run阻断；
- 19:05以后允许L1候选任务；
- 20:40以后经用户确认允许一个L2任务；
- 00:30以后不领取新的L2任务；
- 次日交易前优先完成未结束的Correction和运维检查。

### 10.6 事件推送

首版使用SSE：

```text
GET /api/v1/tasks/events?after_event_id=...
GET /api/v1/tasks/{task_id}/events
```

- SSE只推送任务和发布事件，不传送大型结果；
- 断线后使用`after_event_id`补读；
- 页面最终状态以Task Query为准；
- SSE不可用时页面退回低频轮询；
- 不为此引入Kafka、NATS或WebSocket集群。

## 11. 权限架构

### 11.1 角色

#### owner

- 读取所有个人平台数据；
- 提交、取消和重试允许的任务；
- 编辑StrategySpec、研究Profile、自选和模拟组合；
- 发布或归档策略版本；
- 配置Provider、LLM、通知、调度和备份；
- 管理viewer、Session和Personal Access Token；
- 查看完整审计与资源使用；
- 执行受控导出、修订和维护操作。

#### viewer

- 读取已发布的市场、板块、个股、研究、回测和复盘；
- 查看数据状态、证据、任务结果和历史版本；
- 不提交研究、回测、采集或修订任务；
- 不修改Strategy、组合、配置和通知；
- 不查看密钥、Token、内部Prompt、原始日志或敏感错误详情；
- 不下载包含敏感配置的导出包。

viewer默认关闭，需要owner显式启用。

公网域名部署进一步受[Visory Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)约束：公网v1关闭viewer和外部PAT，只保留一个owner浏览器密码，并在登录时强制执行Cloudflare Turnstile服务端验证。

### 11.2 权限动作

内部采用动作权限而不是在业务代码中到处判断角色：

```text
platform.read
evidence.read
task.run
task.cancel
research.run
strategy.manage
backtest.run
portfolio.manage
artifact.export
operations.read
settings.manage
access.manage
```

角色只是动作集合。v1不提供自定义角色编辑器。

### 11.3 权限矩阵

| 操作 | owner | viewer |
| --- | --- | --- |
| 查看已发布市场/板块/个股 | 允许 | 允许 |
| 查看研究、回测和复盘历史 | 允许 | 允许 |
| 查看公开证据与数据质量 | 允许 | 允许 |
| 提交L1/L2研究 | 允许 | 禁止 |
| 提交Preview/Research/Formal回测 | 允许 | 禁止 |
| 编辑或发布StrategySpec | 允许 | 禁止 |
| 修改自选和模拟组合 | 允许 | 禁止 |
| 取消本人提交的任务 | 允许 | 禁止 |
| 触发数据Correction | 允许，需原因 | 禁止 |
| 修改Provider/LLM/通知 | 允许，必要时重认证 | 禁止 |
| 查看审计和完整运行日志 | 允许 | 禁止 |
| 管理viewer和Token | 允许，需重认证 | 禁止 |

### 11.4 会话与Token

- Web优先使用`HttpOnly`、`Secure`、`SameSite` Cookie；
- 状态修改请求必须有CSRF防护；
- Session ID轮换，服务端可撤销并记录最后活动；
- 密码和Token只保存强Hash，不保存明文；
- CLI/Bot需要长期访问时使用可撤销Personal Access Token；
- Token必须有到期时间、作用域和最近使用记录；
- PAT不会拥有高于创建者的权限，viewer不能创建写Token；
- 修改密码、禁用认证、管理用户、导出密钥和删除Token要求近期重认证；
- 公网部署不允许关闭认证；
- 反向代理必须正确传递可信来源和HTTPS状态，不能信任任意`X-Forwarded-*`。

### 11.5 当前管理员迁移

1. 现有有效管理员密码在升级时映射为唯一`owner`；
2. 现有Session可以在短兼容期内兑换新Session；
3. 未开启认证的实例只允许回环地址完成首次owner初始化；
4. 公网或局域网监听时未初始化owner则进入Setup Lock，不开放业务写接口；
5. 原`.admin_password_hash`在验证迁移完成前保留，之后按备份与回滚策略归档；
6. 迁移过程不把密码Hash写入普通日志或数据库导出。

## 12. 审计

以下事件必须审计：

- 登录成功、失败、退出、Session撤销和Token使用；
- 用户和权限变更；
- Provider、LLM、通知和调度配置变更；
- Task提交、取消、Retry、Priority Override和人工阻断解除；
- Snapshot认证、Correction、降级和回滚；
- Strategy版本创建、发布、归档和Promotion审批；
- 正式回测、研究和复盘发布；
- Artifact导出和敏感日志查看；
- 备份、恢复和保留策略执行。

审计记录至少包含：

```text
audit_id
actor_id
actor_role
session_or_token_id
action
resource_type
resource_id
request_id
occurred_at
client_ip_hash
before_hash
after_hash
reason
result
```

审计日志追加写，不允许从普通页面修改。敏感值只记录字段名和Hash差异。

## 13. 数据和控制面存储

### 13.1 PostgreSQL

保存：

- 用户、权限、Session元数据和PAT Hash；
- Task、Attempt、Event、Artifact Metadata和Worker Lease；
- StrategySpec、版本、运行引用和Promotion；
- Snapshot、Manifest、Definition和发布状态；
- Research、Review、Backtest、Portfolio等结果元数据；
- 审计、配置版本和通知投递记录。

不保存：

- 全量行情和全量Feature宽表；
- 大型报告附件、图像和回测明细文件；
- Provider原始大响应；
- LLM完整敏感调试上下文；
- 明文密码、PAT、Provider Key和LLM Key。

### 13.2 Parquet与DuckDB

- Raw、Normalized、Feature和Fact数据按已确定目录与Manifest管理；
- DuckDB用于服务器侧分析查询和Projection构建；
- API不得接受用户传入任意SQL；
- 查询模板、可用列和资源预算受控；
- 正式Result只引用不可变Snapshot，不引用“最新”路径；
- 文件写入采用临时文件、Hash校验和原子发布。

### 13.3 Artifact存储

Artifact包括：

- HTML/Markdown/PDF报告；
- 回测交易明细和指标表；
- Research Debate和Self-Review结构化结果；
- Task日志、Checkpoint和受控导出；
- 数据质量报告和差异报告。

每个Artifact保存Hash、大小、类型、生产Attempt和保留等级。页面只通过Artifact ID访问。

## 14. 一致性与发布

### 14.1 读一致性

一次页面Projection必须明确使用：

```text
data_snapshot_id
feature_snapshot_id
observation_snapshot_id
result_version_id
projection_schema_version
```

页面翻页或查看详情不能静默切换到新Correction。用户选择“查看最新修订”后才进入新版本。

### 14.2 写一致性

- 命令先提交控制记录，再异步生成Artifact；
- Artifact生成成功且Hash校验通过后才原子发布Result；
- PostgreSQL事务不跨越外部Provider、LLM或Hikyuu执行；
- 发布失败保留Attempt和临时Artifact诊断，但不更新Current指针；
- 通知在Result发布后触发，通知失败不回滚已发布Result；
- Correction创建新版本和新Projection Cache Key。

### 14.3 缓存

- 静态资源使用内容Hash长缓存；
- Certified页面Projection可使用短期服务端缓存；
- 用户、权限、任务和Correction状态不使用不可撤销长缓存；
- 缓存键必须包含Snapshot和Schema Version；
- 不引入Redis，首版可用进程内有界缓存和文件/数据库可重建缓存；
- 缓存丢失只影响性能，不影响权威结果。

## 15. 失败语义

### 15.1 API

- 认证失败返回401；
- 已认证但无权限返回403；
- 资源不存在返回404，不泄露viewer无权资源的存在；
- 版本冲突返回409或412；
- 数据尚未认证返回确定性业务错误，不返回空成功；
- 长任务过载返回Task排队或429，不在API进程勉强执行；
- 内部错误返回`request_id`，敏感堆栈只进受控日志。

### 15.2 页面

- 一个可选卡片失败不应让整页白屏；
- 核心Snapshot缺失时整页进入明确阻断态；
- 历史版本仍可浏览，不跟随当前Provider故障失效；
- SSE断开时退回轮询并显示连接状态；
- 权限不足隐藏命令入口，同时服务端仍必须拒绝绕过请求；
- AI模块失败时保留客观事实和失败原因。

### 15.3 Worker

- 外部超时、资源不足、数据门禁、用户取消和程序异常使用不同Error Code；
- OOM或进程异常退出不得把Task标记为成功；
- 不确定是否完成的副作用必须先对账；
- 重试只对契约声明为Retryable的错误生效；
- 达到最大Attempt后进入FAILED并通知owner；
- P0失败可以阻断依赖Task，不能让依赖任务自行绕过。

## 16. 安全边界

- 所有上传文件限制类型、大小、文件名和解析器；
- 不允许路径穿越、任意URL抓取和内网SSRF；
- LLM Tool Surface只暴露受控查询和命令，不暴露通用HTTP、SQL、Shell和文件工具；
- Provider、LLM和通知密钥使用独立Secret文件或环境注入，页面只显示掩码和连通状态；
- 日志统一脱敏Authorization、Cookie、Password、Secret、Webhook和Token；
- 公开Evidence遵循许可和引用规则，不把版权受限全文复制进Artifact；
- Artifact下载检查权限和资源归属；
- Docker Socket不得挂载进应用容器；
- 应用进程不以root运行；
- owner权限不等同于宿主机root权限；
- 数据目录、配置目录和备份目录的Unix权限在部署文档中独立固化。

## 17. 可观测性

### 17.1 核心指标

- API请求量、P50/P95延迟、5xx、401和403；
- Task按类型、状态和优先级的队列长度；
- Worker心跳、租约过期、Attempt、Retry和取消耗时；
- CPU、内存、磁盘水位、IO等待和Artifact增长；
- Provider成功率、延迟、限流和降级次数；
- Data/Feature Snapshot发布时间和SLA偏差；
- Hikyuu运行时间、峰值内存和Result发布失败；
- LLM调用次数、token、费用、超时和无证据拒绝；
- 页面Projection构建耗时和缓存命中；
- 通知成功、失败和重试。

### 17.2 关联标识

一次操作至少关联：

```text
request_id
task_id
attempt_id
trace_id
snapshot_id
result_id
actor_id
```

日志、Task Event、审计和页面诊断使用同一组标识，方便从页面追溯至Raw Hash。

### 17.3 Operations页面

Operations首页展示：

- 当前交易日数据流水线；
- 最近Data/Feature/Observation Snapshot状态；
- P0—P3队列、运行任务和阻断原因；
- Worker、Scheduler、数据库和磁盘健康；
- Provider降级和Correction；
- 最近失败、重试和需要人工处理的任务；
- 备份最后成功时间与恢复演练时间；
- 安全登录和配置变更摘要。

## 18. 资源基线

当前服务器遵循轻量运行：

| 资源 | v1基线 |
| --- | --- |
| FastAPI | 1个应用实例，避免多实例重复Scheduler |
| Scheduler | 1个Singleton Lease |
| HEAVY Worker | 1个执行槽 |
| LIGHT Worker | 最多2线程，且不与Hikyuu争抢关键资源 |
| Hikyuu | 单Run、受控子进程 |
| L2 Research | 单Run，每日最多1个 |
| L1 Research | 自动候选每日最多5只 |
| DuckDB | 查询线程和内存显式受限 |
| Historical Backfill | 分块、Checkpoint、只在P3窗口运行 |

资源紧张时的裁剪顺序：

1. 暂停历史回填；
2. 停止新L2研究；
3. 延后Research Backtest；
4. 降低非核心Projection刷新频率；
5. 保留P0数据、P1核心Feature、Formal Strategy和主复盘；
6. 核心数据无法认证时阻断正式结果，而不是进一步降低质量。

## 19. 迁移计划

### PF1：平台壳和契约

- 新增领域导航和路由骨架；
- 建立SnapshotStatusBar、EvidenceDrawer和TaskProgressPanel；
- 固化API响应、错误、分页、身份和版本规范；
- 现有页面保持可用。

### PF2：持久任务控制面

- 新增Task、Attempt、Event、Artifact和Worker Lease表；
- 先迁移一个低风险维护任务验证框架；待M6/M7契约完成后再迁移Formal Backtest与L2 Research；
- 增加旧Task Queue Adapter，让旧端点可查询新Task；
- 完成重启、租约、取消、Retry和原子发布测试。

### PF3：数据与观察页面

- 上线Operations、Market和Sector页面；
- 接入已发布Data/Feature/Observation Snapshot；
- 迁移Vibe的客观布局和图表，不复制其数据后端；
- 所有页面启用统一数据状态和Evidence入口。

### PF4：个股、研究和复盘闭环

- 上线Stock L0、Research Center和Review页面；
- 接入StockResearchFactPack和Review FactPack；
- 迁移现有Chat/Analysis历史并标记Legacy血缘；
- 启用L1/L2预算、用户确认和Self-Review状态。

### PF5：策略和回测闭环

- 上线StrategySpec编辑、版本和Preview；
- 上线Backtest Run/Attempt/Result详情与比较；
- 迁移screening、decision-signals和现有backtest路由；
- 验证Research Promotion只能创建草稿。

### PF6：权限和运维收敛

- 现有admin迁移为owner；
- MVP二期完成CSRF、重认证和安全审计；viewer和PAT保持禁用，延后到MVP后独立Work Package；
- 收敛Settings、Alerts和Usage页面；
- 旧端点完成弃用公告后再分版本移除。

## 20. API兼容策略

- 新增接口优先，不在同一版本改变旧响应的既有字段语义；
- 旧端点内部逐步调用新Service，避免双写两套结果；
- 响应可增加`deprecation`和`replacement`元数据；
- Web先迁移，Bot、CLI和Desktop后迁移；
- 旧任务ID可通过Alias表解析到新Task ID；
- 旧历史缺少Snapshot时明确返回`lineage_status=LEGACY_INCOMPLETE`；
- API v2只有在无法兼容的身份、权限或响应结构变化时才创建；
- 不为整理路由而一次性破坏所有现有客户端。

## 21. 验收标准

1. React/Vite只存在一套正式主平台导航和构建产物；
2. Vibe和tick-stock-panel没有作为第二套生产后端或页面运行；
3. FastAPI不直接执行Hikyuu正式回测和L2深度研究；
4. 正式长任务重启后仍可查询并进入恢复、重试或确定性失败；
5. 同一Task Key的重复请求不会产生重复正式运行；
6. Retry创建新Attempt且旧日志、资源和错误仍可查询；
7. 一个重任务执行槽能保证P0/P1在关键窗口优先；
8. 页面刷新不会重复提交研究、回测或数据采集任务；
9. 所有核心页面展示Snapshot日期、状态、版本和数据限制；
10. 页面不自行重算情绪、板块排名、策略评分或回测收益；
11. 个股专属路由使用同一`canonical_id`，研究、策略、回测和通用事实跨域关联使用与其一致的`entity_key`；
12. ResearchResult和StrategySignal在API及页面中不混用；
13. viewer不能通过隐藏入口、直接API或旧端点提交写任务；
14. owner敏感操作要求权限、审计和必要的重新认证；
15. Cookie、Token、Provider Key和LLM Key不会进入普通日志和页面响应；
16. SSE断线后可以补读事件，最终任务状态不依赖SSE；
17. Correction不会让正在查看的历史页面静默切换Snapshot；
18. API错误包含稳定Code和Request ID，不泄露敏感堆栈；
19. Operations页面可以看到数据流水线、队列、Worker、磁盘和失败原因；
20. 现有Web、Bot、CLI和历史记录可在迁移期继续使用；
21. 任意正式页面结果可以沿Result、Task、Attempt、Snapshot、ProviderRun追溯到Raw Hash；
22. 不依赖Redis、Kafka、NATS、Kubernetes或独立API Gateway即可运行v1。

## 22. MVP平台实现基线

1. 页面按P-TASKS/P-DATA基础壳→Market/Sector/Dashboard→Review→Strategy/Backtest→Research分批迁移，旧路由由Adapter保持；
2. 公网MVP只启用唯一owner，viewer和只读分享Token均不启用；
3. SSE热事件保留7天，Task State Event在线保留90天后归档到Audit Artifact；正式资源事件随资源保留；
4. Task表达到100万行或查询P95违反预算时按月分区/归档，在此之前保持单表并建立合适索引；
5. 首批告警：16:00链路错过阶段SLA、Worker心跳超过90秒、P0/P1阻塞、磁盘80%警告/90%严重、备份超过26小时、Artifact Hash失败；
6. Legacy API在新消费者切换后至少保留两个发布版本且不少于30天，并按调用指标决定移除；
7. Page Projection默认TTL 60秒、单API进程上限128MiB；Snapshot发布事件主动失效，不能跨Snapshot返回旧投影；
8. `operator`和viewer属于MVP后角色，不在首版数据库/页面创建半成品权限；
9. MVP顺序、数据回填和阶段Exit Gate以[实施路线与验收方案 v1](implementation-roadmap-and-acceptance-v1.md)为准。

## 23. 参考资料

- [daily_stock_analysis当前FastAPI路由](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/api/v1/router.py)
- [daily_stock_analysis当前React Web](https://github.com/ZhuLinsen/daily_stock_analysis/tree/main/apps/dsa-web)
- [daily_stock_analysis当前任务队列](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/src/services/task_queue.py)
- [daily_stock_analysis当前Web认证](https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/src/auth.py)
- [Visory架构索引](README.md)
- [A 股数据平台与 Canonical Data Contract v1](data-platform-and-canonical-contract.md)
- [盘后数据采集与 Snapshot 发布 SLA v1](data-ingestion-and-snapshot-sla.md)
- [A 股 Feature Store 与指标注册中心架构 v1](feature-store-architecture.md)
- [A 股市场情绪与资金行为架构 v1](market-sentiment-and-capital-flow-architecture.md)
- [A 股板块异动、热门观察与策略评分边界 v1](sector-observation-and-strategy-scoring-architecture.md)
- [全球市场观察与 A 股策略隔离架构 v1](global-market-observation-boundary.md)
- [A 股分层个股研究与 StockResearchFactPack 架构 v1](stock-research-architecture.md)
- [DSA A 股收盘复盘 FactPack 架构 v1](dsa-close-review-fact-pack.md)
- [StrategySpec v1 策略契约](strategy-spec-v1.md)
- [Fleur-Lite 回测运行与结果一致性架构](fleur-lite-backtest-runtime.md)
- [A 股平台 Docker、Cloudflare、NPM 与访问安全架构 v1](docker-cloudflare-npm-deployment-architecture.md)
