from src.core.output import truncate_output


def test_truncate_output_adds_suffix():
    text = "a" * 100
    result = truncate_output(text, limit=50)
    assert len(result) > 50
    assert "truncated" in result
    assert result.startswith("a" * 50)


def test_truncate_output_passthrough():
    assert truncate_output("hello", limit=50) == "hello"
    assert truncate_output(None, limit=50) == ""