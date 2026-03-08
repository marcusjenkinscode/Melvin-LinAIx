#!/usr/bin/env bash
# setup.sh — Bootstrap Melvin-LinAIx: install dependencies, optionally set up Ollama, and register the `melvin` alias.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
MELVIN_ENTRY="${SCRIPT_DIR}/src/melvin.py"

echo "=== Melvin-LinAIx Setup ==="
echo ""

# ── 1. Python version check ─────────────────────────────────────────────────
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11) ]]; then
    echo "ERROR: Python 3.11+ is required. Found Python $PY_VERSION."
    exit 1
fi
echo "[✓] Python $PY_VERSION detected."

# ── 2. Create virtual environment (optional) ────────────────────────────────
if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
    echo "[*] Creating virtual environment at .venv ..."
    "$PYTHON" -m venv "${SCRIPT_DIR}/.venv"
fi

VENV_PY="${SCRIPT_DIR}/.venv/bin/python"
VENV_PIP="${SCRIPT_DIR}/.venv/bin/pip"

echo "[*] Upgrading pip ..."
"$VENV_PIP" install --quiet --upgrade pip

# ── 3. Install Python dependencies ──────────────────────────────────────────
echo "[*] Installing Python dependencies from requirements.txt ..."
"$VENV_PIP" install --quiet -r "${SCRIPT_DIR}/requirements.txt"
echo "[✓] Python dependencies installed."

# ── 4. Ollama installation check ────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    echo "[✓] Ollama is already installed: $(ollama --version 2>/dev/null || echo 'unknown version')"
else
    echo "[*] Ollama not found. Attempting to install ..."
    if [[ "$(uname -s)" == "Linux" ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
        echo "[✓] Ollama installed."
    elif [[ "$(uname -s)" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            brew install ollama
            echo "[✓] Ollama installed via Homebrew."
        else
            echo "WARNING: Homebrew not found. Please install Ollama manually from https://ollama.com/download"
        fi
    else
        echo "WARNING: Unsupported OS for automatic Ollama install. Visit https://ollama.com/download"
    fi
fi

# ── 5. Pull default models (optional) ────────────────────────────────────────
if command -v ollama &>/dev/null; then
    if ollama list &>/dev/null 2>&1; then
        echo "[*] Pulling default model llama3.2:3b (this may take a while) ..."
        ollama pull llama3.2:3b || echo "WARNING: Could not pull llama3.2:3b. Start Ollama first and run: ollama pull llama3.2:3b"
    else
        echo "WARNING: Ollama daemon doesn't appear to be running. Start it with: ollama serve"
        echo "         Then pull models with:  ollama pull llama3.2:3b"
    fi
fi

# ── 6. Register 'melvin' alias ───────────────────────────────────────────────
ALIAS_CMD="alias melvin='${VENV_PY} ${MELVIN_ENTRY}'"

register_alias() {
    local RC_FILE="$1"
    if [[ -f "$RC_FILE" ]]; then
        if grep -q "alias melvin=" "$RC_FILE"; then
            echo "[✓] 'melvin' alias already present in $RC_FILE"
        else
            echo "" >> "$RC_FILE"
            echo "# Melvin-LinAIx alias" >> "$RC_FILE"
            echo "$ALIAS_CMD" >> "$RC_FILE"
            echo "[✓] 'melvin' alias added to $RC_FILE"
        fi
    fi
}

register_alias "$HOME/.bashrc"
register_alias "$HOME/.zshrc"
register_alias "$HOME/.bash_profile"

echo ""
echo "=== Setup Complete ==="
echo "To activate the alias in the current shell, run:"
echo "    source ~/.bashrc   # or ~/.zshrc"
echo ""
echo "Then start Melvin with:"
echo "    melvin --help"
echo "    melvin --user yourname"
echo "    melvin --user yourname --model all"
echo ""
