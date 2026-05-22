"""Tests for refactored chatbot v2.

Run with: pytest tests/test_chatbot_v2.py -v
"""

import os
import pytest
from unittest.mock import patch, MagicMock


# ============ Unit Tests ============

class TestQueryRouter:
    """Test query routing logic."""

    def test_web_only_patterns(self):
        from src.nodes.chatbot_v2 import route_query

        # Should route to web
        assert route_query("香港商業地產市場趨勢") == "web"
        assert route_query("樓市走勢") == "web"
        assert route_query("property market trend") == "web"

    def test_vector_patterns(self):
        from src.nodes.chatbot_v2 import route_query

        # Should route to vector
        assert route_query("中環有什麼寫字樓出租") == "vector"
        assert route_query("尖沙咀商舖租金") == "vector"
        assert route_query("office for rent in Central") == "vector"

    def test_hybrid_patterns(self):
        from src.nodes.chatbot_v2 import route_query

        # Should route to hybrid
        assert route_query("比較中環同尖沙咀租金") == "hybrid"
        assert route_query("compare office rents") == "hybrid"


class TestBuildContext:
    """Test context building."""

    def test_empty_context(self):
        from src.nodes.chatbot_v2 import build_context

        result = build_context([], [])
        assert "No relevant documents found" in result

    def test_documents_only(self):
        from src.nodes.chatbot_v2 import build_context

        docs = [{
            "file_name": "test.pdf",
            "document_type": "listing",
            "content": "Test content",
            "extracted_data": {"building_name": "Test Building"},
        }]
        result = build_context(docs, [])
        assert "test.pdf" in result
        assert "Test Building" in result

    def test_with_web_results(self):
        from src.nodes.chatbot_v2 import build_context

        docs = [{"file_name": "test.pdf", "document_type": "listing", "content": "Test", "extracted_data": {}}]
        web = [{"title": "News Article", "url": "https://example.com", "content": "Web content"}]

        result = build_context(docs, web)
        assert "Web Results" in result
        assert "News Article" in result


class TestLangChainModels:
    """Test LangChain model initialization."""

    def test_get_llm(self):
        from src.nodes.chatbot_v2 import get_llm

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            llm = get_llm()
            assert llm is not None
            assert llm.model_name == "meta-llama/llama-3.3-70b-instruct"

    def test_get_fast_llm(self):
        from src.nodes.chatbot_v2 import get_fast_llm

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            llm = get_fast_llm()
            assert llm is not None
            assert llm.model_name == "deepseek/deepseek-chat"


# ============ Integration Tests (require API keys) ============

@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set"
)
class TestIntegration:
    """Integration tests requiring real API keys."""

    def test_query_variations(self):
        """Test query variation generation."""
        from src.nodes.chatbot_v2 import generate_query_variations

        queries = generate_query_variations("中環寫字樓")
        assert len(queries) >= 1
        assert "中環寫字樓" in queries  # Original should be included

    @pytest.mark.skipif(
        not os.environ.get("AZURE_SEARCH_API_KEY"),
        reason="AZURE_SEARCH_API_KEY not set"
    )
    def test_search_documents(self):
        """Test document search."""
        from src.nodes.chatbot_v2 import search_documents

        results = search_documents("中環寫字樓", top_k=3)
        assert isinstance(results, list)

    @pytest.mark.skipif(
        not os.environ.get("TAVILY_API_KEY"),
        reason="TAVILY_API_KEY not set"
    )
    def test_web_search(self):
        """Test web search."""
        from src.nodes.chatbot_v2 import web_search

        results = web_search("Hong Kong property market", max_results=2)
        assert isinstance(results, list)
        # Should have results or error dict
        assert len(results) > 0


# ============ End-to-End Tests ============

@pytest.mark.skipif(
    not all([
        os.environ.get("OPENROUTER_API_KEY"),
        os.environ.get("AZURE_SEARCH_API_KEY"),
        os.environ.get("AZURE_OPENAI_KEY"),
    ]),
    reason="API keys not set for E2E test"
)
class TestEndToEnd:
    """End-to-end tests."""

    def test_chat_vector_query(self):
        """Test chat with vector search query."""
        from src.nodes.chatbot_v2 import chat

        response = chat("中環有什麼寫字樓出租?", thread_id="test-vector")
        assert response.answer or response.error
        if not response.error:
            assert len(response.answer) > 0

    def test_chat_web_query(self):
        """Test chat with web search query."""
        from src.nodes.chatbot_v2 import chat

        response = chat("香港商業地產市場趨勢", thread_id="test-web")
        assert response.answer or response.error

    def test_chat_stream(self):
        """Test streaming chat."""
        from src.nodes.chatbot_v2 import chat_stream, get_stream_metadata

        chunks = list(chat_stream("中環寫字樓", thread_id="test-stream"))
        assert len(chunks) > 0

        metadata = get_stream_metadata("test-stream")
        assert isinstance(metadata.sources, list)

    def test_conversation_memory(self):
        """Test conversation memory persists."""
        import uuid
        from src.nodes.chatbot_v2 import chat, get_conversation_history

        # Use unique thread_id to avoid conflicts with other tests
        thread_id = f"test-memory-{uuid.uuid4()}"

        # First message
        response = chat("中環寫字樓", thread_id=thread_id)
        assert response.answer, f"Chat failed: {response.error}"

        # Check history
        history = get_conversation_history(thread_id)
        assert len(history) >= 2, f"Expected >= 2 messages, got {len(history)}"


# ============ Comparison Tests ============

@pytest.mark.skipif(
    not all([
        os.environ.get("OPENROUTER_API_KEY"),
        os.environ.get("AZURE_SEARCH_API_KEY"),
    ]),
    reason="API keys not set"
)
class TestComparison:
    """Compare v1 and v2 outputs."""

    def test_same_router_results(self):
        """Ensure routing logic matches between versions."""
        from src.nodes.chatbot_v2 import route_query as route_v2

        # Import v1 router (from backup)
        try:
            from src.nodes.chatbot_backup import route_query as route_v1
        except ImportError:
            pytest.skip("Backup not available")

        test_queries = [
            "中環寫字樓出租",
            "香港商業地產市場趨勢",
            "比較中環同尖沙咀",
            "office for rent",
            "property market news",
        ]

        for query in test_queries:
            v1_result = route_v1(query)
            v2_result = route_v2(query)
            assert v1_result == v2_result, f"Routing mismatch for '{query}': v1={v1_result}, v2={v2_result}"


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
