# Contributing

Contributions are welcome, especially compatibility reports for additional macOS and LINE Desktop versions.

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
