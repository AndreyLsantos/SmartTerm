# SmartTerm

**SmartTerm** is an AI-assisted terminal for PowerShell, Bash, and Windows CMD.
It lets you run real shell commands while getting full-command suggestions,
project-aware search helpers, local AI answers, optional web research, and
approval prompts before risky commands are executed.

SmartTerm is built around one file, `smartterm.py`, and can run with:

- Local autocomplete and command suggestions with no AI model.
- A local `llama.cpp` server using a `.gguf` model.
- Ollama, if you prefer to use an existing Ollama server.
- Optional read-only web search for current information.

SmartTerm is open source under the [MIT License](LICENSE).

---

## What SmartTerm Does

SmartTerm turns your terminal into a guided command workspace:

- Suggests complete commands as you type.
- Understands common intents in English and Portuguese, such as `kill`,
  `porta`, `disk`, `service`, `wifi`, `zip`, and `find file`.
- Indexes your project and suggests searches based on files, symbols, and
  recent command history.
- Lets you ask questions with `?` or `/ask`.
- Can propose a command and ask for approval before running it.
- Protects you from accidental destructive actions with confirmation prompts.
- Keeps investigation context so follow-up questions have useful background.
- Supports temporary knowledge modules from `.txt` or `.md` files.

---

## Requirements

- Windows, Linux, or another system with Python support.
- Python **3.11 or newer**.
- Python dependencies listed in `requirements.txt`:
  - `prompt_toolkit`
  - `httpx`
- Optional but recommended:
  - `rg` / ripgrep for fast project search.
  - Git for Windows, which provides tools such as `grep`, `head`, and `tail`.
  - A local `.gguf` model if you want AI features through `llama.cpp`.
  - A `llama.cpp` server build, or Ollama if you want to use `--ollama`.

The source repository does not need to include models, virtual environments, or
`llama.cpp` binaries. If you keep a local `llama\llama-server.exe` folder next
to `smartterm.py`, SmartTerm can use it automatically. You can also point to a
server binary with `--llama-server`.

---

## Open Source Repository Notes

This repository is prepared to be published as a source-first GitHub project.

Included in the repository:

- SmartTerm source code.
- Tests.
- Example project files.
- Documentation.
- MIT license.
- Contribution and security guidelines.
- GitHub issue, pull request, and test workflow templates.

Not included in Git:

- `.venv/`
- `__pycache__/`
- generated test output
- local `.gguf` models
- local `llama.cpp` runtime binaries in `llama/`
- secrets or machine-local configuration

Project repository:

```text
https://github.com/AndreyLsantos/SmartTerm
```

---

## Installation

Open PowerShell in the SmartTerm folder:

```powershell
cd C:\Users\pand4\Desktop\smartterm
```

Create a virtual environment:

```powershell
py -3 -m venv .venv
```

Install the dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

You can then start SmartTerm through the included launcher:

```powershell
.\smartterm.cmd "D:\path\to\your\project"
```

---

## First Run With Local AI

To use a local `llama.cpp` server, provide a `.gguf` model:

```powershell
.\smartterm.cmd "D:\path\to\your\project" --model-path "C:\models\qwen3-4b.gguf"
```

SmartTerm saves the model path for later sessions. After the first run, you can
usually start it with only the project path:

```powershell
.\smartterm.cmd "D:\path\to\your\project"
```

Inside SmartTerm, you can switch models at any time:

```text
/model C:\models\another-model.gguf
```

If no model is configured, SmartTerm still works as a terminal with local
suggestions, history, project indexing, and command safety prompts. Only AI
answers and AI-generated suggestions are unavailable.

---

## Start Without AI

Use `--no-ai` when you want SmartTerm to behave as a smart terminal without
loading any model:

```powershell
.\smartterm.cmd "D:\path\to\your\project" --no-ai
```

This is useful when you only want local command suggestions and project-aware
search helpers.

---

## Start With Ollama

If you already run Ollama locally, start SmartTerm with:

```powershell
.\smartterm.cmd "D:\path\to\your\project" --ollama --model qwen3:4b
```

By default, SmartTerm connects to:

```text
http://127.0.0.1:11434
```

You can override that with:

```powershell
.\smartterm.cmd "D:\path\to\your\project" --ollama --model qwen3:4b --ollama-url http://127.0.0.1:11434
```

---

## The Interface

SmartTerm opens as a terminal chat interface:

- The conversation and command output stay in the upper area.
- The command box stays fixed at the bottom.
- Suggested text appears as ghost text.
- Status, hints, and confirmation prompts appear near the input area.

Press **Enter** to run only what you typed. Ghost text is never executed unless
you explicitly accept it.

---

