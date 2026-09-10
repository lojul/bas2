"""LLM client — OpenRouter, moonshotai/kimi-k2.

See core/config.py's AGENT_MODEL comment for why k2 specifically (not k3/k2.6+,
not Azure OpenAI). OpenRouter is OpenAI-API-compatible, so a plain ChatOpenAI
pointed at OpenRouter's base_url works and plugs directly into LangGraph's
create_react_agent.
"""

from langchain_openai import ChatOpenAI

from core.config import AGENT_MODEL, OPENROUTER_API_KEY


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=AGENT_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.3,
        # Without an explicit cap, langchain.agents.create_agent's model_node
        # auto-computes max_tokens to fill kimi-k2's remaining advertised
        # context window (observed: 100352) — which exceeds what OpenRouter's
        # Novita provider actually allows for this model (98304), so every
        # single request failed with a 400 from the provider. Well under the
        # ceiling; plenty for a property-search reply.
        max_tokens=4000,
    )
