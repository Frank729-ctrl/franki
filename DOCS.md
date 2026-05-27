# Franki — Documentation

> AI-powered terminal assistant for developers and security professionals.

Franki is an open-source CLI that brings full AI agent capabilities to your terminal. It supports multiple AI providers simultaneously, runs an autonomous tool-use agent that can read and write files and execute commands, and ships with purpose-built modes for coding, pentesting, and SOC analysis.

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [CLI Commands](#cli-commands)
4. [Interactive Mode — Slash Commands](#interactive-mode--slash-commands)
5. [Skills (Modes)](#skills-modes)
6. [Agent Tools](#agent-tools)
7. [Providers](#providers)
8. [Configuration Reference](#configuration-reference)
9. [Project Memory — CLAUDE.md / .franki.md](#project-memory--claudemd--frankimd)
10. [Hooks System](#hooks-system)
11. [Extended Thinking](#extended-thinking)
12. [Response Cache](#response-cache)
13. [Per-Tool Permissions](#per-tool-permissions)
14. [MCP Servers](#mcp-servers)
15. [Custom Tools](#custom-tools)
16. [Security Notes](#security-notes)

---

## Installation

```bash
pipx install franki-cli
```

> **Why pipx?** Franki is a CLI tool. `pipx` installs it in an isolated environment and puts the `franki` command on your PATH — no manual venv setup needed.
>
> Install pipx first if needed: `sudo apt install pipx && pipx ensurepath`

Or with pip inside a virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install franki-cli
```

After installing, run the setup wizard to add your first API key:

```bash
franki init
```

---

## Quick Start

```bash
# Start the interactive REPL
franki

# One-shot commands (no REPL)
franki fix app.py "index out of range in process_items"
franki review auth.py
franki explain router.py
franki commit                          # AI-generated commit message from diff
franki cmd "find all TODO comments"    # generate and run a shell command

# Pipe input
cat error.log | franki "what caused this?"

# Auto-accept all tool calls (no prompts)
franki --yes
franki -y
```

---

## CLI Commands

These are run directly from the shell, not inside the REPL.

| Command | Description |
|---|---|
| `franki` | Start the interactive REPL |
| `franki init` | Run the provider setup wizard |
| `franki config` | Edit config from the command line |
| `franki fix <file> [description]` | Analyse and fix a bug in a file |
| `franki review <file>` | Get a senior-engineer code review |
| `franki explain <file>` | Plain-language explanation of a file |
| `franki commit` | AI-generated commit message from `git diff` |
| `franki cmd <description>` | Generate a shell command and optionally run it |
| `franki resume [name]` | Resume a saved session |
| `franki profile list\|save\|load\|delete [name]` | Manage configuration profiles |
| `franki --version` / `franki -V` | Print version |

### Flags

| Flag | Description |
|---|---|
| `--yes` / `-y` | Auto-accept all tool calls without confirmation prompts |

### Pipe support

Franki reads from stdin when it is not a terminal. This lets you pipe file content or command output directly into a question:

```bash
cat server.py | franki "add input validation to every route"
cat access.log | franki "summarise suspicious requests"
git diff | franki "write a commit message"
```

---

## Interactive Mode — Slash Commands

Type `/help` inside the REPL to see the full list. The commands below cover all available functionality.

### Conversation

| Command | Description |
|---|---|
| `/clear` | Clear the current conversation history |
| `/compact` | Summarise the conversation to save tokens |
| `/rewind` | Remove the last exchange (user + assistant) |
| `/retry` | Re-send the last message |
| `/history` | Show the full conversation history |
| `/context` | Show token usage and context-window fill level |
| `/pin <text>` | Pin a reminder into every system prompt |
| `/template <name>` | Use a saved message template |
| `/export` | Save the session as a markdown file |
| `/copy` | Copy the last response to clipboard |
| `/note <text>` | Append a note to your notes file |

### AI & Skills

| Command | Description |
|---|---|
| `/skill <name>` | Switch AI personality/mode (coding, pentest, soc, security) |
| `/skill list` | List all available skills |
| `/model <provider> <model>` | Switch to a different provider or model |
| `/explain <topic>` | Ask for a plain-language explanation |
| `/report` | Generate a detailed written report |
| `/tools` | List and describe available agent tools |
| `/think on\|off\|<N>` | Enable extended thinking with a token budget |

### Coding & Files

| Command | Description |
|---|---|
| `/diff` | Show a diff of all files changed this session |
| `/undo` | Revert the last file write |
| `/autocommit on\|off` | Auto `git commit` after every agent file edit |
| `/cd <path>` | Change the working directory |

### Security

| Command | Description |
|---|---|
| `/scope <targets>` | Set the authorised pentest scope (IPs, domains) |
| `/mitre <technique>` | Look up a MITRE ATT&CK technique |
| `/payload <description>` | Generate an educational payload |

### Search & Memory

| Command | Description |
|---|---|
| `/search <query>` | Run a web search |
| `/remember <text>` | Save a fact to persistent memory |
| `/memories` | List all saved memories |
| `/forget <text\|index>` | Delete a saved memory |

### Cost & Routing

| Command | Description |
|---|---|
| `/cost` | Show token usage and estimated cost for this session |
| `/routing` | Show which providers were used and why |
| `/providers` | List, add, edit, or remove configured providers |
| `/ollama` | List and select local Ollama models |
| `/mcp` | Manage MCP server connections |

### Permissions & Automation

| Command | Description |
|---|---|
| `/auto` | Show auto-accept status |
| `/auto on\|off` | Enable or disable auto-accept mode |
| `/auto notify on\|off` | Toggle task-done desktop notifications |
| `/toolperms list` | Show per-tool permission overrides |
| `/toolperms allow <tool>` | Always allow a specific tool without prompting |
| `/toolperms block <tool>` | Always block a specific tool |
| `/toolperms reset <tool>` | Remove override for a tool |
| `/hooks list` | Show configured hooks |
| `/hooks set <event> <cmd>` | Set a shell hook for a tool event |
| `/hooks unset <event>` | Remove a hook |
| `/hooks clear` | Remove all hooks |
| `/sandbox on\|off` | Block all destructive tools (write, run, patch) |
| `/audit` | Show the recent tool execution log |

### Sessions & Profiles

| Command | Description |
|---|---|
| `/sessions` | List and restore saved sessions |
| `/branch save [name]` | Checkpoint the current conversation |
| `/branch restore <name>` | Revert to a checkpoint |
| `/branch` | List checkpoints |
| `/profile list\|save\|load\|delete [name]` | Manage configuration profiles |

### System

| Command | Description |
|---|---|
| `/init` | Re-run the provider setup wizard |
| `/config` | Open the config editor |
| `/test` | Run the provider connection test |
| `/feedback <text>` | Submit feedback |
| `/help` | Show the help screen |
| `/exit` / `/quit` | End the session |

---

## Skills (Modes)

Skills change the AI's system prompt and behavioural focus. Switch with `/skill <name>` or set a default in config.

| Skill | Focus |
|---|---|
| `coding` | Production-grade code in any language, security flag awareness |
| `pentest` | Authorised testing — recon, scanning, exploitation, wireless, MITRE ATT&CK mapping |
| `soc` | Log analysis, alert triage, TTP mapping, incident report writing |
| `security` | CTF, certifications (CEH/OSCP/eJPT), vuln research, secure coding, threat modelling |

**Auto-detection:** Franki analyses each message for domain keywords and suggests switching skill if ≥ 2 keywords from another mode are detected (e.g. typing "nmap" and "privilege escalation" suggests `pentest`).

**Custom skills:** Create markdown files at `~/.config/franki/skills/<name>.md`. The file content becomes the system prompt for `/skill <name>`.

---

## Agent Tools

When the AI needs to take action, it calls tools. Franki will ask for confirmation before any destructive operation unless auto-accept is enabled or the tool has an "always" permission override.

| Tool | Type | Description |
|---|---|---|
| `read_file` | Read | Read the contents of a file |
| `write_file` | Write | Create or overwrite a file |
| `edit_file` | Write | Replace a specific string inside a file (safer than full rewrite) |
| `apply_patch` | Write | Apply a unified diff patch to a file |
| `run_command` | Execute | Run a shell command and return output |
| `list_directory` | Read | List files and directories at a path |
| `search_files` | Read | Find files by glob pattern |
| `grep_files` | Read | Search file contents with a string or regex |
| `run_background` | Execute | Start a long-running background process |
| `check_background` | Read | Read new output from a background process |
| `stop_background` | Execute | Terminate a background process |
| `list_backgrounds` | Read | List all running background processes |
| `web_search` | Read | Search the web (Tavily or DuckDuckGo) |

**Inline diffs:** Every file write shows a coloured before/after diff in the terminal.

**Parallel writes:** When auto-accept is on and the agent writes multiple files in one turn, writes to different paths execute in parallel.

**Path traversal protection:** Write tools block paths under `/etc/`, `/usr/`, `/bin/`, `/sbin/`, and other system directories.

---

## Providers

Franki supports any OpenAI-compatible API as well as native Anthropic and Cohere APIs. Multiple providers can be configured simultaneously — Franki automatically falls back to the next when one hits a rate limit.

| Provider | Notes |
|---|---|
| **Anthropic** | claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5. Supports prompt caching and extended thinking. |
| **Groq** | Very fast inference. Good free tier. Recommended starting point. |
| **Gemini** | Google's models via OpenAI-compatible endpoint. Long context window. |
| **OpenRouter** | Aggregator — access hundreds of models with one API key, including free-tier options. |
| **Ollama** | Fully local inference. No API key required. Use `/ollama` to pick a model. |
| **Together AI** | Hosted open-source models. |
| **Cerebras** | High-speed inference for Llama models. |
| **Mistral** | Mistral's own models (small, large, etc.). |
| **Cohere** | Command R family. Native Cohere API adapter. |
| **Azure OpenAI** | Azure-hosted OpenAI models. |

### Adding a provider

```bash
franki init          # full wizard
/providers add       # add inside the REPL
```

### Routing strategy

Set in config under `routing_strategy`:

- `capability` (default) — matches provider capabilities to the active skill
- `priority` — strict priority order
- `speed` — fastest providers first
- `cost` — cheapest providers first

Set `local_first: true` to always prefer Ollama/LM Studio before cloud providers.

---

## Configuration Reference

Config is stored at `~/.config/franki/config.json`. Edit with `/config` or `franki config`.

| Field | Default | Description |
|---|---|---|
| `active_provider` | `""` | Currently active provider name |
| `active_skill` | `"coding"` | Default skill on startup |
| `auto_skill` | `true` | Auto-suggest skill switch based on message content |
| `stream` | `true` | Enable streaming responses |
| `auto_accept` | `false` | Skip confirmation prompts for all tool calls |
| `notify_on_done` | `true` | Desktop notification when a multi-step task finishes |
| `auto_copy` | `false` | Auto-copy each response to clipboard |
| `auto_compact` | `true` | Auto-summarise when context window fills |
| `auto_compact_threshold` | `0.70` | Fraction of context window that triggers compaction |
| `auto_compact_messages` | `0` | Compact after N user messages (0 = disabled) |
| `auto_commit` | `false` | Auto `git commit` after each agent file edit |
| `tool_result_max_chars` | `2000` | Trim tool results to this many chars before re-sending (reduces token usage) |
| `max_history_turns` | `0` | Sliding window — only send last N user turns to API (0 = unlimited) |
| `tool_permissions` | `{}` | Per-tool overrides: `{"run_command": "always", "write_file": "ask"}` |
| `hooks` | `{}` | Shell hooks: `{"post_tool.write_file": "black $FRANKI_TOOL"}` |
| `thinking_budget` | `0` | Extended thinking token budget — Anthropic models only (0 = off) |
| `routing_strategy` | `"capability"` | Provider selection strategy |
| `local_first` | `false` | Prefer local providers (Ollama) |
| `tavily_api_key` | `""` | Tavily API key for web search (falls back to DuckDuckGo) |
| `mcp` | `{}` | MCP server definitions |
| `export_path` | `~/Documents/franki-sessions` | Where `/export` saves markdown files |

---

## Project Memory — CLAUDE.md / .franki.md

Franki reads a project context file at startup and injects its content into the system prompt so the AI always knows your project's conventions, architecture, and constraints.

**Supported filenames (checked in order):**
1. `.franki.md` in the current directory or any parent
2. `CLAUDE.md` in the current directory
3. `.claude/CLAUDE.md` in the current directory

Franki walks up the directory tree until it finds one of these files or reaches the home directory. This means a single `.franki.md` in a monorepo root applies to all sub-projects.

**What to put in it:**
```markdown
# My Project

## Stack
Python 3.12, FastAPI, PostgreSQL, Redis

## Conventions
- Use `ruff` for linting — run after every file change
- All API routes in `app/routes/`, models in `app/models/`
- Snake_case everywhere

## Do not touch
- `legacy/` directory — read-only

## Custom tools
<!-- franki-tool: deploy | Deploy to staging | environment: string -->
```

The `.franki.md` file also supports custom tool definitions (see [Custom Tools](#custom-tools)).

---

## Hooks System

Hooks let you run shell commands automatically around tool calls and session events.

### Events

| Event | Triggered |
|---|---|
| `pre_session` | Once at session start (output injected into context) |
| `post_session` | Once when the session ends |
| `pre_tool` | Before every tool call |
| `post_tool` | After every tool call |
| `pre_tool.<name>` | Before a specific tool (e.g. `pre_tool.write_file`) |
| `post_tool.<name>` | After a specific tool (e.g. `post_tool.run_command`) |

### Environment variables

Hooks receive these environment variables:

| Variable | Available in |
|---|---|
| `FRANKI_TOOL` | `pre_tool`, `post_tool`, `pre_tool.*`, `post_tool.*` |
| `FRANKI_ARGS` | `pre_tool`, `pre_tool.*` — tool arguments as JSON |
| `FRANKI_RESULT` | `post_tool`, `post_tool.*` — first 500 chars of tool output |

### Examples

```bash
# Auto-format Python files after every write
/hooks set post_tool.write_file black "$FRANKI_TOOL" 2>/dev/null || true

# Run tests after any file change
/hooks set post_tool.write_file python -m pytest --tb=short -q

# Show git status at the start of every session
/hooks set pre_session git status --short

# Notify when session ends
/hooks set post_session notify-send "Franki session ended"
```

### Manage hooks

```bash
/hooks           # list all hooks
/hooks set <event> <command>
/hooks unset <event>
/hooks clear     # remove all hooks
```

---

## Extended Thinking

Extended thinking lets supported models (Anthropic claude-* family) spend extra tokens on internal reasoning before responding. This significantly improves accuracy on hard problems — multi-step logic, algorithm design, complex debugging.

```bash
/think on          # enable with default budget (8,000 tokens)
/think 16000       # enable with a custom budget
/think off         # disable
/think             # show current status
```

Or set permanently in config:
```json
"thinking_budget": 8000
```

**Notes:**
- Minimum budget: 1,024 tokens
- Thinking tokens are billed as output tokens
- Only available with Anthropic models — other providers accept the parameter but ignore it
- When thinking is on, temperature is forced to 1.0 (Anthropic requirement)

---

## Response Cache

Franki caches AI responses in memory using an LRU cache with a 1-hour TTL. Identical requests (same provider + model + message history) return instantly from cache without an API call.

This is useful during development when you ask the same question repeatedly, or when using `/mitre`, `/quiz`, or `/explain` commands.

Check cache stats:
```bash
/cost    # includes cache hit rate
```

The cache holds up to 128 entries and expires entries after 1 hour. It is in-memory only — cleared when the process exits.

---

## Per-Tool Permissions

By default, Franki asks for confirmation before any write or execute tool call. You can override this per tool.

### Permission levels

| Level | Behaviour |
|---|---|
| `always` | Run without any confirmation prompt |
| `ask` | Always ask (default for NEEDS_CONFIRM tools) |
| `never` | Block completely — agent is told the tool is unavailable |

### Manage permissions

```bash
/toolperms list
/toolperms allow run_command       # never ask for run_command
/toolperms allow write_file        # never ask for writes
/toolperms block apply_patch       # always block apply_patch
/toolperms reset write_file        # back to default (ask)
```

Or set in config:
```json
"tool_permissions": {
  "read_file": "always",
  "run_command": "always",
  "write_file": "ask",
  "apply_patch": "never"
}
```

**Tip:** Combine with `auto_accept: true` for fully unattended agent runs, and use `never` to prevent specific tools even in that mode.

---

## MCP Servers

Franki supports the Model Context Protocol (MCP). MCP servers expose additional tools that the AI agent can call — for example, a database query tool, a Jira integration, or a custom internal API.

### Adding an MCP server

```bash
/mcp add mydb --command "python -m mydb_server"
/mcp add jira --command "npx @jira/mcp-server" --env JIRA_TOKEN=your_token
```

Or in config:
```json
"mcp": {
  "mydb": {
    "command": "python -m mydb_server",
    "args": [],
    "env": {"DB_URL": "postgres://..."},
    "enabled": true
  }
}
```

### Managing MCP servers

```bash
/mcp list               # list all configured servers
/mcp enable <name>
/mcp disable <name>
/mcp remove <name>
```

MCP tools appear in the environment block and are described to the model automatically on every request.

---

## Custom Tools

Define project-specific tools in your `.franki.md` using HTML comment directives. These tools call shell commands and return their output to the agent.

**Syntax:**
```
<!-- franki-tool: <name> | <description> | <param_name>: <param_description>, ... -->
```

**Example `.franki.md`:**
```markdown
<!-- franki-tool: deploy | Deploy the app to the staging environment | environment: Target environment (staging or production) -->
<!-- franki-tool: run_tests | Run the test suite for a specific module | module: Python module path to test -->
<!-- franki-tool: lint | Run the linter on a file | path: File path to lint -->
```

Custom tools are executed as shell commands with the parameter values as environment variables. Manage at runtime with `/toolperms allow|block <tool_name>`.

---

## Security Notes

### Scope enforcement (pentest mode)

When using the `pentest` skill, set a scope to ensure the AI only targets authorised systems:

```bash
/scope 192.168.1.0/24, example.com
```

The scope is injected into the system prompt as a hard constraint. The AI will refuse actions targeting out-of-scope systems.

### Sandbox mode

Sandbox mode blocks all destructive tools — no file writes, no command execution:

```bash
/sandbox on
```

Use this when you want to ask questions about a codebase without any risk of changes.

### Path traversal protection

Write tools (`write_file`, `edit_file`, `apply_patch`) reject paths under system directories: `/etc/`, `/usr/`, `/bin/`, `/sbin/`, `/lib/`, `/proc/`, `/sys/`, and others.

### API key storage

API keys are stored in `~/.config/franki/config.json`. This file is only readable by your user account. For production or team use, keys can also be set via environment variables — these take precedence over the config file:

```bash
export GROQ_API_KEY=gsk_...
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=...
export OPENROUTER_API_KEY=...
```

### Audit log

Every tool call is logged. View recent activity:

```bash
/audit
```

---

## File Structure

```
franki/
├── franki/
│   ├── agent/
│   │   ├── loop.py          # Agent execution loop — tool use, permissions, hooks
│   │   └── tools.py         # Tool schemas and implementations
│   ├── providers/
│   │   ├── generic.py       # OpenAI-compatible adapter (Groq, Gemini, etc.)
│   │   ├── anthropic.py     # Native Anthropic Messages API adapter
│   │   ├── cohere.py        # Native Cohere API adapter
│   │   └── azure.py         # Azure OpenAI adapter
│   ├── cache.py             # LRU response cache
│   ├── commands.py          # All slash command handlers
│   ├── config.py            # Configuration model and loader
│   ├── environment.py       # Runtime environment block (injected into system prompt)
│   ├── hooks.py             # Pre/post tool shell hooks
│   ├── main.py              # Entry point, REPL, toolbar
│   ├── project_context.py   # .franki.md / CLAUDE.md loader
│   ├── router.py            # Provider routing and fallback
│   ├── session.py           # Conversation state management
│   ├── skills.py            # Skill definitions and auto-detection
│   └── utils/ai.py          # ask_ai(), stream_to_terminal(), cache_stats()
└── tests/                   # pytest test suite (1100+ tests)
```

---

## License

MIT
