# Melvin-LinAIx

> A purely local, open-source AI agent system.  
> **Two versions**: an Ollama-powered model version and a fully standalone vanilla version.  
> No cloud. No external APIs. Your data stays on your machine.

---

## Table of Contents

1. [Features](#features)
2. [Two Versions](#two-versions)
3. [Skills Knowledge Base](#skills-knowledge-base)
4. [Folder Structure](#folder-structure)
5. [Requirements](#requirements)
6. [Quick Start](#quick-start)
7. [Setting up the `melvin` Alias](#setting-up-the-melvin-alias)
8. [Usage — Ollama Version](#usage--ollama-version)
9. [Usage — Vanilla Version](#usage--vanilla-version)
10. [Throttle Controls](#throttle-controls)
11. [Priority Memory](#priority-memory)
12. [Memory Bank](#memory-bank)
13. [Ensemble Mode](#ensemble-mode)
14. [Running Tests](#running-tests)

---

## Features

- **Two flavours** — a full Ollama LLM version (`melvin.py`) and a standalone knowledge-base version (`melvin_vanilla.py`) that needs no AI service.
- **`skills.txt` knowledge base** — structured reference covering punctuation, writing styles, programming languages (MS-DOS through CSS3), mathematics history, astronomy, and core directives.
- **Append-only JSON blockchain** — every conversation is logged in a hash-chained shard file so history can never be silently edited.
- **Per-user memory banks** — each user gets an isolated directory (`memory-bank-username-XXXXXX/`) with up to 1 000 000 entries per shard.
- **Priority memory** — messages containing priority keywords (e.g. "important", "critical") are auto-classified as high-priority and surfaced with `/priority`.
- **Throttle / heat level** — press **1–9** at any prompt to control verbosity; press **ESC** or type **X Y Z X Y Z** to open the interactive control menu.
- **Multi-model ensemble mode** — query all installed models in parallel (`--model all`).
- **Integrity verification** — recompute the full SHA-256 hash chain at any time (`--verify`).
- **Full-text history search** — `/search <term>` inside the chat, or `--history N` from the CLI.
- **Python 3.11+, type-hinted, fully documented.**

---

## Two Versions

| Feature | `melvin.py` (Ollama) | `melvin_vanilla.py` (Vanilla) |
|---|---|---|
| Requires Ollama | ✅ Yes | ❌ No |
| Answers from | LLM inference | `skills.txt` lookup |
| Memory / history | ✅ Same JSON blockchain | ✅ Same JSON blockchain |
| Priority memory | ✅ | ✅ |
| Throttle controls | ✅ 1–9 + menu | ✅ 1–9 + menu |
| Ensemble mode | ✅ Multi-model | N/A |
| Good for | Open-ended questions | Offline / constrained use |

---

## Skills Knowledge Base

`skills.txt` is a plain-text knowledge base loaded at startup.  It is
divided into sections:

| Section | Contents |
|---|---|
| `CORE_DIRECTIVES` | Melvin's persistent rules and priority keywords |
| `LEVEL_SYSTEM` | Levels 1–9 describing Melvin's reasoning capability |
| `PUNCTUATION_AND_WRITING` | Punctuation marks, letter cases, handwriting styles, learning theory |
| `PROGRAMMING_LANGUAGES` | Variables, functions, loops, classes for MS-DOS, Bash, JS, TS, React, PHP, Go, Python, C++, Java, HTML, CSS, SQL, Linux/Windows/macOS commands |
| `MATHEMATICS_AND_NUMBERS` | History of numbers (Egyptian, Babylonian, Greek, Roman, Hindu-Arabic), calculus, π, Einstein's relativity, Newton's gravity |
| `ASTRONOMY` | All 8 planets + dwarf Pluto, their moons and atmospheric compositions, moon landing, Hubble, JWST, black holes |
| `WORD_EXAMPLES` | Common words used correctly in sentences |
| `THROTTLE_SETTINGS` | Heat level 1–9 descriptions and shortcut documentation |

You can extend the knowledge base by adding entries to `skills.txt`
and restarting Melvin (or calling `/reload` in a future version).

---

## Folder Structure

```
Melvin-LinAIx/
├── skills.txt                          ← knowledge base (all versions)
├── memory-bank-exampleuser-ABC123/     ← example user memory bank
│   ├── index.json
│   └── conversations_0000.json
├── src/
│   ├── __init__.py
│   ├── melvin.py           ← Ollama-powered CLI entry point
│   ├── melvin_vanilla.py   ← standalone vanilla CLI entry point
│   ├── config.py           ← paths, Ollama host/port, defaults
│   ├── conversation.py     ← chat loop, throttle, priority detection
│   ├── memory_manager.py   ← JSON blockchain append/verify/search/priority
│   ├── models_manager.py   ← Ollama model list/pull/query
│   ├── skills_manager.py   ← skills.txt loader and searcher
│   ├── user_manager.py     ← per-user directory & identity
│   └── utils.py            ← hashing, sanitization, binary encoding helpers
├── tests/
│   ├── test_memory.py          ← 17 memory unit tests
│   └── test_skills_and_vanilla.py  ← 48 skills/vanilla/priority tests
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

## Usage — Ollama Version

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
| `/heat [1-9]` | Get or set the throttle level |
| `/priority` | Show recent high-priority memories |
| `/quit` or `/exit` | End the session |

---

## Usage — Vanilla Version

The vanilla version requires **no Ollama** and works entirely offline.
It answers questions by searching `skills.txt`.

```
python src/melvin_vanilla.py [OPTIONS]

Options:
  --user NAME      Your identity name (default: "default")
  --heat N         Initial throttle level 1–9 (default: 5)
  --history N      Print last N entries and exit
  --search TERM    Search conversation memory and exit
  --verify         Verify memory hash-chain integrity and exit
  --verbose        Print extra debug information
```

### Examples

```bash
# Start a chat session (no Ollama needed)
python src/melvin_vanilla.py --user alice

# Start with maximum verbosity (heat 9)
python src/melvin_vanilla.py --user alice --heat 9

# Show last 5 history entries
python src/melvin_vanilla.py --user alice --history 5

# Search conversation memory
python src/melvin_vanilla.py --user alice --search python

# Verify memory integrity
python src/melvin_vanilla.py --user alice --verify
```

### What to ask the vanilla version

The vanilla version answers questions based on `skills.txt`.  Type
keywords from any of its knowledge domains:

```
python function          → Python function syntax
bash loop                → Bash for/while loop syntax
javascript class         → JavaScript class syntax
jupiter moons            → Jupiter's moons from ASTRONOMY section
newton gravity           → Newton's gravity formula
css flexbox              → CSS3 Flexbox layout properties
punctuation comma        → What a comma means and when to use it
level system             → Melvin's reasoning level descriptions
core directives          → Melvin's persistent rules
```

### In-chat commands (vanilla)

| Command | Description |
|---|---|
| `/help` | List available commands |
| `/history [N]` | Show last N conversations (default 5) |
| `/search <term>` | Search conversation memory |
| `/skills <query>` | Search the skills knowledge base directly |
| `/verify` | Verify hash-chain integrity |
| `/heat [1-9]` | Get or set the throttle level |
| `/priority` | Show recent high-priority memories |
| `/quit` or `/exit` | End the session |

---

## Throttle Controls

Both versions support a **heat level** (1–9) that controls how much
detail Melvin includes in each response.

| Level | Behaviour |
|---|---|
| 1 | Minimal — one-line answers; low-priority memories stored as binary keywords |
| 2 | Very terse — key facts only |
| 3 | Concise — short paragraphs |
| 4 | Moderately concise |
| 5 | **Default** — balanced explanations |
| 6 | Detailed with examples |
| 7 | Comprehensive with background |
| 8 | Thorough step-by-step |
| 9 | Maximum — full encyclopaedic style |

**Keyboard shortcuts:**

- Type a **single digit 1–9** at the `You:` prompt to change level instantly.
- Type **ESC** (or the literal text `esc`) to open the interactive menu.
- Type the sequence **`x`**, **`y`**, **`z`**, **`x`**, **`y`**, **`z`** (each as a separate input) to open the interactive menu.
- Use `/heat N` as a slash command inside the chat.

---

## Priority Memory

Melvin automatically classifies every message into one of three priority
levels based on keywords loaded from `skills.txt`:

| Level | Trigger words / phrases | Storage behaviour |
|---|---|---|
| **High** (1) | `important`, `priority`, `remember this`, `critical`, `urgent`, `never forget` | Saved normally; surfaced first by `/priority` |
| **Normal** (0) | *(no special keywords)* | Standard storage |
| **Low** (2) | `it's ok if you can't do this` | At heat level 1, stored as compact binary-encoded keywords |

Retrieve high-priority memories with `/priority` or `--priority` flag.

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
  "timestamp":       "2026-01-15T10:30:00+00:00",
  "user_message":    "What is the capital of France?",
  "ai_response":     "Paris.",
  "model_used":      "llama3.2:3b",
  "priority_level":  0,
  "keywords_binary": null,
  "context_hash":    "a3f8…"
}
```

`priority_level` is `0` (normal), `1` (high), or `2` (low).  
`keywords_binary` is set only for low-priority entries at heat level 1.  
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

All 65 tests run offline — no Ollama connection required.

