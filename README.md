# Melvin-LinAIx

> A purely local, open-source AI agent system powered by [Ollama](https://ollama.com).  
> No cloud. No external APIs. Your data stays on your machine.

---

## Table of Contents

1. [Features](#features)
2. [Folder Structure](#folder-structure)
3. [Requirements](#requirements)
4. [Quick Start](#quick-start)
5. [Setting up the `melvin` Alias](#setting-up-the-melvin-alias)
6. [Usage](#usage)
7. [Memory Bank](#memory-bank)
8. [Ensemble Mode](#ensemble-mode)
9. [Running Tests](#running-tests)

---

## Features

- **Purely local** — all inference runs via Ollama on your hardware.
- **Append-only JSON blockchain** — every conversation is logged in a hash-chained shard file so history can never be silently edited.
- **Per-user memory banks** — each user gets an isolated directory (`memory-bank-username-XXXXXX/`) with up to 1 000 000 entries per shard.
- **Multi-model ensemble mode** — query all installed models in parallel and aggregate their answers (`--model all`).
- **Integrity verification** — recompute the full SHA-256 hash chain at any time (`--verify`).
- **Full-text history search** — `/search <term>` inside the chat, or `--history N` from the CLI.
- **Python 3.11+, type-hinted, fully documented.**

---

## Folder Structure

```
Melvin-LinAIx/
├── memory-bank-exampleuser-ABC123/     ← example user memory bank
│   ├── index.json
│   └── conversations_0000.json
├── src/
│   ├── __init__.py
│   ├── melvin.py           ← CLI entry point
│   ├── config.py           ← paths, Ollama host/port, defaults
│   ├── conversation.py     ← chat loop & ensemble querying
│   ├── memory_manager.py   ← JSON blockchain append/verify/search
│   ├── models_manager.py   ← Ollama model list/pull/query
│   ├── user_manager.py     ← per-user directory & identity
│   └── utils.py            ← hashing, sanitization, timestamps, ensemble helpers
├── tests/
│   └── test_memory.py      ← 17 unit tests
├── README.md
├── requirements.txt
├── setup.sh
└── .gitignore
```

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11+ | Tested on 3.11 and 3.12 |
| [Ollama](https://ollama.com/download) | Must be running (`ollama serve`) |
| pip dependencies | See `requirements.txt` |

---

## Quick Start

### 1. Install Ollama

```bash
# Linux (one-liner)
curl -fsSL https://ollama.com/install.sh | sh

# macOS (Homebrew)
brew install ollama
```

Start the Ollama daemon:

```bash
ollama serve
```

### 2. Pull a model

```bash
ollama pull llama3.2:3b
```

### 3. Clone and set up Melvin-LinAIx

```bash
git clone https://github.com/marcusjenkinscode/Melvin-LinAIx.git
cd Melvin-LinAIx
bash setup.sh
```

`setup.sh` will:
- Check for Python 3.11+
- Create a `.venv` virtual environment
- Install all pip dependencies
- Attempt to pull `llama3.2:3b` via Ollama
- Register the `melvin` alias in `~/.bashrc` / `~/.zshrc`

### 4. Activate the alias

```bash
source ~/.bashrc   # or: source ~/.zshrc
```

---

## Setting up the `melvin` Alias

If you prefer to add the alias manually, add this line to your shell RC file:

```bash
alias melvin='<path-to-repo>/.venv/bin/python <path-to-repo>/src/melvin.py'
```

Or run directly without the alias:

```bash
python src/melvin.py --user yourname
```

---

## Usage

```
melvin [OPTIONS]

Options:
  --user NAME          Your identity name (default: "default")
  --model MODEL        Model to use: a name, comma-separated list, or "all"
                       (default: llama3.2:3b)
  --list-models        List locally installed Ollama models and exit
  --pull MODEL         Pull (download) a model and exit
  --verify             Verify memory hash-chain integrity and exit
  --history N          Print last N conversation entries and exit
  --verbose            Print extra debug information
```

### Examples

```bash
# Start a chat session
melvin --user alice

# Use a specific model
melvin --user alice --model phi3:mini

# Use all installed models (ensemble)
melvin --user alice --model all

# Use two specific models
melvin --user alice --model "llama3.2:3b,phi3:mini"

# List installed models
melvin --list-models

# Pull a new model
melvin --pull qwen2.5:7b

# Verify memory integrity
melvin --verify --user alice

# Show last 10 history entries
melvin --history 10 --user alice
```

### In-chat commands

| Command | Description |
|---|---|
| `/help` | List available commands |
| `/history [N]` | Show last N exchanges (default 5) |
| `/search <term>` | Full-text search across all history |
| `/verify` | Verify hash-chain integrity |
| `/models` | Show active model(s) |
| `/quit` or `/exit` | End the session |

---

## Memory Bank

Each user's conversation history is stored in:

```
memory-bank-<username>-<6-char-code>/
├── index.json                  ← metadata: current file, total count, last updated
├── conversations_0000.json     ← first shard (up to 1 000 000 entries)
└── conversations_0001.json     ← second shard (auto-created when first is full)
```

**Directory naming:** the username is sanitized (lowercased, non-alphanumeric → `_`) and combined with a random 6-character code using a `-` separator — no `+` characters.

### Entry format

```json
{
  "timestamp":    "2026-01-15T10:30:00+00:00",
  "user_message": "What is the capital of France?",
  "ai_response":  "Paris.",
  "model_used":   "llama3.2:3b",
  "context_hash": "a3f8…"
}
```

`context_hash` is `SHA-256(previous_hash + JSON(entry_data))`, forming an append-only chain.

### Override data directory

```bash
export MELVIN_DATA_DIR=/path/to/storage
melvin --user alice
```

---

## Ensemble Mode

When `--model all` (or a comma-separated list) is passed, Melvin queries every selected model **in parallel** using a thread pool. Responses are aggregated by a consensus algorithm: the response whose vocabulary has the highest mean overlap with all other responses is selected and prefixed with a `[Ensemble from: …]` header.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

All 17 tests run offline — no Ollama connection required.

