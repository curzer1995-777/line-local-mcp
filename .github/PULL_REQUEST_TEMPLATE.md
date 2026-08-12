## Summary

Describe the user-visible change and why it is needed.

## Verification

- Tests run:
- Synthetic fixtures added or updated:

## Security and privacy

- [ ] The change preserves the read-only design.
- [ ] No real LINE data, credentials, identifiers, memory dumps, or private paths are included.
- [ ] MCP tool annotations remain accurate.
- [ ] Network exposure and Keychain behavior are unchanged, or the impact is documented in `SECURITY.md`.
- [ ] Relevant README and CHANGELOG entries are updated.

## Checklist

- [ ] `python -m compileall -q src tests` passes.
- [ ] `pytest` passes.
- [ ] The pull request is focused and contains no unrelated changes.
