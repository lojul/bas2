"""The agent itself — channel-agnostic. Takes a message, returns a reply.

Deliberately no lead-qualification gate (that's what makes BAS's Teams bot feel
slow/rigid) — the system prompt tells it to search first and ask clarifying
questions only if a search comes back empty.
"""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from core.llm import build_llm
from core.tools.create_crm_lead import create_crm_lead
from core.tools.search_properties import search_properties

SYSTEM_PROMPT = """You are a Hong Kong commercial property assistant for Century 21.

Answer questions about property listings, districts, leasing terms, and
availability using the search_properties tool whenever the user asks about
specific properties, districts, or availability — search first, don't ask for
budget/district/timeline before searching. Only ask a clarifying question if
the search itself comes back empty or ambiguous.

Use create_crm_lead when the user expresses interest in a specific property or
asks to be contacted by an agent.

Only answer Hong Kong commercial property questions — politely decline
unrelated topics (e.g. cooking, coding, general trivia). Respond in the same
language the user writes in (Chinese or English). Never make up information
not returned by search_properties — if nothing matches, say so.
"""

_checkpointer = MemorySaver()
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        llm = build_llm()
        _agent = create_react_agent(
            llm,
            [search_properties, create_crm_lead],
            prompt=SYSTEM_PROMPT,
            checkpointer=_checkpointer,
        )
    return _agent


def run_turn(channel: str, conversation_id: str, message: str) -> dict:
    """Run one conversation turn.

    conversation_id is expected to already be channel-namespaced by the caller
    (e.g. "slack:C123/U456") so different channels never collide in memory.
    """
    logging.info("run_turn: channel=%s conversation_id=%s", channel, conversation_id)

    agent = _get_agent()
    config = {"configurable": {"thread_id": conversation_id}}
    result = agent.invoke({"messages": [{"role": "user", "content": message}]}, config=config)

    reply = result["messages"][-1].content

    # TODO: search_properties currently returns a formatted string, not
    # structured docs, so there's nothing to populate here yet. Revisit if a
    # channel needs structured sources (e.g. clickable listing cards).
    sources: list[dict] = []

    return {"reply": reply, "sources": sources, "conversation_id": conversation_id}
