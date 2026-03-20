import hashlib
import json
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from services.java_client import java_client
from services.redis_client import get_redis

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

# ── 开发模式 mock 用户（DEV_SKIP_AUTH=true 时使用）─────────────
# 字段规范：
#   当前会话人 → operatorId / operatorName
#   （客户字段 userId/userName、员工字段 empId/empName 由 Tool 参数传递，不在 user 对象里）
_DEV_USER = {
    "operatorId": "dev_operator_001",
    "operatorName": "开发测试用户",
    "roles": ["admin"],
    "deptId": "dept_001",
    "permissions": [
        {"resource": "ai_assistant", "action": "access"},
        {"resource": "ai_tool:search_customer", "action": "execute"},
        {"resource": "ai_tool:get_customer_basic", "action": "execute"},
        {"resource": "ai_tool:get_serve_interact", "action": "execute"},
        {"resource": "ai_tool:get_serve_browse", "action": "execute"},
        {"resource": "ai_tool:get_position", "action": "execute"},
        {"resource": "ai_tool:get_sue", "action": "execute"},
        {"resource": "ai_tool:get_warning", "action": "execute"},
        {"resource": "ai_tool:get_customer_flow", "action": "execute"},
    ],
}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        if request.url.path.startswith("/api/internal/"):
            return await call_next(request)

        # ── DEV_SKIP_AUTH 开关：绕过所有权限检查 ──────────────
        if settings.dev_skip_auth:
            logger.debug("DEV_SKIP_AUTH=true，跳过权限验证，使用 mock 用户")
            request.state.user = _DEV_USER
            return await call_next(request)
        # ───────────────────────────────────────────────────────

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "缺少 Authorization header"}, status_code=401)

        token = auth_header[7:]
        try:
            user = await get_user_permissions(token)
        except Exception as e:
            logger.warning("Token 验证失败: %s", e)
            return JSONResponse({"error": "Token 无效或已过期"}, status_code=401)

        has_access = any(
            p.get("resource") == "ai_assistant" and p.get("action") == "access"
            for p in user.get("permissions", [])
        )
        if not has_access:
            return JSONResponse({"error": "无权限使用智能助手"}, status_code=403)

        request.state.user = user
        return await call_next(request)


async def get_user_permissions(token: str) -> dict:
    """拉取用户权限，Redis 缓存 perm_cache_ttl 秒"""
    cache_key = f"perm:{hashlib.md5(token.encode()).hexdigest()}"
    redis = await get_redis()

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    user = await java_client.verify_token(token)
    await redis.setex(cache_key, settings.perm_cache_ttl, json.dumps(user))
    return user


async def invalidate_user_cache(operator_id: str) -> int:
    """Java 权限变更时主动清除该用户所有缓存（按 operatorId 匹配）"""
    redis = await get_redis()
    keys = await redis.keys("perm:*")
    deleted = 0
    for key in keys:
        data = await redis.get(key)
        if data:
            try:
                user = json.loads(data)
                if user.get("operatorId") == operator_id:
                    await redis.delete(key)
                    deleted += 1
            except Exception:
                pass
    return deleted


def get_allowed_tools(user: dict, all_tools: list[dict]) -> list[dict]:
    """从用户权限中过滤出允许调用的 Tool 列表"""
    allowed_names = {
        p["resource"].replace("ai_tool:", "")
        for p in user.get("permissions", [])
        if p.get("resource", "").startswith("ai_tool:")
           and p.get("action") == "execute"
    }
    return [t for t in all_tools if t["name"] in allowed_names]
