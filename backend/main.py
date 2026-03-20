import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from pydantic import BaseModel

from admin.tool_manager import tool_manager
from auth.middleware import AuthMiddleware, invalidate_user_cache
from config import settings
from db.database import close_pool, init_db, seed_tools, seed_tools
from db.session_repo import message_repo, session_repo
from graph.builder import build_graph
from pause.resume_handler import (
    build_resume_command,
    clear_partial_result,
    save_partial_result,
)
from services.redis_client import close_redis, get_redis

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_tools()
    logger.info("数据库初始化 + Tool 种子数据完成")
    # 使用内存 checkpointer（生产环境替换为 Redis checkpointer）
    app.state.graph = build_graph()
    logger.info("LangGraph 图编译完成")
    yield
    await close_pool()
    await close_redis()
    logger.info("服务已关闭")


app = FastAPI(title="企业智能助手", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)


# ── Pydantic 模型 ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ResumeRequest(BaseModel):
    session_id: str
    action: str                      # continue | modify | cancel | select_customer
    new_params: dict | None = None
    # 多客户选择时传入
    selected_user_id:   str | None = None
    selected_user_name: str | None = None


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None


class ToolCreateRequest(BaseModel):
    name: str
    display_name: str
    description: str
    java_url: str
    http_method: str = "POST"
    parameters: dict = {}
    param_mapping: dict = {}
    allowed_roles: list[str] = []


class ToolToggleRequest(BaseModel):
    enabled: bool


# ── 健康检查 ───────────────────────────────────────────────────

def _serialize(row: dict) -> dict:
    """把 asyncpg 返回的 UUID/datetime 转成 JSON 友好的字符串"""
    import uuid as _uuid
    import datetime as _dt
    return {
        k: str(v) if isinstance(v, (_uuid.UUID, _dt.datetime, _dt.date)) else v
        for k, v in row.items()
    }


@app.get("/health")
async def health():
    redis = await get_redis()
    await redis.ping()
    return {"status": "ok"}


# ── 会话管理 ───────────────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions(request: Request):
    user = request.state.user
    sessions = await session_repo.list_by_operator(user["operatorId"])
    return {"data": [_serialize(s) for s in sessions]}


