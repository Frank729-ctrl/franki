# franki

> AI-powered terminal assistant for developers and security professionals.

franki is an open source CLI that brings AI assistance directly to your terminal —
for coding, CEH/pentesting, SOC analysis, and exam prep.
It supports multiple free AI providers with automatic fallback when one hits a rate limit.

## Install

```bash
pip install franki
```

After installing, run:

```bash
franki init
```

## Quick start

```bash
franki                                          # launch interactive REPL
franki "explain this nmap output"
franki @myfile.py "refactor this function"
franki "!nmap -sV 192.168.8.1" "what does this mean"
```

## Skills

Switch skills with `/skill` inside the REPL:

| Skill   | Purpose                              |
|---------|--------------------------------------|
| coding  | Code generation, review, debugging   |
| pentest | CEH-aligned recon, exploitation help |
| soc     | Log analysis, alert triage, MITRE    |
| ceh     | CEH v13 exam prep and quizzes        |

## Providers

franki works with multiple free AI APIs and automatically falls back
when one hits a rate limit:

- **Groq** (free — groq.com)
- **Google Gemini** (free — aistudio.google.com)
- **OpenRouter** (free tier — openrouter.ai)
- **DelkaAI** (coming soon)

Configure keys with:

```bash
franki config
```

## Slash commands

```
/skill <name>    switch skill (coding/pentest/soc/ceh)
/model <name>    switch AI model
/clear           clear conversation
/history         show current session
/help            show all commands
/exit            quit
```

Coming in Phase 2+:

```
/export          save session to markdown
/note <text>     save a finding note
/scope <ip>      set pentest target scope
/quiz            CEH flashcard quiz
/report          generate pentest report from session
/mitre <text>    map behaviour to MITRE ATT&CK
```

## Configuration

franki stores config at `~/.config/franki/config.json`.

```bash
franki config list                   # show all config (keys masked)
franki config set groq.api_key sk-…  # set a value
franki config get active_model       # read a value
franki config reset                  # reset to defaults
franki init                          # re-run setup wizard
```

## License

MIT — built by Frank Dela Nutsukpuie
