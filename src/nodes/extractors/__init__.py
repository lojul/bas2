"""Extraction strategies for different document structures.

Each extractor receives a DocumentState (post-OCR, post-classify, post-analyze)
and returns a DocumentState with `extracted` populated.

Path routing is done in graph.py based on state.extraction_path:
  STRUCTURED    → structured.py   (standard single-pass LLM)
  CONVERSATIONAL → conversational.py (two-pass LangChain: segment → per-entity)
  VISUAL        → structured.py   (fallback until vision path is built)
"""
