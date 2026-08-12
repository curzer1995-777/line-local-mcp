from line_local_mcp.redaction import redact_text


def test_redacts_password_and_token_query_parameter():
    value = "密碼：hello https://example.com/doc?token=secret&view=1"
    redacted, changed = redact_text(value)
    assert changed is True
    assert "hello" not in redacted
    assert "secret" not in redacted
    assert "view=1" in redacted


def test_leaves_normal_text_unchanged():
    value = "Please confirm the invoice tomorrow."
    assert redact_text(value) == (value, False)