## Essential Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Tab` or `Right Arrow` | Accept the full suggested command |
| `Ctrl+Right Arrow` | Accept only the next suggested word |
| `Alt+Down` / `Alt+Up` | Cycle through suggestions |
| `Up` / `Down` with popup open | Move inside the completion popup |
| `Tab` or `Enter` with popup open | Apply the selected popup item |
| `Esc` | Close popup or clear text selection |
| `Enter` | Execute the typed command |
| `? question` | Ask the AI |
| `PgUp` / `PgDn` | Scroll the conversation |
| Mouse wheel | Scroll the conversation |
| `Ctrl+End` | Return to the latest output |
| Drag mouse in conversation | Select text |
| `Ctrl+C` with selected text | Copy the selection |
| `Ctrl+C` without selection | Interrupt command or AI response, or clear input |
| `Ctrl+V`, `Shift+Insert`, right click | Paste into the command box |
| `F4` | Toggle native console selection mode |
| `F2` | Toggle AI on or off |

---

## Running Commands

Type normal shell commands and press **Enter**:

```text
Get-ChildItem
```

```text
rg -n "ChatContent" Cliente/VN/src
```

```text
git status
```

SmartTerm supports PowerShell, Bash, and CMD. Choose a shell at startup:

```powershell
.\smartterm.cmd "D:\path\to\project" --shell powershell
```

```powershell
.\smartterm.cmd "D:\path\to\project" --shell bash
```

```powershell
.\smartterm.cmd "D:\path\to\project" --shell cmd
```

You can also switch shell during a session:

```text
/shell powershell
/shell bash
/shell cmd
```

Each command runs in a new subprocess. Directory changes are handled by
SmartTerm, so `cd` and `/cd` update the active working directory. Shell
variables and aliases created inside one command do not persist into the next
command.

---

## Command Suggestions

SmartTerm suggests commands from several sources:

- Your recent command history.
- Files and symbols found in the indexed project.
- Built-in investigation templates.
- Installed programs and shell commands.
- PowerShell cmdlets and parameters.
- Live process and service lists.
- AI completions, when AI is enabled and ready.

Examples:

```text
kill
```

SmartTerm may suggest process-ending commands appropriate to the active shell.

```text
porta
```

SmartTerm may suggest commands that inspect listening ports or find which
process owns a port.

```text
Stop-Process -Name
```

SmartTerm can show live process names.

```text
Stop-Service -Name
```

SmartTerm can show services, with running services prioritized.

Press `Tab` on an empty command line to open common commands and investigation
next steps.

---

## Asking the AI

Use `?` or `/ask`:

```text
? what does this error mean?
```

```text
/ask find where ChatContent is created
```

The AI can:

- Answer a question.
- Explain recent command output.
- Suggest a command.
- Decide to perform read-only web research when the question needs current
  information.

When the AI suggests a command, SmartTerm shows it first and asks before
running it:

```text
/ask find the Wamp folder on this computer

AI> Suggested command (powershell):
Get-ChildItem -Path C:\ -Directory -Recurse -Filter "wamp*" -ErrorAction SilentlyContinue |
Select-Object -First 20 -ExpandProperty FullName

Run this command now?
Execute? [y/N]
```

Only approve commands you understand.

---

## Command Safety

SmartTerm includes a safety classifier for commands.

Read-only commands, such as simple searches and listing commands, usually run
immediately:

```text
Get-ChildItem | Select-String ChatContent
```

Commands that may modify files, stop services, kill processes, write output, or
run unknown code ask for confirmation:

```text
Remove-Item -Recurse -Force build
```

The confirmation prompt appears in the command box. Type `y` to execute or
anything else to cancel.

Important: this is a practical safety check, not a sandbox. SmartTerm helps you
notice risky commands, but the commands still run on your machine.

---

## Web Research

SmartTerm can search the web when a question mentions the internet, a website,
a URL, news, or current information:

```text
/ask search the web for the current Python version
```

```text
/ask open https://example.com and summarize the page
```

```text
/ask bring today's news about Python
```

Web access is read-only. SmartTerm does not log in, submit forms, make
purchases, publish content, or modify websites.

SmartTerm also blocks unsafe web targets such as:

- `localhost`
- private network addresses
- URLs containing credentials

Disable web access for a session:

```powershell
.\smartterm.cmd "D:\path\to\project" --no-web
```

Or toggle it inside SmartTerm:

```text
/web off
/web on
```

---

## Temporary Knowledge Modules

Use a module when you want the AI to answer from a specific `.txt` or `.md`
file, or from a folder containing text files:

```text
/modulo C:\studies\sql-injection.md
```

Then ask:

```text
? what are the main types of SQL injection and how can I prevent them?
```

SmartTerm does not train the model. Instead, it splits the material into local
chunks and retrieves the most relevant parts for each question. Answers cite
sources like:

```text
[1] sql-injection.md:12-28
```

Unload the module:

```text
/modulo off
```

Modules are session-only and are not saved after SmartTerm exits.

---

## Internal Commands

