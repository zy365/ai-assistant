from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AssistantState(TypedDict):
    messages:            Annotated[list, add_messages]
    user:                dict
    session_id:          str
    query_results:       dict[str, Any]
    status:              str
    customer_candidates: list[dict]
    selected_user_id:    str | None
    selected_user_name:  str | None
    confirmed_customer:  str | None
