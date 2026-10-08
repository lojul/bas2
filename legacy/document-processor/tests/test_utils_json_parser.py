"""Tests for JSON parser utility."""

import pytest
from src.utils.json_parser import parse_json_response


class TestParseJsonResponse:
    """Tests for parse_json_response function."""

    def test_parse_plain_json(self):
        """Should parse plain JSON object."""
        result = parse_json_response('{"type": "listing", "confidence": 0.9}')
        assert result == {"type": "listing", "confidence": 0.9}

    def test_parse_json_with_whitespace(self):
        """Should parse JSON with leading/trailing whitespace."""
        result = parse_json_response('  \n{"name": "test"}\n  ')
        assert result == {"name": "test"}

    def test_parse_markdown_code_block(self):
        """Should extract JSON from markdown code block."""
        content = '```json\n{"type": "news"}\n```'
        result = parse_json_response(content)
        assert result == {"type": "news"}

    def test_parse_markdown_code_block_no_language(self):
        """Should extract JSON from code block without language tag."""
        content = '```\n{"type": "contact"}\n```'
        result = parse_json_response(content)
        assert result == {"type": "contact"}

    def test_parse_json_with_preamble(self):
        """Should find JSON after preamble text."""
        content = 'Here is the result:\n{"building": "Tower A"}'
        result = parse_json_response(content)
        assert result == {"building": "Tower A"}

    def test_parse_json_array(self):
        """Should wrap array in items key."""
        result = parse_json_response('[{"unit": "1A"}, {"unit": "2B"}]')
        assert result == {"items": [{"unit": "1A"}, {"unit": "2B"}]}

    def test_fix_trailing_comma_in_object(self):
        """Should fix trailing comma in object."""
        result = parse_json_response('{"name": "test",}')
        assert result == {"name": "test"}

    def test_fix_trailing_comma_in_array(self):
        """Should fix trailing comma in array."""
        result = parse_json_response('{"items": [1, 2, 3,]}')
        assert result == {"items": [1, 2, 3]}

    def test_extract_partial_json(self):
        """Should extract partial valid JSON when truncated."""
        content = '{"name": "test", "value": 123} extra text here'
        result = parse_json_response(content)
        assert result == {"name": "test", "value": 123}

    def test_raises_on_no_json(self):
        """Should raise ValueError when no JSON found."""
        with pytest.raises(ValueError, match="No JSON found"):
            parse_json_response("This is plain text with no JSON")

    def test_raises_on_invalid_json(self):
        """Should raise ValueError on invalid JSON."""
        with pytest.raises(ValueError, match="Could not parse JSON"):
            parse_json_response('{"invalid": json syntax}')

    def test_complex_nested_json(self):
        """Should parse complex nested structures."""
        content = '''{"building": "Tower", "units": [{"floor": "1", "rent": 5000}]}'''
        result = parse_json_response(content)
        assert result["building"] == "Tower"
        assert len(result["units"]) == 1
        assert result["units"][0]["rent"] == 5000
