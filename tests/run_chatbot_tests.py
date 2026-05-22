#!/usr/bin/env python
"""Run chatbot v2 tests with .env loaded.

Usage: python tests/run_chatbot_tests.py
"""

import os
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Print loaded keys
print("=== Environment Check ===")
print(f"OPENROUTER_API_KEY: {'✓' if os.environ.get('OPENROUTER_API_KEY') else '✗'}")
print(f"AZURE_SEARCH_API_KEY: {'✓' if os.environ.get('AZURE_SEARCH_API_KEY') else '✗'}")
print(f"AZURE_OPENAI_KEY: {'✓' if os.environ.get('AZURE_OPENAI_KEY') else '✗'}")
print(f"TAVILY_API_KEY: {'✓' if os.environ.get('TAVILY_API_KEY') else '✗'}")
print()

# Run specific tests
import pytest

if __name__ == "__main__":
    # Run all tests
    sys.exit(pytest.main([
        "tests/test_chatbot_v2.py",
        "-v",
        "--tb=short",
        "-x",  # Stop on first failure
    ]))
