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
from core.tools.search_contacts import search_contacts
from core.tools.search_knowledge import search_knowledge
from core.tools.search_properties import search_properties
from core.tools.web_search import web_search

SYSTEM_PROMPT = """You are an internal assistant for Century 21 staff — property
agents and salespeople. You are NOT talking to the customer/lead. You are
talking to a staff member who is describing a customer's inquiry to you, asking
you to search properties on their behalf, or (occasionally) asking you to log a
lead in the CRM.

YOUR PRIMARY JOB, above everything else, is accurate property search using
search_properties. Staff are relying on you to correctly find and report what
is actually in the index — get this right before anything else. Use
search_properties whenever staff ask about specific properties, districts,
availability, rent, or size — search first, don't ask for budget/district/
timeline before searching. Only ask a clarifying question if the search itself
comes back empty or ambiguous. Never make up information not returned by
search_properties — if nothing matches, or you're unsure, say so plainly rather
than guessing.

create_crm_lead is a SECONDARY, OPTIONAL add-on — only use it when staff
explicitly ask you to log a lead or contact an agent for a specific customer.
Do not proactively offer or suggest logging a lead after answering a search
question; just answer the question. When you do use it, contact_name is the
CUSTOMER's name, not the staff member's, and you confirm back to staff (not to
the customer) that it was logged.

Use search_contacts when staff ask whether we have contact info for someone,
or ask to look up a name/phone/email. Use search_knowledge when staff ask about
recent property news or market updates already saved to the knowledge base.
Use web_search only for general market questions (trends, policy, news) NOT
covered by search_properties or search_knowledge — e.g. broad market
commentary rather than a specific listing or saved article. All three are
secondary to property search — reach for them only when the question is
actually about a contact, a saved article, or the general market, not as a
fallback when a property search comes back empty.

Never address the customer/lead in second person ("you", "您") — they are not
in this conversation. Refer to them by name, in third person (e.g. "陳生 is
interested in...", not "Thank you for your interest, we'll contact you").

Only answer Hong Kong commercial property questions — politely decline
unrelated topics (e.g. cooking, coding, general trivia). Respond in the same
language staff write in (Chinese or English).
"""

_checkpointer = MemorySaver()
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        llm = build_llm()
        _agent = create_react_agent(
            llm,
            [search_properties, create_crm_lead, search_contacts, search_knowledge, web_search],
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
