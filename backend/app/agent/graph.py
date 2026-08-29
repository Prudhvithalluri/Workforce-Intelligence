import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    decide_and_execute,
    finalize_if_complete,
    recover,
    start_or_continue,
    wait_for_otp,
)
from agent.state import AgentState
from config import settings

logger = logging.getLogger(__name__)


def route_after_decide(state: AgentState):
    logger.info(
        "graph_route status=%s otp_required=%s has_error=%s retries=%s",
        state.get("status"),
        bool(state.get("otp_required")),
        bool(state.get("error")),
        state.get("retry_count", 0),
    )
    if state.get("status") in ("completed", "failed"):
        return "finalize"

    if state.get("otp_required") or state.get("status") == "waiting_for_user":
        return "otp_wait"

    if state.get("error"):
        if state.get("retry_count", 0) >= settings.MAX_AGENT_RETRIES:
            return "finalize"
        return "recover"

    return "decide"


builder = StateGraph(AgentState)

builder.add_node("start", start_or_continue)
builder.add_node("decide", decide_and_execute)
builder.add_node("recover", recover)
builder.add_node("otp_wait", wait_for_otp)
builder.add_node("finalize", finalize_if_complete)

builder.add_edge(START, "start")
builder.add_edge("start", "decide")

builder.add_conditional_edges(
    "decide",
    route_after_decide,
    {
        "decide": "decide",
        "recover": "recover",
        "otp_wait": "otp_wait",
        "finalize": "finalize",
    },
)

builder.add_edge("recover", "decide")
builder.add_edge("otp_wait", "decide")
builder.add_edge("finalize", END)

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)
