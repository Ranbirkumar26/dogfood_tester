"""LangGraph assembly: wire the nodes into the plan-execute-review state machine.

Design rationale (design D1): the control loop is a LangGraph StateGraph so we get durable
execution, per-thread checkpointing, and graph visualization for free. This module is a thin
wiring layer; all behavior lives in GraphNodes and the pure decide/loop functions. The graph
shape is exactly docs/architecture/state-machine.md:

    bootstrap -> planner -> executor -> reviewer -> decide -+-> planner   (continue / replan)
                    ^                                        +-> executor  (retry / next step)
                    |                                        +-> finalize  (done / budget / stop)
                    +----------------------------------------+
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from website_agent.agent.decide import Edge
from website_agent.agent.graph_state import GraphState
from website_agent.agent.nodes import GraphDeps, GraphNodes, route_after_decide


def build_graph(deps: GraphDeps, checkpointer: Any | None = None) -> Any:
    """Compile the agent graph over ``deps``. Pass a checkpointer for durable execution."""
    nodes = GraphNodes(deps)
    graph: StateGraph[GraphState] = StateGraph(GraphState)

    graph.add_node("bootstrap", nodes.bootstrap)
    graph.add_node("planner", nodes.planner)
    graph.add_node("executor", nodes.executor)
    graph.add_node("reviewer", nodes.reviewer)
    graph.add_node("decide", nodes.decide)
    graph.add_node("finalize", nodes.finalize)

    graph.add_edge(START, "bootstrap")
    graph.add_edge("bootstrap", "planner")
    # An empty plan (nothing left to do) finalizes; otherwise execute the head step.
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"executor": "executor", "finalize": "finalize"},
    )
    graph.add_edge("executor", "reviewer")
    graph.add_edge("reviewer", "decide")
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {
            Edge.PLANNER.value: "planner",
            Edge.EXECUTOR.value: "executor",
            Edge.FINALIZE.value: "finalize",
        },
    )
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


def _route_after_planner(state: GraphState) -> str:
    """Finalize immediately if the planner produced no steps (frontier exhausted)."""
    if state.plan is None or state.plan.is_empty:
        return "finalize"
    return "executor"
