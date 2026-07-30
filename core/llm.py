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
    )
