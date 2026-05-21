"""Pytest configuration and fixtures."""

import os
import sys

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set minimal env vars for testing (avoid loading real secrets in unit tests)
os.environ.setdefault("LANGCHAIN_API_KEY", "test-key")
os.environ.setdefault("LANGCHAIN_PROJECT", "document-processor-test")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")  # Disable tracing in tests


@pytest.fixture
def sample_file_path():
    """Sample file path for testing."""
    return "/test/sample-document.pdf"


@pytest.fixture
def sample_file_name():
    """Sample file name for testing."""
    return "sample-document.pdf"
