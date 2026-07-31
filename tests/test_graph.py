"""Tests for the LangGraph workflow."""

from src.graph import (
    GraphState,
    app,
    compile_graph,
    create_graph,
    run_ocr_node,
    classify_node,
    extract_structured_node,
    review_gate_node,
    reject_node,
)
from src.state import DocumentState, ProcessingStatus


class TestRunOcrNode:
    def test_node_exists(self):
        assert callable(run_ocr_node)


class TestClassifyNode:
    def test_node_exists(self):
        assert callable(classify_node)


class TestExtractNode:
    def test_node_exists(self):
        assert callable(extract_structured_node)


class TestRejectNode:
    def test_node_exists(self):
        assert callable(reject_node)

    def test_node_sets_rejected_status(self):
        state = DocumentState(file_path="", file_name="test.pdf")
        result = reject_node({"state": state})
        assert result["state"].odoo_sync_status == "rejected"


class TestGraphCreation:
    def test_create_graph_returns_state_graph(self):
        graph = create_graph()
        assert graph is not None

    def test_compile_graph_returns_compiled(self):
        compiled = compile_graph()
        assert compiled is not None
        assert hasattr(compiled, "invoke")

    def test_app_is_compiled(self):
        assert app is not None
        assert hasattr(app, "invoke")


class TestGraphStructure:
    def test_graph_has_expected_nodes(self):
        graph = create_graph()
        compiled = graph.compile()
        graph_dict = compiled.get_graph().to_json()

        node_ids = [n.get("id") for n in graph_dict.get("nodes", [])]
        assert "run_ocr" in node_ids
        assert "classify" in node_ids
        assert "extract_structured" in node_ids
        assert "extract_conversational" in node_ids
        assert "review_gate" in node_ids
        assert "odoo_sync" in node_ids
        assert "knowledge_sync" in node_ids
        assert "contact_sync" in node_ids
        assert "reject" in node_ids
        # Removed nodes should NOT be present
        assert "get_download_url" not in node_ids
        assert "index" not in node_ids

    def test_graph_flow_structure(self):
        graph = create_graph()
        compiled = graph.compile()
        graph_dict = compiled.get_graph().to_json()

        edges = graph_dict.get("edges", [])
        edge_pairs = [(e.get("source"), e.get("target")) for e in edges]

        assert ("__start__", "run_ocr") in edge_pairs
        assert ("run_ocr", "classify") in edge_pairs
        assert ("classify", "analyze") in edge_pairs
        assert ("analyze", "extract_structured") in edge_pairs
        assert ("analyze", "extract_conversational") in edge_pairs
        assert ("extract_structured", "review_gate") in edge_pairs
        assert ("extract_conversational", "review_gate") in edge_pairs
        assert ("review_gate", "odoo_sync") in edge_pairs
        assert ("review_gate", "reject") in edge_pairs
        assert ("odoo_sync", "__end__") in edge_pairs
