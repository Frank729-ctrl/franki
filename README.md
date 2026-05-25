# franki

> AI-powered terminal assistant for developers and security professionals.

franki is an open source CLI that brings AI assistance directly to your terminal —
for coding, CEH/pentesting, SOC analysis, and exam prep.
It supports multiple free AI providers with automatic fallback when one hits a rate limit.

## Install

```bash
pip install franki-cli
```

After installing, run the setup wizard to add your API keys:

```bash
franki init
```

## Quick start

```bash
franki                                    # launch interactive REPL
franki --version                          # print version
franki init                               # re-run setup wizard
franki config list                        # show config (keys masked)
```

Inside the REPL:

```bash
explain how TCP handshakes work           # plain message
@myfile.py refactor this function         # inject a file into context
!nmap -sV 192.168.1.1                     # run a shell command and analyse output
/skill pentest                            # switch skill
/help                                     # show all commands
```

## Skills

| Skill   | Purpose                                        |
|---------|------------------------------------------------|
| coding  | Code generation, review, debugging             |
| pentest | CEH-aligned recon, exploitation, reporting     |
| soc     | Log analysis, alert triage, incident response  |
| ceh     | CEH v13 exam prep and flashcard quizzes        |

## Providers

franki works with multiple free AI APIs and automatically falls back when one hits a rate limit:

| Provider | Free tier | Get key |
|----------|-----------|---------|
| Groq | Yes | groq.com |
| Google Gemini | Yes | aistudio.google.com |
| OpenRouter | Free models available | openrouter.ai |
| DelkaAI | Self-hosted option | — |

Configure keys:

```bash
franki config set groq.api_key <key>
franki config set gemini.api_key <key>
franki config set openrouter.api_key <key>
```

## Commands

### Conversation
| Command | Description |
|---------|-------------|
| `/clear` | Clear conversation history |
| `/compact` | Summarise history to save context |
| `/rewind` | Undo the last exchange |
| `/history` | Show current session log |
| `/context` | Show model, memory, tokens, search status |

### Output
| Command | Description |
|---------|-------------|
| `/export` | Save session to Obsidian vault as markdown |
| `/copy` | Copy last AI response to clipboard |
| `/note <text>` | Save a timestamped finding note |
| `/report` | Generate a pentest or SOC report from the session |
| `/search <query>` | Web search via Tavily — injects results into context |

### Navigation
| Command | Description |
|---------|-------------|
| `/skill <name>` | Switch skill: coding / pentest / soc / ceh |
| `/model <name>` | Switch AI model |
| `/scope <ip/cidr>` | Set pentest target scope |
| `/scope clear` | Remove active scope |

### CEH / Security
| Command | Description |
|---------|-------------|
| `/quiz` | CEH v13 flashcard quiz mode |
| `/mitre <behaviour>` | Map a behaviour to MITRE ATT&CK |
| `/payload <type>` | Suggest payloads for an attack type |
| `/tools <task>` | Suggest the right tools for a task |
| `/explain <tool>` | Explain a tool, its flags, and usage |

### Memory
| Command | Description |
|---------|-------------|
| `/remember <fact>` | Save a fact to long-term memory |
| `/memories` | List all saved memory, scopes, skill usage, notes |
| `/forget <id\|all>` | Remove a fact by id, or clear all memory |

### System
| Command | Description |
|---------|-------------|
| `/connect` | Show connection mode (delkaai / direct) |
| `/connect delkaai` | Switch to DelkaAI backend |
| `/connect direct` | Switch back to direct providers |
| `/init` | Re-run the API key setup wizard |
| `/config` | Open the config editor |
| `/providers` | Show provider status and configuration |
| `/help` | Show all commands |
| `/quit` | Exit (prompts to save session) |

## Auto-search

franki automatically runs a web search and injects the results before the AI responds
when your message contains keywords like `latest`, `current`, `today`, `news`,
or a CVE ID (`CVE-XXXX-XXXXX`).

Requires a Tavily API key (`TAVILY_API_KEY`) or a connected DelkaAI backend.

## Long-term memory

franki remembers things across sessions:

```bash
/remember I use Python 3.11 and FastAPI
/remember my pentest lab is 10.10.10.0/24
/memories        # view everything stored
/forget 2        # remove entry #2
```

Stored facts, recent pentest scopes, skill usage, and notes are automatically
injected into the system prompt at the start of every session.

## Configuration

Config is stored at `~/.config/franki/config.json`.

```bash
franki config list                    # show all config (keys masked)
franki config set groq.api_key <key>  # set a value
franki config get active_model        # read a value
franki config reset                   # reset to defaults
```

## License

MIT — see [LICENSE](LICENSE)
