# PostgreSQL 与 Alembic 基础（WP-0002）

最后更新：2026-08-29

## 1. 范围与固定技术栈

WP-0002 只建立 Visory 目标控制面的 PostgreSQL 基础，不迁移或改写任何 Legacy SQLite 业务表。

固定且唯一的数据库栈：

- SQLAlchemy `2.0.52` 同步 `Engine` 与 `QueuePool`；
- psycopg `3.3.4` 同步驱动，SQLAlchemy URL driver 为 `postgresql+psycopg`；
- Alembic `1.19.1`；
- PostgreSQL 16 作为本地或 CI 的一次性验收实例。

本 WP 不提供异步 Engine、`asyncpg`、第二套连接池或 ORM 业务模型。后续 Repository 只能使用调用方提供的事务 `Session`，不得隐式 `commit()`。

## 2. 配置与 Secret

平台数据库配置由 `PostgresSettings.from_environment()` 读取：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VISORY_POSTGRES_HOST` | `127.0.0.1` | PostgreSQL host |
| `VISORY_POSTGRES_PORT` | `5432` | 1—65535 |
| `VISORY_POSTGRES_DATABASE` | `visory` | 数据库名 |
| `VISORY_POSTGRES_USER` | `visory` | 用户名 |
| `VISORY_POSTGRES_PASSWORD_FILE` | 无 | 必填，必须是绝对文件路径 |
| `VISORY_POSTGRES_CONNECT_TIMEOUT_SECONDS` | `5` | 1—300 |
| `VISORY_POSTGRES_POOL_SIZE` | `5` | 1—100 |
| `VISORY_POSTGRES_MAX_OVERFLOW` | `5` | 0—100 |
| `VISORY_POSTGRES_POOL_TIMEOUT_SECONDS` | `30` | 1—300 |
| `VISORY_POSTGRES_POOL_RECYCLE_SECONDS` | `1800` | 0—86400 |
| `VISORY_POSTGRES_APPLICATION_NAME` | `visory` | PostgreSQL application name |

`VISORY_POSTGRES_PASSWORD`、`VISORY_POSTGRES_DSN` 和 `VISORY_POSTGRES_URL` 被显式拒绝。配置对象只保存 Secret 文件引用，不保存密码、DSN 或可回显的连接串。

Secret 文件要求：

- 普通文件且不得是 Symlink；
- UTF-8、单行、非空、最多 4096 bytes；
- 允许一个终止换行，不允许首尾空白、NUL 或控制字符；
- POSIX 环境不得向 group/other 开放权限，推荐 `chmod 600`；
- 缺失、不可读、权限过宽或格式错误均返回稳定错误码，错误文本不包含值或绝对路径。

示例只创建本地测试引用，不要把 Secret 文件加入 Git：

```bash
umask 077
printf '%s\n' '***' > /tmp/visory-postgres-password
export VISORY_POSTGRES_PASSWORD_FILE=/tmp/visory-postgres-password
```

## 3. 连接、健康检查与事务

入口位于 `src/repositories/platform/`：

- `create_postgres_engine(settings)`：创建单一同步 Engine，启用 `pool_pre_ping`、LIFO QueuePool、固定 timeout/recycle；
- `PostgresDatabase.check_health()`：执行 `SELECT 1`；
- `PostgresDatabase.transaction()`：上下文正常结束时提交，异常时由 SQLAlchemy 回滚；
- `PostgresDatabase.close()`：幂等关闭连接池；关闭后继续使用返回 `DATABASE_POOL_CLOSED`。

连接或已失效连接错误统一映射为：

```text
error_code=DATABASE_UNAVAILABLE
retryable=true
```

其他数据库操作错误为 `DATABASE_OPERATION_FAILED`，Migration 错误为 `DATABASE_MIGRATION_FAILED`。公共错误只包含稳定错误码、公共消息、retryable 与有限 details；底层异常仅保留为 cause，不进入 `str()` 或 `repr()`。

## 4. Migration 基线

Alembic 配置：

- 配置文件：`alembic.ini`；
- Migration 根：`migrations/`；
- 当前唯一 revision：`0001_wp0002_baseline`；
- parent：`<base>`；
- baseline revision 不创建任何业务表，只建立 `alembic_version` 状态。

必须在 PostgreSQL 在线连接上运行；离线 SQL 生成不属于本 WP 支持范围。

```bash
python -m alembic heads
python -m alembic history --verbose
python -m alembic upgrade head
python -m alembic current
python -m alembic downgrade base
python -m alembic upgrade head
```

应用代码和测试也可调用：

```python
from src.repositories.platform import (
    downgrade_database,
    get_migration_status,
    upgrade_database,
)

upgrade_database(engine)
status = get_migration_status(engine)
downgrade_database(engine, "base")
```

## 5. 测试数据库与清理

`tests/integration/platform/conftest.py` 使用管理员数据库创建随机的 `visory_test_<20 hex>` 数据库。Fixture 在退出时：

1. 关闭应用连接池；
2. 终止该测试数据库的遗留连接；
3. 删除测试数据库；
4. dispose 管理员 Engine。

测试环境变量使用 `VISORY_TEST_POSTGRES_*` 前缀，密码仍只通过 `VISORY_TEST_POSTGRES_PASSWORD_FILE` 引用。GitHub Python Job 使用 PostgreSQL 16 service 和 runner 临时 Secret 文件；不接触生产 Secret 或服务器目录。

## 6. 验收与回滚

WP-0002 的 PostgreSQL 集成测试覆盖：空库 upgrade、重复 upgrade、downgrade base 后重新 upgrade、Migration 状态、`timestamptz` Instant 往返、事务提交/回滚、不可连接错误、连接池关闭和测试数据库清理。

最小回滚：

- Schema：在隔离数据库运行 `python -m alembic downgrade base`；
- 代码：revert WP-0002 commits；
- 配置：移除 `VISORY_POSTGRES_*`，Legacy `DATABASE_PATH` 与现有 API 行为不受影响；
- 测试环境：删除一次性 Secret 文件和测试数据库。不得用本 Migration 操作 Legacy SQLite 文件。