@app.post("/api/sessions")
async def create_session(request: Request):
    user = request.state.user
    session = await session_repo.create(user["operatorId"])
    return {"data": session}


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    session = await session_repo.get(uuid.UUID(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session["operator_id"] != request.state.user["operatorId"]:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    messages = await message_repo.list_by_session(uuid.UUID(session_id))
    return {"data": [_serialize(m) for m in messages]}


@app.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdateRequest, request: Request):
    session = await session_repo.get(uuid.UUID(session_id))
    if not session or session["operator_id"] != request.state.user["operatorId"]:
        raise HTTPException(status_code=403, detail="无权操作此会话")
    if body.title:
        await session_repo.update_title(uuid.UUID(session_id), body.title)
    if body.status == "archived":
        await session_repo.archive(uuid.UUID(session_id))
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    session = await session_repo.get(uuid.UUID(session_id))
    if not session or session["operator_id"] != request.state.user["operatorId"]:
        raise HTTPException(status_code=403, detail="无权操作此会话")
    await session_repo.delete(uuid.UUID(session_id))
    return {"ok": True}


# ── SSE 对话流 ────────────────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    user = request.state.user

    # 自动创建或复用会话
    if body.session_id:
        session = await session_repo.get(uuid.UUID(body.session_id))
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        session_id = body.session_id
    else:
        session = await session_repo.create(user["operatorId"], body.message[:40])
        session_id = str(session["id"])

    # 保存用户消息
    await message_repo.add(
        session_id=uuid.UUID(session_id),
        operator_id=user["operatorId"],
        role="user",
        content=body.message,
    )

    # 自动更新会话标题（首条消息）
    if not session.get("title") or session.get("title") == "新对话":
        await session_repo.update_title(uuid.UUID(session_id), body.message[:40])

    # 加载历史消息，让模型看到完整对话上下文（含客户确认的 SystemMessage）
    prev_messages = await message_repo.list_by_session(uuid.UUID(session_id))
    history: list = []
    for m in prev_messages:
        if m["role"] == "user":
            history.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant" and m["content"]:
            history.append(AIMessage(content=m["content"]))
        elif m["role"] == "system" and m["content"]:
            history.append(SystemMessage(content=m["content"]))
    # 当前这条用户消息已经存入 DB，history 里已包含，无需重复追加
    if not history or history[-1].content != body.message:
        history.append(HumanMessage(content=body.message))

    graph = request.app.state.graph
    config = {
        "configurable": {
            "thread_id": session_id,
            "user": user,
        }
    }
    initial_state = {
        "messages":            history,
        "query_results":       {},
        "status":              "running",
        "user":                user,
        "session_id":          session_id,
        "customer_candidates": [],
        "selected_user_id":    None,
        "selected_user_name":  None,
        "confirmed_customer":  None,
    }

    async def generate():
        accumulated = ""
        try:
            final_state = {}

            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event", "")

                # 逐 token 流式推送
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if not chunk:
                        continue
                    if getattr(chunk, "tool_call_chunks", None):
                        continue
                    token = getattr(chunk, "content", "") or ""
                    if not token:
                        continue
                    accumulated += token
                    payload = json.dumps({"type": "text", "content": token, "session_id": session_id})
                    yield f"data: {payload}\n\n"

                # 节点执行完毕，获取最终 state
                elif kind == "on_chain_end" and event.get("name") == "run_agent":
                    final_state = event.get("data", {}).get("output", {})

            # 检查是否需要用户选择客户
            if final_state.get("status") == "need_select_customer":
                customers = final_state.get("customer_candidates", [])
                payload = json.dumps({
                    "type":       "select_customer",
                    "customers":  customers,
                    "message":    "找到多个匹配客户，请选择：",
                    "session_id": session_id,
                })
                yield f"data: {payload}\n\n"
                return  # 等待前端 resume

            # 正常结束：保存 AI 回复
            if accumulated:
                # 存客户确认 SystemMessage（search_customer 唯一结果时由 nodes.py 生成）
                confirmed = final_state.get("confirmed_customer")
                if confirmed:
                    await message_repo.add(
                        session_id=uuid.UUID(session_id),
                        operator_id=user["operatorId"],
                        role="system",
                        content=confirmed,
                    )
            if accumulated:
                await message_repo.add(
                    session_id=uuid.UUID(session_id),
                    operator_id=user["operatorId"],
                    role="assistant",
                    content=accumulated,
                )
            await session_repo.touch(uuid.UUID(session_id))
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        except asyncio.CancelledError:
            if accumulated:
                await message_repo.add(
                    session_id=uuid.UUID(session_id),
                    operator_id=user["operatorId"],
                    role="assistant",
                    content=accumulated + "（已中断）",
                )
            logger.info("SSE 已被客户端中断: session=%s", session_id)

        except Exception as e:
            logger.error("SSE 流异常: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


# ── 暂停 / 恢复 ────────────────────────────────────────────────

@app.post("/api/chat/resume")
async def chat_resume(body: ResumeRequest, request: Request):
    user = request.state.user

    if body.action == "cancel":
        return {"ok": True, "message": "已放弃，请重新输入"}

    # select_customer：用选定的客户重新跑图，走 StreamingResponse
    if body.action == "select_customer":
        session_id = body.session_id
        graph = request.app.state.graph
        config = {"configurable": {"thread_id": session_id + "_resume", "user": user}}

        # 还原完整对话历史（含所有 user/assistant 消息）
        session_messages = await message_repo.list_by_session(uuid.UUID(session_id))
        history_messages = []
        for m in session_messages:
            if m["role"] == "user":
                history_messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant" and m["content"]:
                history_messages.append(AIMessage(content=m["content"]))
            elif m["role"] == "system" and m["content"]:
                history_messages.append(SystemMessage(content=m["content"]))
        # 取最后一条 user 消息作为当前 query（selected_user_id 会注入 state，节点会自动带上）
        if not history_messages:
            history_messages = [HumanMessage(content="")]

        # selected_user_id 注入 state，run_agent 会将其作为 SystemMessage 写入对话历史
        # 对话历史存入数据库后，下轮模型自己从 messages 里读取客户上下文
        resume_state = {
            "messages":            history_messages,
            "query_results":       {},
            "status":              "running",
            "user":                user,
            "session_id":          session_id,
            "customer_candidates": [],
            "selected_user_id":    body.selected_user_id,
            "selected_user_name":  body.selected_user_name,
            "confirmed_customer":  None,
        }

        async def generate_resume():
            accumulated = ""
            try:
                async for event in graph.astream_events(
                    resume_state, config=config, version="v2"
                ):
                    kind = event.get("event", "")
                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if not chunk or getattr(chunk, "tool_call_chunks", None):
                            continue
                        token = getattr(chunk, "content", "") or ""
                        if not token:
                            continue
                        accumulated += token
                        payload = json.dumps({"type": "text", "content": token, "session_id": session_id})
                        yield f"data: {payload}\n\n"

                if accumulated:
                    # 先存一条隐藏的系统消息，记录客户选择结果，供后续轮次模型读取
                    await message_repo.add(
                        session_id=uuid.UUID(session_id),
                        operator_id=user["operatorId"],
                        role="system",
                        content=f"[已确认客户] {body.selected_user_name}，userId={body.selected_user_id}",
                    )
                    await message_repo.add(
                        session_id=uuid.UUID(session_id),
                        operator_id=user["operatorId"],
                        role="assistant",
                        content=accumulated,
                    )
                await session_repo.touch(uuid.UUID(session_id))
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
            except Exception as e:
                logger.error("resume SSE 异常: %s", e, exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            generate_resume(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 其他 action（continue / modify）走原有逻辑
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.session_id, "user": user}}
    cmd = build_resume_command(body.action, body.new_params)
    results = []
    async for event in graph.astream(cmd, config=config, stream_mode="values"):
        msgs = event.get("messages", [])
        if msgs:
            results.append(msgs[-1].content if hasattr(msgs[-1], "content") else str(msgs[-1]))
    return {"ok": True, "messages": results}


@app.post("/api/chat/cancel")
async def chat_cancel(request: Request, body: dict):
    session_id = body.get("session_id", "")
    await clear_partial_result(session_id)
    return {"ok": True}


# ── Tool 管理（运营后台）────────────────────────────────────────

@app.get("/admin/tools")
async def list_tools():
    tools = await tool_manager.get_all_enabled()
    return {"data": tools}


@app.post("/admin/tools")
async def create_tool(body: ToolCreateRequest):
    tool = await tool_manager.create(body.model_dump())
    return {"data": tool, "message": "创建成功，立即生效"}


@app.put("/admin/tools/{name}")
async def update_tool(name: str, body: ToolCreateRequest):
    tool = await tool_manager.update(name, body.model_dump())
    if not tool:
        raise HTTPException(status_code=404, detail="Tool 不存在")
    return {"data": tool, "message": "更新成功，60秒内全部实例生效"}


@app.patch("/admin/tools/{name}/toggle")
async def toggle_tool(name: str, body: ToolToggleRequest):
    ok = await tool_manager.toggle(name, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Tool 不存在")
    status = "启用" if body.enabled else "禁用"
    return {"ok": True, "message": f"已{status}，立即生效"}


@app.delete("/admin/tools/{name}")
async def delete_tool(name: str):
    ok = await tool_manager.delete(name)
    if not ok:
        raise HTTPException(status_code=404, detail="Tool 不存在")
    return {"ok": True, "message": "已删除"}


# ── 内部接口：权限缓存失效 ────────────────────────────────────

@app.delete("/api/internal/cache/perm/{operator_id}")
async def invalidate_perm_cache(operator_id: str):
    """供 Java 权限系统调用，权限变更后主动清除缓存"""
    count = await invalidate_user_cache(operator_id)
    return {"ok": True, "cleared": count}
