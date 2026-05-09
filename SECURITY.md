# Security Policy

macOS Hermes Agent Pets is local-first. It does not require a hosted service, but it does interact with local Hermes commands, the filesystem, and a native overlay process.

## Supported Versions

Security fixes target the current `main` branch until formal releases are tagged.

## Reporting a Vulnerability

Please do not open a public issue for a vulnerability involving command execution, destructive file operations, approval bypasses, or local data exposure.

Report privately to the repository owner first. Include:

- A concise description of the issue.
- Exact reproduction steps.
- macOS version, Hermes version, and install method.
- Whether the issue affects `/pet` commands, deletion approvals, overlay launch, plugin install, or custom pet packaging.

## Security-Sensitive Areas

- Deletion approval and cancel behavior.
- Dangerous command blocking.
- Hermes hook input parsing.
- Plugin install paths.
- Overlay launch arguments.
- Custom pet import and validation.
- Any future network, dashboard, or remote-control feature.

## Local Data

The plugin stores local state under `~/.hermes/hermes-pet-agent` when installed. Do not include private state files, local paths, screenshots with sensitive terminal content, or personal character assets in bug reports unless they are necessary and safe to share.
