# Security Policy

## Supported Versions

Security fixes are handled for the latest public version of SmartTerm.

## Reporting a Vulnerability

Please report security issues privately before opening a public issue.

If this project is hosted on GitHub, use GitHub's private vulnerability
reporting feature when available. Otherwise, contact the maintainer directly.

Include:

- A short description of the issue.
- Steps to reproduce it.
- The operating system and shell used.
- Whether AI, web research, Ollama, or local `llama.cpp` mode was enabled.

## Scope

SmartTerm runs real shell commands on the user's machine. Its confirmation
prompts and command classifier are safety aids, not a sandbox.

Please treat these areas as security-sensitive:

- Command approval and safety classification.
- Secret redaction and history storage.
- Web URL validation and read-only web research.
- Local AI server binding, ports, and API keys.
- Project indexing exclusions for secret files.
