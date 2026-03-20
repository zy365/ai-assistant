from __future__ import annotations

import asyncio
import json
import logging
import time
import datetime
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from admin.tool_manager import tool_manager
from auth.middleware import get_allowed_tools
from config import settings
from db.audit_repo import audit_repo
from graph.state import AssistantState
from services.java_client import java_client

logger = logging.getLogger(__name__)

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")



base_prompt = """你的名字是小元，你是专业的企业业务数据查询助手，只负责准确查询并总结呈现给用户所需数据，不做额外解释。

规则:
1. 【严格按需调用】只调用用户明确问到的内容对应的 Tool，不要主动多查用户没有提及的数据
2. 优先调用 Tool 获取真实数据，不要凭空捏造，调用工具时，严禁使用占位符作为参数传递
3. 自然语言整合输出：
    - 禁止机械罗列字段名、字段含义或原始返回结构
    - 对 Tool 返回结果做提炼、归纳、通顺化，用流畅自然的中文口语化表达
    - 只呈现关键结论与数据，不冗余复述接口细节
4. 客户查询规范：仅知晓客户姓名时，必须先调用 search_customer(keyword) 获取 userId，再调用其他客户相关 Tool。
5. 直接给出结果：回复仅包含整理后的结果与分析，不重复用户问题。
6. 当前真实时间：{{current_time}}
7. 如果用户问到与时间范围相关的查询，需要根据当前真实时间计算出合理的 startDate 和 endDate 后作为工具调用参数，格式为 yyyy-MM-dd HH:mm:ss
    时间参数精准解析：
    第一步：以【当前真实时间】为唯一基准，解析用户提问中的所有时间描述（如 “最近 3 天”“本周”“昨天”“2026 年 2 月”）。
    第二步：将解析后的时间描述转化为 Tool 可接收的标准时间参数（优先使用 startDate/endDate，格式为 yyyy-MM-dd HH:mm:ss），规则如下：
    ✅ 最近 N 天 → startDate = 当前时间 - N 天（yyyy-MM-dd HH:mm:ss）、endDate = 当前时间的日期（yyyy-MM-dd HH:mm:ss）
    ✅ 昨天 → startDate = 昨天日期（yyyy-MM-dd HH:mm:ss）、endDate = 昨天日期（yyyy-MM-dd HH:mm:ss）
    ✅ 本周 → startDate = 本周一日期（yyyy-MM-dd HH:mm:ss）、endDate = 当前时间的日期（yyyy-MM-dd HH:mm:ss）
    ✅ 本月 → startDate = 本月 1 日（yyyy-MM-dd HH:mm:ss）、endDate = 当前时间的日期（yyyy-MM-dd HH:mm:ss）
    ✅ 具体时间段（如 2026 年 3 月 1 日 - 3 月 10 日）→ startDate=2026-03-01 00:00:00、endDate=2026-03-10 23:59:59
    ✅ 无明确时间 → 默认最近30天

示例：
- 用户问「持仓情况」→ 仅调用 get_position
- 用户问「预警和客诉」→ 同时调用 get_warning 和 get_sue
"""

SYSTEM_PROMPT = base_prompt.replace("{{current_time}}", current_time_str)

def _build_llm_with_tools(tool_schemas: list[dict]) -> ChatOpenAI:
    llm = ChatOpenAI(
        model=settings.qwen_model,
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        streaming=True,
        temperature=0.1,
    )
    if tool_schemas:
        functions = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                },
            }
            for t in tool_schemas
        ]
        return llm.bind_tools(functions)
    return llm


