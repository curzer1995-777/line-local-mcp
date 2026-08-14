# Changelog

All notable changes to this project are documented here. The project follows [Semantic Versioning](https://semver.org/) where practical.

## [Unreleased]

## [0.2.0] - 2026-08-14

### Added

- Strict Pydantic output models and JSON Schemas for every MCP tool.
- Machine-readable, model-recoverable tool execution errors.
- Explicit idempotent/read-only annotations and prompt-injection guidance for message data.
- Compatibility tests for both MCP 2026-07-28 and legacy clients.

### Changed

- Migrated from MCP Python SDK 1.x to 2.x while preserving the five existing tool names.
- Require timezone-aware ISO 8601 values for message and chat time filters.
- Expanded server and tool metadata so clients can select tools more reliably.

## [0.1.0] - 2026-08-12

### Added

- Read-only MCP tools for status, chat listing, message retrieval, search, and recent activity.
- Disposable encrypted-database snapshots and macOS Keychain storage.
- One-time verified key bootstrap using an isolated temporary LINE app copy.
- Default official-account exclusion and common secret-pattern redaction.
- macOS installer, diagnostic command, synthetic test suite, and GitHub Actions CI.
- Bilingual project origin, setup, security, privacy, troubleshooting, and limitation documentation.

[Unreleased]: https://github.com/curzer1995-777/line-local-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/curzer1995-777/line-local-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/curzer1995-777/line-local-mcp/releases/tag/v0.1.0
