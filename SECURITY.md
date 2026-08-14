# Security Policy

## Status and support

LINE Local MCP is beta software built against undocumented LINE Desktop storage. Security fixes are supported on the latest `main` branch. There is no guarantee that every LINE or macOS release remains compatible.

| Version | Security support |
| --- | --- |
| Latest `main` and newest release | Supported on a best-effort basis |
| Older releases | Not supported; upgrade before reporting |

## Threat model

The project is designed for one authorized user reading their own locally synchronized LINE history on their own Mac.

Security goals:

- Never send, delete, edit, mark read, or otherwise write to LINE.
- Open only an immutable database snapshot with SQLite read-only flags.
- Never return or log the database decryption key.
- Persist a verified key only in macOS Keychain; reuse it only in server-process memory.
- Bind optional HTTP transport to `127.0.0.1` only.
- Mark every MCP tool read-only, non-destructive, and closed-world.
- Exclude official/business accounts by default and redact common secret patterns.

Out of scope and not guaranteed:

- Protecting data after an authorized MCP client sends it to an AI provider.
- Complete DLP, PII, credential, or company-secret detection.
- A compromised Mac, malicious AI client, untrusted Terminal, or attacker with the user's macOS session.
- Multi-user authorization on the loopback HTTP endpoint.
- Compatibility with future LINE storage formats.
- Use on accounts or devices the operator is not authorized to access.

## One-time key bootstrap

LINE Desktop encrypts its local database. When no usable key exists, `--setup-key`:

1. Copies `/Applications/LINE.app` into a random temporary directory.
2. Ad-hoc signs only that copy with `get-task-allow` so Apple's LLDB can inspect it.
3. Starts the temporary copy and asks the user to sign in to the same account.
4. Scans the temporary process memory for narrowly formatted candidates.
5. Accepts a candidate only if it successfully opens a snapshot of the user's local LINE database and exposes the expected LINE tables.
6. Stores the verified value in macOS Keychain without printing it.
7. Terminates the temporary process and removes temporary files.

The bootstrap does not attach to the original `/Applications/LINE.app`. macOS or LINE may retain container or login metadata created by the temporary app after the temporary bundle is deleted.

## Runtime snapshot and key cache

To avoid copying and reopening the full encrypted database for every tool call, the server may reuse one immutable snapshot for `LINE_MCP_SNAPSHOT_CACHE_SECONDS` (30 seconds by default). Setting the value to `0` disables snapshot reuse.

- A generation fingerprint covers the database main file and any WAL/SHM sidecars. A changed source fingerprint causes a new snapshot generation.
- The source fingerprint is checked before and after copying. A changing source is discarded and retried instead of exposing a mixed snapshot.
- Active readers lease their generation. A replaced snapshot is deleted only after its last reader finishes, so an in-flight query cannot switch generations.
- Snapshot directories are created as private system temporary directories. The latest encrypted snapshot can remain until a later call replaces it or the server process exits; retired snapshots are deleted after their readers finish.
- After the first Keychain lookup, the decryption key is kept in server-process memory to avoid repeated Keychain subprocess calls. It is never returned through MCP or written to repository files or logs.
- `snapshot_id` identifies a generation without revealing the database path, key, or message contents. Cache counters are diagnostic metadata only.

## Deployment guidance

- Prefer STDIO for local clients.
- Never expose `--transport streamable-http` directly to the public internet; it has no built-in public authentication.
- Use a private tunnel with explicit access controls for cloud clients.
- Grant Full Disk Access only to a trusted launcher.
- Keep `LINE_MCP_REDACT_SENSITIVE` enabled unless the risk is explicitly accepted.
- Review the connected AI provider's retention and training policies before querying sensitive chats.

## Reporting a vulnerability

Do not open a public issue containing keys, message text, account identifiers, private paths, or reproduction data from a real LINE database.

Use GitHub's private vulnerability reporting for this repository when available. Include:

- affected version or commit;
- macOS and LINE Desktop versions;
- impact and prerequisites;
- a minimal reproduction using synthetic data whenever possible.

If private reporting is unavailable, open a public issue containing no sensitive details and ask the maintainer for a private contact channel.
