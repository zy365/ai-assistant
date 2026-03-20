import asyncpg
from config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── DDL ──────────────────────────────────────────────────────
# 字段规范：
#   当前会话人 → operator_id / operator_name
#   DB 内部使用 snake_case，与 Java 侧字段通过 repo 层映射

INIT_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 会话表（operator_id = 当前登录操作人）
CREATE TABLE IF NOT EXISTS sessions (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id         VARCHAR(64) NOT NULL,
    title               VARCHAR(200),
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    selected_user_id    VARCHAR(64),
    selected_user_name  VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 兼容已有数据库，忽略列已存在的错误
DO $$ BEGIN
  ALTER TABLE sessions ADD COLUMN IF NOT EXISTS selected_user_id   VARCHAR(64);
  ALTER TABLE sessions ADD COLUMN IF NOT EXISTS selected_user_name VARCHAR(64);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_sessions_operator_updated
    ON sessions(operator_id, updated_at DESC);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    operator_id  VARCHAR(64) NOT NULL,
    role         VARCHAR(20) NOT NULL,
    content      TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_content_trgm
    ON messages USING GIN (content gin_trgm_ops);

-- Tool 调用日志表
CREATE TABLE IF NOT EXISTS tool_logs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    operator_id     VARCHAR(64) NOT NULL,   -- 当前会话人 ID
    operator_name   VARCHAR(64),            -- 当前会话人姓名
    tool_name       VARCHAR(100) NOT NULL,
    params          JSONB,
    result          JSONB,
    status          VARCHAR(20),
    duration_ms     INTEGER,
    roles_at_call   TEXT[],
    scope_injected  JSONB,
    permission_rule VARCHAR(200),
    called_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_logs_session
    ON tool_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_logs_operator
    ON tool_logs(operator_id, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_logs_params
    ON tool_logs USING GIN (params);

-- Tool 定义表（运营后台动态管理）
CREATE TABLE IF NOT EXISTS tool_definitions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(100) UNIQUE NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    description   TEXT        NOT NULL,
    java_url      VARCHAR(500) NOT NULL,
    http_method   VARCHAR(10) NOT NULL DEFAULT 'POST',
    parameters    JSONB       NOT NULL DEFAULT '{}',
    param_mapping JSONB       NOT NULL DEFAULT '{}',
    allowed_roles TEXT[]      NOT NULL DEFAULT '{}',
    enabled       BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def init_db() -> None:
    return
    # pool = await get_pool()
    # async with pool.acquire() as conn:
    #     await conn.execute(INIT_SQL)


# ── 种子数据：预置 Tool 定义 ──────────────────────────────────
# 字段规范（Tool 参数层）：
#   客户  → userId（客户ID）/ userName（客户姓名）
#   员工  → empId（员工ID）/ empName（员工姓名）
#   操作人 → operatorId（当前会话人ID，由系统注入，模型无需传）

SEED_TOOLS_SQL = """
INSERT INTO tool_definitions
  (name, display_name, description, java_url, http_method, parameters, param_mapping, allowed_roles)
VALUES
  (
    'search_customer',
    '搜索客户',
    '根据客户姓名搜索客户信息，返回匹配的客户列表（含 userId、userName）。用户提到客户名称时，必须先调此 Tool 获取 userId，再调其他查客户数据的 Tool。',
    '/api/customers/search',
    'GET',
    '{"type":"object","properties":{"userName":{"type":"string","description":"客户姓名或姓名关键字"}},"required":["userName"]}',
    '{}',
    ARRAY['sales_manager','risk_control','admin']
  ),
  (
    'get_bubble',
    '查询客户冒泡',
    '查询指定客户的冒泡记录（理财到期提醒、资产变动等触发的跟进信号）。需传入 userId（客户ID），可先调 search_customer 获取。',
    '/api/customers/bubble',
    'GET',
    '{"type":"object","properties":{"userId":{"type":"string","description":"客户ID，从 search_customer 结果中获取"}},"required":["userId"]}',
    '{}',
    ARRAY['sales_manager','admin']
  ),
  (
    'get_position',
    '查询客户持仓',
    '查询指定客户当前的投资持仓情况，包括持仓品种、金额、占比。需传入 userId（客户ID）。',
    '/api/customers/position',
    'GET',
    '{"type":"object","properties":{"userId":{"type":"string","description":"客户ID"}},"required":["userId"]}',
    '{}',
    ARRAY['sales_manager','risk_control','admin']
  ),
  (
    'get_interaction',
    '查询客户互动记录',
    '查询与指定客户的历史互动记录，包括电话、微信、面谈等。需传入 userId（客户ID）。',
    '/api/customers/interaction',
    'GET',
    '{"type":"object","properties":{"userId":{"type":"string","description":"客户ID"},"limit":{"type":"integer","description":"返回条数，默认20"}},"required":["userId"]}',
    '{}',
    ARRAY['sales_manager','admin']
  ),
  (
    'get_call_records',
    '查询员工通话记录',
    '查询指定员工在一段时间内的通话记录，包括每日通话次数、时长。需传入 empName（员工姓名）。用于展示员工通话趋势图表时调用。',
    '/api/employees/call-records',
    'GET',
    '{"type":"object","properties":{"empName":{"type":"string","description":"员工姓名"},"days":{"type":"integer","description":"查询最近几天，默认30"}},"required":["empName"]}',
    '{}',
    ARRAY['sales_manager','admin']
  ),
  (
    'get_sales_data',
    '查询销售业绩',
    '查询员工或团队的销售业绩数据，包括完成金额、目标达成率。可传入 empName（员工姓名）查个人，不传则查整个团队。',
    '/api/sales/performance',
    'GET',
    '{"type":"object","properties":{"empName":{"type":"string","description":"员工姓名，不传则查整个团队"},"month":{"type":"string","description":"月份，格式 yyyy-MM，如 2026-03"}},"required":[]}',
    '{}',
    ARRAY['sales_manager','admin']
  )
ON CONFLICT (name) DO NOTHING;
"""


async def seed_tools() -> None:
    """插入预置 Tool 定义（已存在的跳过）"""
    return
    # pool = await get_pool()
    # async with pool.acquire() as conn:
    #     await conn.execute(SEED_TOOLS_SQL)
