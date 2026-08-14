# Changelog

All notable changes to this project are documented here. The project follows [Semantic Versioning](https://semver.org/) where practical.

## [Unreleased]

## [0.3.0] - 2026-08-15

### Added

- `read_chat_activity` for resolving all matching chat names and reading one explicit time window in a single snapshot-backed tool call.
- Explicit result completeness fields for bounded chat, message, search, and activity results.
- Safe structured message metadata for alt text, file names, sizes, dimensions, durations, media types, and attachment availability without exposing download URLs.
- Message text provenance distinguishing original text, previews, metadata, and placeholders.
- Generation identifiers and snapshot-cache diagnostics in structured results.

### Changed

- Chat-name filtering now evaluates every eligible chat instead of a fixed over-fetched candidate window.
- Literal message search also covers safe textual metadata and applies official-account filtering before result limits.
- Reuse an immutable, generation-aware encrypted-database snapshot and in-process Keychain value for the configured short TTL; source, WAL, or SHM changes invalidate reuse.
- Verify source fingerprints before and after copying, retry changing sources, and retain leased generations until active readers finish.
- Cache chat/name indexes per generation, combine bounded rows and exact match counts in one query, and use exact per-chat index seeks for the newest-message timestamp.
- Select and order recent activity by exact message timestamps rather than potentially stale chat metadata.

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

[Unreleased]: https://github.com/curzer1995-777/line-local-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/curzer1995-777/line-local-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/curzer1995-777/line-local-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/curzer1995-777/line-local-mcp/releases/tag/v0.1.0
