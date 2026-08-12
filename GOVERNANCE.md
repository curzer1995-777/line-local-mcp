# Governance

LINE Local MCP is an independent, maintainer-led open source project.

## Roles

- **Users** use the software and report problems or ideas.
- **Contributors** submit issues, documentation, tests, or code under the MIT License.
- **Maintainers** review contributions, manage releases, handle security reports, and protect the project's safety boundaries.

The current lead maintainer is [curzer1995-777](https://github.com/curzer1995-777). Additional maintainers may be invited based on sustained, trustworthy contributions.

## Decisions

Discussion happens in public issues and pull requests whenever privacy and security allow. Maintainers seek practical consensus and make the final decision when consensus is not reached.

Changes that add LINE writes, message sending, read-state mutation, credential or session extraction, traffic interception, public unauthenticated exposure, or collection of third-party data are outside the project's charter and will not be accepted.

## Releases

The project follows [Semantic Versioning](https://semver.org/) where practical:

- patch releases contain compatible fixes;
- minor releases add compatible features;
- major releases may change public tools, configuration, or supported data formats.

Because LINE's private local format can change independently, a LINE update may still cause compatibility loss without a project major-version change. Releases are documented in [CHANGELOG.md](CHANGELOG.md).

## Project continuity

If the lead maintainer can no longer maintain the project, stewardship may be transferred to a trusted contributor who agrees to preserve the license, public history, privacy rules, and read-only charter.