| Command | Purpose |
| --- | --- |
| `/help` | Show help inside SmartTerm |
| `/ask <question>` | Ask the AI |
| `/explain` | Ask the AI to explain the latest command output |
| `/why` | Show where the latest suggestion came from |
| `/context` | Show project, shell, history, and investigation context |
| `/clear-context` | Clear investigation context but keep command history |
| `/files` | Show indexed files and symbol information |
| `/history` | Show recent command history |
| `/shell powershell\|bash\|cmd` | Switch shell |
| `/model [file.gguf]` | Show or change the local AI model |
| `/project [folder]` | Show or change the project root |
| `/cd [folder]` | Change directory inside the current project |
| `/reindex` | Rebuild the project index |
| `/ai on\|off` | Enable or disable AI |
| `/web on\|off` | Enable or disable web access |
| `/warmup` | Start model loading or reconnection |
| `/cancel` | Cancel the current AI response |
| `/modulo <file-or-folder>` | Load a temporary knowledge module |
| `/modulo off` | Unload the active knowledge module |
| `/exit` | Exit SmartTerm |

---

## Useful Startup Options

| Option | Description |
| --- | --- |
| `project` | Project root to open |
| `--shell powershell\|bash\|cmd` | Choose the shell |
| `--shell-executable <path>` | Use a specific shell executable |
| `--model-path <file.gguf>` | Use a local `.gguf` model with `llama.cpp` |
| `--llama-server <path>` | Use a specific `llama-server` executable |
| `--gpu-layers <number>` | GPU layer count; `-1` is automatic, `0` is CPU-only |
| `--ollama` | Use Ollama instead of local `llama.cpp` |
| `--model <name>` | Ollama model name, for example `qwen3:4b` |
| `--ollama-url <url>` | Ollama server URL |
| `--no-ai` | Disable AI |
| `--no-web` | Disable web research |
| `--completion-timeout <seconds>` | AI suggestion timeout |
| `--context-chars <number>` | Approximate character budget for AI context |
| `--num-ctx <number>` | Token context requested from Ollama |
| `--max-files <number>` | Maximum project files to index |
| `--state-dir <folder>` | Folder for SmartTerm state |
| `--version` | Print the SmartTerm version |

Show CLI help:

```powershell
.\.venv\Scripts\python.exe .\smartterm.py --help
```

---

## Local AI Notes

When using local `llama.cpp`, SmartTerm:

- Starts `llama-server` in the background.
- Binds it to `127.0.0.1`.
- Uses a random API key.
- Chooses a free local port.
- Stops the server when SmartTerm exits.

The first model load may take longer because Vulkan shaders can be compiled.
After that, suggestions are usually faster.

GPU behavior:

- `--gpu-layers -1` lets `llama.cpp` choose based on available VRAM.
- `--gpu-layers 0` forces CPU-only mode.

The llama server log is stored at:

```text
%LOCALAPPDATA%\SmartTerm\llama-server.log
```

If another program is using GPU memory, fewer layers may fit on the GPU and AI
responses may be slower.

---

## Project Indexing

SmartTerm indexes source files and text files from the project root. The index
helps with:

- File suggestions.
- Symbol suggestions.
- Search templates.
- AI context about the current project.
- Follow-up investigation steps.

Generated folders and sensitive files are skipped, including common directories
such as `.git`, `.venv`, `node_modules`, `bin`, `build`, `dist`, `.ssh`, `.aws`,
`.azure`, and `.kube`.

Rebuild the index manually:

```text
/reindex
```

Show indexed files:

```text
/files
```

---

## State and Privacy

SmartTerm stores local state in:

```text
%LOCALAPPDATA%\SmartTerm
```

Command history is stored in:

```text
%LOCALAPPDATA%\SmartTerm\smartterm.sqlite3
```

This database is not encrypted. Do not paste passwords, tokens, private keys,
or other secrets into SmartTerm.

SmartTerm tries to avoid saving obviously sensitive commands, and it skips
common secret files during indexing, but you should still treat the terminal as
a normal local shell with local history.

---

## Limitations

- Each command runs in a new subprocess.
- Variables and aliases created by one command do not persist.
- Interactive programs such as `vim`, `ssh`, or prompts like `Read-Host` are
  better used in a normal terminal.
- Project indexing is heuristic. It helps you investigate, but it does not prove
  that something is unused or absent.
- Safety classification is approximate. Review commands before approving them.
- Web research is read-only and limited to public pages.

---

## Testing

Run the offline regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_smartterm.py
```

Optionally test a real local llama server with a `.gguf` model:

```powershell
$env:SMARTTERM_TEST_GGUF="C:\models\model.gguf"
.\.venv\Scripts\python.exe -m unittest -v test_smartterm.py
```

---

## Quick Examples

Open a project without AI:

```powershell
.\smartterm.cmd "D:\Pensando\xjOL" --no-ai
```

Open a project with local AI:

```powershell
.\smartterm.cmd "D:\Pensando\xjOL" --model-path "C:\models\qwen3-4b.gguf"
```

Ask a question:

```text
? where is ChatContent created?
```

Ask for a command:

```text
/ask show the largest files in this project
```

Search with project-aware suggestions:

```text
rg -n "ChatContent"
```

Switch to Bash:

```text
/shell bash
```

Disable web access:

```text
/web off
```

Exit:

```text
/exit
```
