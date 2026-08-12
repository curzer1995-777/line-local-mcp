# Contributing

Contributions are welcome, especially compatibility reports for additional macOS and LINE Desktop versions.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). General help belongs in GitHub Issues; sensitive security reports must follow [SECURITY.md](SECURITY.md).

## Before opening an issue

- Search existing issues first.
- Use the closest issue template and provide macOS, LINE Desktop, Python, and project versions.
- Remove usernames, chat names, message text, local paths, account identifiers, keys, and tokens.
- Use synthetic data for reproductions. Never upload a real LINE database or memory dump.

## Ground rules

- Preserve the read-only design. Do not add message sending, read-state changes, UI automation, session theft, traffic interception, or attachment exfiltration.
- Never commit a LINE database, WAL/SHM file, Keychain value, memory dump, chat export, personal identifier, or real message content.
- Use synthetic fixtures for tests and bug reports.
- Keep all MCP tool annotations accurate.
- Document changes to the bootstrap, database format assumptions, redaction, or network exposure in `SECURITY.md`.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

Before submitting a pull request:

```bash
python -m compileall -q src tests
pytest
```

Explain the user-visible behavior, tests run, and security impact in the pull request.

## Pull request process

1. Keep each pull request focused on one change.
2. Add or update synthetic tests for behavior changes.
3. Update README, SECURITY, or CHANGELOG when the public contract changes.
4. Complete every applicable item in the pull request template.
5. Maintainers may request changes when a proposal weakens the read-only or local-first boundaries.

Contributions are accepted under the repository's [MIT License](LICENSE). See [GOVERNANCE.md](GOVERNANCE.md) for decision-making and release policy.