async def _execute_tool(tool_name: str, tool_args: dict, user: dict, session_id: str) -> str:
    tool_def = await tool_manager.get_one(tool_name)
    if not tool_def:
        return json.dumps({"error": f"Tool '{tool_name}' 不存在或已禁用"})

    t0 = time.monotonic()
    status = "success"

    mapping_raw = tool_def.get("param_mapping") or {}
    mapping: dict = json.loads(mapping_raw) if isinstance(mapping_raw, str) else mapping_raw
    params = {mapping.get(k, k): v for k, v in tool_args.items()}
    logger.info(f"_execute_tool params {params}")

    # 防御占位符参数
    placeholder_pattern = re.compile(
        r'(result[.]|_result[.]|[.]userId|[.]id\b|<[^>]+>|[{][{][^}]+[}][}])',
        re.IGNORECASE
    )
    for k, v in params.items():
        if isinstance(v, str) and placeholder_pattern.search(v):
            return json.dumps({
                "error": f"参数 '{k}' 值 '{v}' 是占位符，请先调用 search_customer 获取真实 userId"
            })

    # params["operatorId"] = user["operatorId"]
    # params["operatorName"] = user.get("operatorName", "")
    # params["startDate"] = time.monotonic()
    # start_date = params.get("startDate")  # 缺失时返回空字符串
    # end_date = params.get("endDate")
    # time_format = "%Y-%m-%d %H:%M:%S"
    #
    # if start_date:
    #     params["startDate"] = datetime.datetime.strptime(start_date, time_format)
    # if end_date:
    #     params["endDate"] = datetime.datetime.strptime(end_date, time_format)

    try:
        if tool_def["http_method"] == "GET":
            result = await java_client.get(tool_def["java_url"], params=params)
        else:
            result = await java_client.post(tool_def["java_url"], body=params)
    except Exception as e:
        result = {"error": str(e)}
        status = "error"

    duration_ms = int((time.monotonic() - t0) * 1000)

    await audit_repo.log_tool_call(
        session_id=session_id,
        operator_id=user["operatorId"],
        operator_name=user.get("operatorName", ""),
        tool_name=tool_name,
        params=params,
        result=result,
        status=status,
        duration_ms=duration_ms,
        roles_at_call=user.get("roles", []),
        scope_injected={"operatorId": user["operatorId"], "operatorName": user.get("operatorName", "")},
        permission_rule=f"ai_tool:{tool_name}",
    )

    return json.dumps(result, ensure_ascii=False)


