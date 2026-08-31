from collections.abc import Callable

from strands.agent.agent_result import AgentResult
from strands.multiagent import GraphBuilder
from strands.multiagent.base import Status
from strands.multiagent.graph import GraphState

from agent.agent_factory import agent_factory
from agent.domains import QueryPlan
from mcp_client.client import get_streamable_http_mcp_client
from prompts import (
    KNOWLEDGE_BASE_NODE_SYSTEM_PROMPT,
    PARK_RESOLVER_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    SQL_NODE_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)


SQL_TOOL_NAMES = [
    "find_parks_established_between",
    "find_oldest_parks",
    "find_park_by_code",
    "find_parks_in_state",
    "find_parks_by_name",
    "get_all_parks",
]

RESOLVER_TOOL_NAMES = [
    "find_park_by_code",
    "find_parks_by_name",
]

KNOWLEDGE_BASE_TOOL_NAMES = [
    "retrieve_context",
    "search_all_park_context",
]


get_router_agent = agent_factory(
    tools=[],
    prompt=ROUTER_SYSTEM_PROMPT,
    structured_output_model=QueryPlan,
    use_session_manager=False,
)

get_park_resolver_agent = agent_factory(
    tools=[
        get_streamable_http_mcp_client(
            tool_filters={"allowed": RESOLVER_TOOL_NAMES}
        )
    ],
    prompt=PARK_RESOLVER_SYSTEM_PROMPT,
    use_session_manager=False,
)

get_sql_agent = agent_factory(
    tools=[
        get_streamable_http_mcp_client(
            tool_filters={"allowed": SQL_TOOL_NAMES}
        )
    ],
    prompt=SQL_NODE_SYSTEM_PROMPT,
    use_session_manager=False,
)

get_knowledge_base_agent = agent_factory(
    tools=[
        get_streamable_http_mcp_client(
            tool_filters={"allowed": KNOWLEDGE_BASE_TOOL_NAMES}
        )
    ],
    prompt=KNOWLEDGE_BASE_NODE_SYSTEM_PROMPT,
    use_session_manager=False,
)

get_synthesis_agent = agent_factory(
    tools=[],
    prompt=SYNTHESIS_SYSTEM_PROMPT,
    use_session_manager=False,
)


def _query_plan(state: GraphState) -> QueryPlan | None:
    """Return the router's validated plan when routing completed successfully."""
    node_result = state.results.get("router")
    if node_result is None or not isinstance(node_result.result, AgentResult):
        return None

    plan = node_result.result.structured_output
    return plan if isinstance(plan, QueryPlan) else None


def _when(
    *routes: str,
    park_named: bool | None = None,
) -> Callable[[GraphState], bool]:
    """Build a conditional edge predicate from the router's QueryPlan."""

    def condition(state: GraphState) -> bool:
        plan = _query_plan(state)
        if plan is None or plan.route not in routes:
            return False

        if park_named is None:
            return True

        has_park_name = bool(plan.park_name and plan.park_name.strip())
        return has_park_name is park_named

    return condition


def _hybrid_evidence_complete(state: GraphState) -> bool:
    """Wait for both evidence branches before hybrid synthesis."""
    plan = _query_plan(state)
    if plan is None or plan.route != "hybrid":
        return False

    return all(
        node_id in state.results
        and state.results[node_id].status == Status.COMPLETED
        for node_id in ("sql", "knowledge_base")
    )


def create_content_loop(session_id: str, user_id: str):
    """Build the bounded SQL/Knowledge Base graph for one user session."""
    router = get_router_agent(session_id, user_id)
    park_resolver = get_park_resolver_agent(session_id, user_id)
    sql_agent = get_sql_agent(session_id, user_id)
    knowledge_base_agent = get_knowledge_base_agent(session_id, user_id)
    synthesis_agent = get_synthesis_agent(session_id, user_id)

    builder = GraphBuilder()
    builder.set_graph_id("parks_content_loop")

    builder.add_node(router, "router")
    builder.add_node(park_resolver, "park_resolver")
    builder.add_node(sql_agent, "sql")
    builder.add_node(knowledge_base_agent, "knowledge_base")
    builder.add_node(synthesis_agent, "synthesis")

    # Resolve named parks before querying either source.
    builder.add_edge(
        "router",
        "park_resolver",
        condition=_when("sql", "knowledge_base", "hybrid", park_named=True),
    )

    # Requests without a named park enter the selected evidence node directly.
    builder.add_edge(
        "router",
        "sql",
        condition=_when("sql", "hybrid", park_named=False),
    )
    builder.add_edge(
        "router",
        "knowledge_base",
        condition=_when("knowledge_base", park_named=False),
    )

    # Named requests continue from resolution to their selected source nodes.
    builder.add_edge(
        "park_resolver",
        "sql",
        condition=_when("sql", "hybrid"),
    )
    builder.add_edge(
        "park_resolver",
        "knowledge_base",
        condition=_when("knowledge_base", "hybrid"),
    )

    # Broad hybrid requests use SQL first so retrieval can consume its records.
    builder.add_edge(
        "sql",
        "knowledge_base",
        condition=_when("hybrid", park_named=False),
    )

    # Single-source routes synthesize when their evidence node completes.
    builder.add_edge("sql", "synthesis", condition=_when("sql"))
    builder.add_edge(
        "knowledge_base",
        "synthesis",
        condition=_when("knowledge_base"),
    )

    # Hybrid synthesis waits until both evidence branches have completed.
    builder.add_edge(
        "sql",
        "synthesis",
        condition=_hybrid_evidence_complete,
    )
    builder.add_edge(
        "knowledge_base",
        "synthesis",
        condition=_hybrid_evidence_complete,
    )

    builder.set_entry_point("router")
    builder.set_max_node_executions(6)
    builder.set_execution_timeout(180)
    builder.set_node_timeout(90)

    return builder.build()
