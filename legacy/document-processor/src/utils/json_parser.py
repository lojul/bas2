"""Shared JSON parsing utility for AI responses."""

import re
import json
from typing import Any


def parse_json_response(content: str) -> dict[str, Any]:
    """Parse JSON from AI response, handling common formats.

    Handles:
    - Plain JSON
    - JSON wrapped in markdown code blocks
    - JSON with trailing text
    - Common JSON syntax errors (trailing commas)

    Args:
        content: Raw AI response content

    Returns:
        Parsed JSON as dict

    Raises:
        ValueError: If JSON cannot be parsed
    """
    content = content.strip()

    # Extract from markdown code blocks
    if "```" in content:
        code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', content)
        if code_blocks:
            content = code_blocks[0].strip()

    # Find JSON start if content has preamble text
    if not content.startswith('{') and not content.startswith('['):
        for i, char in enumerate(content):
            if char in '{[':
                content = content[i:]
                break
        else:
            raise ValueError(f"No JSON found in response: {content[:100]}")

    # Try parsing as-is
    try:
        result = json.loads(content)
        return _normalize_result(result)
    except json.JSONDecodeError:
        pass

    # Fix common JSON issues (trailing commas)
    fixed_content = re.sub(r',\s*}', '}', content)
    fixed_content = re.sub(r',\s*]', ']', fixed_content)

    try:
        result = json.loads(fixed_content)
        return _normalize_result(result)
    except json.JSONDecodeError:
        pass

    # Try to extract partial valid JSON (find matching braces)
    try:
        brace_count = 0
        last_valid_pos = 0
        for i, char in enumerate(content):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_valid_pos = i + 1
                    break

        if last_valid_pos > 0:
            partial = content[:last_valid_pos]
            result = json.loads(partial)
            return _normalize_result(result)
    except json.JSONDecodeError:
        pass

    # All parsing attempts failed
    raise ValueError(f"Could not parse JSON: {content[:200]}")


def _normalize_result(result: Any) -> dict[str, Any]:
    """Normalize parsed result to dict format."""
    if isinstance(result, list):
        return {"items": result}
    if isinstance(result, dict):
        return result
    return {"value": result}
