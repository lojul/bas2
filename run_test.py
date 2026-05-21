#!/usr/bin/env python3
"""Test script to verify Sprint 1 setup and LangSmith tracing."""

import os
import sys

# Add src to path for local development
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()


def check_env():
    """Check required environment variables."""
    required = [
        "LANGCHAIN_API_KEY",
    ]
    optional = [
        ("LANGCHAIN_PROJECT", "document-processor"),
        ("LANGCHAIN_TRACING_V2", "true"),
    ]

    print("=" * 50)
    print("Environment Check")
    print("=" * 50)

    all_set = True
    for var in required:
        value = os.getenv(var)
        if value:
            print(f"  {var}: {'*' * min(8, len(value))}... (set)")
        else:
            print(f"  {var}: NOT SET (required!)")
            all_set = False

    for var, default in optional:
        value = os.getenv(var, default)
        print(f"  {var}: {value}")

    print()
    return all_set


def run_test():
    """Run the test workflow."""
    from src.graph import process_document

    print("=" * 50)
    print("Running Test Workflow")
    print("=" * 50)

    result = process_document(
        file_path="/test/sample-document.pdf",
        file_name="sample-document.pdf",
    )

    print(f"  File: {result.file_name}")
    print(f"  Path: {result.file_path}")
    print(f"  Status: {result.status.value}")
    print(f"  Document Type: {result.document_type.value}")
    print(f"  Created: {result.created_at.isoformat()}")
    print(f"  Updated: {result.updated_at.isoformat()}")
    print()

    return result


def main():
    """Main entry point."""
    print()
    print("Sprint 1: Foundation & Hello World")
    print("=" * 50)
    print()

    # Check environment
    if not check_env():
        print("ERROR: Required environment variables not set.")
        print("Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)

    # Run test
    result = run_test()

    # Success message
    print("=" * 50)
    print("SUCCESS!")
    print("=" * 50)
    print()
    print("Next steps:")
    print("1. Check LangSmith dashboard for the trace")
    print(f"   Project: {os.getenv('LANGCHAIN_PROJECT', 'document-processor')}")
    print("   URL: https://smith.langchain.com")
    print()
    print("2. You should see a trace named 'process_document'")
    print("   with a child span 'echo_node'")
    print()

    return 0 if result.status.value == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
