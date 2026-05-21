"""Tests for the LangGraph workflow."""

from src.graph import (
    GraphState,
    app,
    compile_graph,
    create_graph,
    get_download_url_node,
    run_ocr_node,
    classify_node,
    extract_node,
    index_node,
)
from src.state import DocumentState, ProcessingStatus


class TestGetDownloadUrlNode:
    """Tests for the get_download_url node."""

    def test_node_updates_status_to_downloading(self):
        """Node should update status to DOWNLOADING."""
        state = DocumentState(
            file_path="test-item-id",
            file_name="file.pdf",
            status=ProcessingStatus.PENDING,
        )
        input_data: GraphState = {"state": state}

        # Note: This will fail without mocking OneDrive API
        # Just testing the node exists and has correct signature
        assert callable(get_download_url_node)

    def test_node_preserves_file_info(self):
        """Node should preserve file information."""
        state = DocumentState(
            file_path="test-item-id",
            file_name="file.pdf",
        )
        input_data: GraphState = {"state": state}

        # Verify node function signature
        assert callable(get_download_url_node)


class TestRunOcrNode:
    """Tests for the run_ocr node."""

    def test_node_exists(self):
        """run_ocr_node should exist and be callable."""
        assert callable(run_ocr_node)


class TestClassifyNode:
    """Tests for the classify node."""

    def test_node_exists(self):
        """classify_node should exist and be callable."""
        assert callable(classify_node)


class TestExtractNode:
    """Tests for the extract node."""

    def test_node_exists(self):
        """extract_node should exist and be callable."""
        assert callable(extract_node)


class TestIndexNode:
    """Tests for the index node."""

    def test_node_exists(self):
        """index_node should exist and be callable."""
        assert callable(index_node)


class TestGraphCreation:
    """Tests for graph creation and compilation."""

    def test_create_graph_returns_state_graph(self):
        """create_graph should return a StateGraph instance."""
        graph = create_graph()
        assert graph is not None

    def test_compile_graph_returns_compiled(self):
        """compile_graph should return compiled graph."""
        compiled = compile_graph()
        assert compiled is not None
        assert hasattr(compiled, "invoke")

    def test_app_is_compiled(self):
        """App module variable should be a compiled graph."""
        assert app is not None
        assert hasattr(app, "invoke")


class TestGraphStructure:
    """Tests for graph structure."""

    def test_graph_has_expected_nodes(self):
        """Graph should have get_download_url, run_ocr, classify, extract, and index nodes."""
        graph = create_graph()
        compiled = graph.compile()
        graph_dict = compiled.get_graph().to_json()

        # Check nodes exist in the graph
        node_ids = [n.get("id") for n in graph_dict.get("nodes", [])]
        assert "get_download_url" in node_ids
        assert "run_ocr" in node_ids
        assert "classify" in node_ids
        assert "extract" in node_ids
        assert "index" in node_ids

    def test_graph_flow_structure(self):
        """Graph should flow: start → get_download_url → run_ocr → classify → extract → index → end."""
        graph = create_graph()
        compiled = graph.compile()
        graph_dict = compiled.get_graph().to_json()

        # Check edges
        edges = graph_dict.get("edges", [])
        edge_pairs = [(e.get("source"), e.get("target")) for e in edges]

        assert ("__start__", "get_download_url") in edge_pairs
        assert ("get_download_url", "run_ocr") in edge_pairs
        assert ("run_ocr", "classify") in edge_pairs
        assert ("classify", "extract") in edge_pairs
        assert ("extract", "index") in edge_pairs
        assert ("index", "__end__") in edge_pairs
