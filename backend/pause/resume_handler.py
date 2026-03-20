import json
import logging

from langgraph.types import Command

from services.redis_client import get_redis

logger = logging.getLogger(__name__)

_PAUSE_KEY_PREFIX = "pause:"


async def save_partial_result(session_id: str, content: str) -> None:
    """SSE 被 AbortController 中断时，保存已输出的部分内容"""
    redis = await get_redis()
    await redis.setex(f"{_PAUSE_KEY_PREFIX}{session_id}", 3600, content)
    logger.info("已保存中断内容: session=%s, len=%d", session_id, len(content))


async def get_partial_result(session_id: str) -> str | None:
    redis = await get_redis()
    return await redis.get(f"{_PAUSE_KEY_PREFIX}{session_id}")


async def clear_partial_result(session_id: str) -> None:
    redis = await get_redis()
    await redis.delete(f"{_PAUSE_KEY_PREFIX}{session_id}")


def build_resume_command(action: str, new_params: dict | None = None) -> Command:
    """
    构建 LangGraph resume 命令
    action: continue | modify | cancel
    """
    if action == "cancel":
        return Command(resume="cancel")
    elif action == "modify" and new_params:
        return Command(resume=json.dumps(new_params))
    else:
        return Command(resume="continue")
