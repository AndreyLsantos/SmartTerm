# Contributing to SmartTerm

Thanks for taking the time to improve SmartTerm.

## Development Setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_smartterm.py
```

On Linux or macOS, use the equivalent Python command:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m unittest -v test_smartterm.py
```

## Pull Request Guidelines

- Keep changes focused and easy to review.
- Include tests for behavior changes.
- Avoid committing local models, generated files, virtual environments, logs, or
  bundled binary runtimes.
- Do not include secrets, private keys, tokens, real credentials, or private
  machine paths.
- Explain user-visible behavior changes in the pull request description.

## Code Style

SmartTerm is currently a single-file Python app. Prefer small, readable changes
that preserve the existing structure unless a refactor clearly improves the
code.

Use clear names, keep comments useful, and avoid adding dependencies unless
they materially improve the project.

