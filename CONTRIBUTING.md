# Contributing to franki

Thanks for your interest. Here is how to get started.

## Setup

```bash
git clone https://github.com/Frank729-ctrl/franki.git
cd franki
python -m venv .venv && source .venv/bin/activate
pip install -e .
franki init
```

## Rules

- One file per component — never bundle multiple classes into one file
- No hardcoded API keys anywhere
- New slash commands go in `franki/commands.py` and must appear in `/help`
- New providers go in `franki/providers/` and must be wired into `router.py`
- All AI calls must use the router — never call a provider directly from a command

## Running tests

```bash
pytest tests/
```

## Submitting

Open a PR against `main`. Fill in the PR template.
