"""The agent itself — channel-agnostic. Takes a message, returns a reply.

Deliberately no lead-qualification gate (that's what makes BAS's Teams bot feel
slow/rigid) — just answer, using tools when useful.
"""

import logging

# TODO: real implementation —
#   from langgraph.prebuilt import create_react_agent
#   from langgraph.checkpoint.memory import MemorySaver
#   from core.tools.search_properties import search_properties
#   from core.tools.create_crm_lead import create_crm_lead
#   agent = create_react_agent(llm, [search_properties, create_crm_lead], checkpointer=MemorySaver())


def run_turn(channel: str, conversation_id: str, message: str) -> dict:
    """Run one conversation turn. Not yet implemented — scaffold only.

    conversation_id is expected to already be channel-namespaced by the caller
    (e.g. "slack:C123/U456") so different channels never collide in memory.
    """
    logging.info("run_turn: channel=%s conversation_id=%s", channel, conversation_id)
    return {
        "reply": "Not yet implemented — scaffold only.",
        "sources": [],
        "conversation_id": conversation_id,
    }
