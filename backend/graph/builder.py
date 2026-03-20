from langgraph.graph import END, START, StateGraph
# langgraph>=0.2.0: MemorySaver path unchanged
from langgraph.checkpoint.memory import MemorySaver

from graph.nodes import run_agent
from graph.state import AssistantState


def build_graph(checkpointer=None):
    """
    简化后的图结构：
    START → run_agent（ReAct 循环，内部处理所有 Tool 调用）→ END

    之前的多节点路由（parse_intent / search_customer / ask_user_select ...）
    已合并进 run_agent 的 ReAct 循环，由模型自主决策调用顺序。
    """
    builder = StateGraph(AssistantState)
    builder.add_node("run_agent", run_agent)
    builder.add_edge(START, "run_agent")
    builder.add_edge("run_agent", END)

    cp = checkpointer or MemorySaver()
    return builder.compile(checkpointer=cp)


graph = build_graph()
