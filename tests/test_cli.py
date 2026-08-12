from line_local_mcp.cli import build_parser


def test_cli_defaults_to_local_stdio():
    args = build_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.port == 8765
    assert args.doctor is False
    assert args.setup_key is False


def test_cli_supports_doctor():
    assert build_parser().parse_args(["--doctor"]).doctor is True


def test_cli_supports_key_setup():
    assert build_parser().parse_args(["--setup-key"]).setup_key is True
