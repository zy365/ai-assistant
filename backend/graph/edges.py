# 注：此文件为旧版多节点路由的条件函数，已被 ReAct 单节点取代，保留仅供参考
from typing import Literal
from graph.state import AssistantState


def route_by_customer_count(
    state: AssistantState,
) -> Literal["none", "single", "multiple", "skip"]:
    """根据客户搜索结果决定路由方向"""
    intent = state.get("intent", {})
    # 如果意图里没有客户名，直接跳过客户选择流程
    if not intent.get("userName"):
        return "skip"

    count = len(state.get("customer_candidates", []))
    if count == 0:
        return "none"
    elif count == 1:
        return "single"
    else:
        return "multiple"
