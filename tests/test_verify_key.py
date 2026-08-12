from line_local_mcp.verify_key import verify_key


def test_verify_key_rejects_non_hex_without_opening_database(tmp_path):
    assert verify_key(tmp_path / "missing.db", "not-a-key") is False
