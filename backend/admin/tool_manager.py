import json
import logging
from uuid import UUID

from config import settings
from db.database import get_pool
from services.redis_client import get_redis

logger = logging.getLogger(__name__)

_ALL_ENABLED_KEY = "tools:all_enabled"


def _deserialize_tool(t: dict) -> dict:
    """从 Redis 读回后，确保 JSONB 字段是 dict 而非字符串"""
    for field in ("parameters", "param_mapping"):
        v = t.get(field)
        if isinstance(v, str):
            try:
                t[field] = json.loads(v)
            except Exception:
                t[field] = {}
    return t


class ToolManager:
    """从数据库动态加载 Tool 定义，Redis 缓存 tool_cache_ttl 秒"""

    async def get_all_enabled(self) -> list[dict]:
        redis = await get_redis()
        cached = await redis.get(_ALL_ENABLED_KEY)
        if cached:
            return [_deserialize_tool(t) for t in json.loads(cached)]

        pool = await get_pool()
        rows = await pool.fetch(
            "SELECT * FROM tool_definitions WHERE enabled = true ORDER BY name"
        )
        tools = [dict(r) for r in rows]
        # asyncpg 返回的 JSONB 已是 dict，TEXT[] 已是 list
        await redis.setex(_ALL_ENABLED_KEY, settings.tool_cache_ttl, json.dumps(tools, default=str))
        return tools

    async def get_one(self, name: str) -> dict | None:
        redis = await get_redis()
        cache_key = f"tool_def:{name}"
        cached = await redis.get(cache_key)
        if cached:
            return _deserialize_tool(json.loads(cached))

        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT * FROM tool_definitions WHERE name=$1 AND enabled=true", name
        )
        if not row:
            return None
        tool = dict(row)
        await redis.setex(cache_key, settings.tool_cache_ttl, json.dumps(tool, default=str))
        return tool

    async def create(self, data: dict) -> dict:
        pool = await get_pool()
        row = await pool.fetchrow(
            """INSERT INTO tool_definitions
               (name, display_name, description, java_url, http_method,
                parameters, param_mapping, allowed_roles)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
            data["name"],
            data["display_name"],
            data["description"],
            data["java_url"],
            data.get("http_method", "POST"),
            json.dumps(data.get("parameters", {})),
            json.dumps(data.get("param_mapping", {})),
            data.get("allowed_roles", []),
        )
        await self._invalidate_cache(data["name"])
        return dict(row)

    async def update(self, name: str, data: dict) -> dict | None:
        pool = await get_pool()
        row = await pool.fetchrow(
            """UPDATE tool_definitions SET
               display_name=$2, description=$3, java_url=$4,
               http_method=$5, parameters=$6, param_mapping=$7,
               allowed_roles=$8, updated_at=now()
               WHERE name=$1 RETURNING *""",
            name,
            data["display_name"],
            data["description"],
            data["java_url"],
            data.get("http_method", "POST"),
            json.dumps(data.get("parameters", {})),
            json.dumps(data.get("param_mapping", {})),
            data.get("allowed_roles", []),
        )
        if row:
            await self._invalidate_cache(name)
        return dict(row) if row else None

    async def toggle(self, name: str, enabled: bool) -> bool:
        pool = await get_pool()
        result = await pool.execute(
            "UPDATE tool_definitions SET enabled=$2, updated_at=now() WHERE name=$1",
            name, enabled,
        )
        await self._invalidate_cache(name)
        return result == "UPDATE 1"

    async def delete(self, name: str) -> bool:
        pool = await get_pool()
        result = await pool.execute(
            "DELETE FROM tool_definitions WHERE name=$1", name
        )
        await self._invalidate_cache(name)
        return result == "DELETE 1"

    async def _invalidate_cache(self, name: str) -> None:
        redis = await get_redis()
        await redis.delete(f"tool_def:{name}", _ALL_ENABLED_KEY)
        logger.info("Tool 缓存已清除: %s", name)

    async def build_tool_schemas(self, tools: list[dict]) -> list[dict]:
        """将数据库 Tool 定义转换为 LLM Function Calling 格式"""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("parameters") or {},
            }
            for t in tools
        ]


tool_manager = ToolManager()