async def run_agent(state: AssistantState) -> dict:
    """
    ReAct 循环。
    search_customer 返回多个结果时，不用 interrupt()，
    而是直接返回 status="need_select_customer"，由 main.py 检测并推给前端。
    """
    user = state["user"]
    session_id = state["session_id"]
    selected_user_id = state.get("selected_user_id")
    selected_user_name = state.get("selected_user_name")

    logger.info(f"run agent begin state:{state}, selected_user_id:{selected_user_id}")

    all_tools = await tool_manager.get_all_enabled()
    allowed = get_allowed_tools(user, [{"name": t["name"]} for t in all_tools])
    logger.info(f"run agent allowed tools:{allowed}")

    allowed_names = {t["name"] for t in allowed}
    tool_schemas = [t for t in all_tools if t["name"] in allowed_names]

    llm = _build_llm_with_tools(tool_schemas)
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])

    # selected_user_id 仅在 resume 后首轮使用，注入为 SystemMessage 进入对话历史
    # 后续轮次模型直接从消息历史中读取客户上下文，无需外部传递
    if selected_user_id:
        messages.append(SystemMessage(
            content=f"[客户已确认] 用户选择了客户：{selected_user_name}，userId={selected_user_id}。"
                    f"后续涉及该客户的查询请直接使用此 userId，无需重新调用 search_customer"
        ))

    for _ in range(8):
        # json_str = json.dumps(messages, ensure_ascii=False, indent=2)
        logger.info(f"llm invoke message:{messages}")
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        # 逐个执行 tool_calls
        for tc in response.tool_calls:
            # 拷贝一份 args，避免直接修改原始对象
            args = dict(tc.get("args") or {})

            # 如果已经有选定客户，则对除 search_customer 以外的工具统一注入 / 覆盖 userId
            # 这样后续所有与客户相关的工具调用都不会再依赖模型自己猜 userId
            if selected_user_id and tc["name"] != "search_customer":
                args["userId"] = selected_user_id

            logger.info(f"llm invoke tc:{tc}, patched_args:{args}")

            start_date = args.get("startDate")  # 缺失时返回空字符串
            end_date = args.get("endDate")
            time_format = "%Y-%m-%d %H:%M:%S"

            if start_date:
                args["startDate"] = str_to_timestamp(start_date)
            if end_date:
                args["endDate"] = str_to_timestamp(end_date)

            raw = await _execute_tool(tc["name"], args, user, session_id)

            if tc["name"] == "search_customer":
                # 解析搜索结果
                try:
                    result_data = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    result_data = {}

                customers: list = (
                    result_data.get("data")
                    or result_data.get("list")
                    or result_data.get("records")
                    or []
                )

                if len(customers) == 0:
                    # 搜索无结果：把提示写入 ToolMessage，让模型告知用户，同时清空 selected_user_id
                    selected_user_id = None
                    selected_user_name = None
                    messages.append(ToolMessage(
                        tool_call_id=tc["id"],
                        name=tc["name"],
                        content=json.dumps({"result": "未找到匹配的客户，请确认姓名是否正确"}, ensure_ascii=False),
                    ))
                    # 跳过后续 ToolMessage append，直接进入下一轮让模型回复
                    continue
                elif len(customers) > 1:
                    # 多个结果：需要用户选择。
                    # 注意：为了满足 OpenAI tools 协议，必须先补上一条 ToolMessage，
                    # 否则下一轮对话历史中会出现带 tool_calls 的 assistant 消息却没有对应的 tool 消息。
                    messages.append(
                        ToolMessage(
                            tool_call_id=tc["id"],
                            name=tc["name"],
                            content=raw,
                        )
                    )
                    return {
                        "messages": [],
                        "query_results": {},
                        "status": "need_select_customer",
                        "customer_candidates": customers,
                        "selected_user_id": None,
                        "selected_user_name": None,
                        "current_date": datetime.datetime.now(),
                    }
                elif len(customers) == 1:
                    # 只有一个结果时，自动确认并切换当前客户，但不中断本轮流程
                    c = customers[0]
                    selected_user_id = (
                        c.get("userId")
                        or c.get("userid")
                        or c.get("id")
                    )
                    selected_user_name = (
                        c.get("userName")
                        or c.get("username")
                        or c.get("name")
                    )
                    # 不追加 SystemMessage 到 messages（会破坏消息序列）
                    # selected_user_id 已更新，后续工具调用会自动注入正确 userId

            messages.append(ToolMessage(
                tool_call_id=tc["id"],
                name=tc["name"],
                content=raw,
            ))
            # search_customer 空结果时已经在上面 continue，不会走到这里

    final = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls),
        AIMessage(content="抱歉，处理过程中出现了问题，请重试。")
    )

    confirmed_customer = (
        f"[已确认客户] {selected_user_name}，userId={selected_user_id}"
        if selected_user_id else None
    )

    return {
        "messages": [final],
        "query_results": {},
        "status": "done",
        "customer_candidates": [],
        "selected_user_id": selected_user_id,
        "selected_user_name": selected_user_name,
        "confirmed_customer": confirmed_customer,
    }


import datetime

def str_to_timestamp(time_str, time_format="%Y-%m-%d %H:%M:%S"):
    """
    字符串转时间戳（秒级）
    :param time_str: 时间字符串，如 "2026-03-19 17:31:45"
    :param time_format: 时间格式，需与字符串匹配
    :return: 秒级时间戳（int），失败返回None
    """
    try:
        dt = datetime.datetime.strptime(time_str, time_format)
        timestamp = int(dt.timestamp())
        return timestamp * 1000
    except ValueError as e:
        print(f"解析失败：{e}（格式需匹配 {time_format}）")
        return None

# 调用示例
if __name__ == '__main__':
    time_str = "2026-03-19 17:31:45"
    timestamp = str_to_timestamp(time_str) * 1000
    print(f"字符串：{time_str} → 时间戳：{timestamp}")