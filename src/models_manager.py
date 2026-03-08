"""
models_manager.py — Ollama model lifecycle management.

Responsibilities
----------------
* Detect whether the Ollama daemon is reachable.
* List locally installed models.
* Pull (download) one or more models.
* Provide a thin query interface used by conversation.py.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

try:
    import ollama  # type: ignore[import-untyped]
except ImportError:
    ollama = None  # type: ignore[assignment]

from src.config import DEFAULT_MODEL, OLLAMA_BASE_URL, RECOMMENDED_MODELS


class ModelsManager:
    """Manage Ollama models for Melvin-LinAIx.

    Args:
        host: Ollama API base URL (defaults to ``config.OLLAMA_BASE_URL``).
    """

    def __init__(self, host: str = OLLAMA_BASE_URL) -> None:
        self.host = host
        self._client: Optional[Any] = self._make_client()

    # ── Public API ────────────────────────────────────────────────────────────

    def is_ollama_available(self) -> bool:
        """Return ``True`` if the Ollama daemon is reachable."""
        if ollama is None:
            return False
        try:
            self._list_raw()
            return True
        except Exception:
            return False

    def assert_ollama_running(self) -> None:
        """Raise a ``RuntimeError`` if Ollama is not reachable."""
        if not self.is_ollama_available():
            raise RuntimeError(
                "Ollama is not running or not reachable at "
                f"{self.host}. "
                "Start it with:  ollama serve"
            )

    def list_installed(self) -> list[str]:
        """Return a list of locally installed model names.

        Returns:
            List of model name strings (e.g. ``["llama3.2:3b", "phi3:mini"]``).
        """
        try:
            raw = self._list_raw()
        except Exception as exc:
            print(f"[WARN] Could not list models: {exc}", file=sys.stderr)
            return []

        models = []
        for m in raw.get("models", []):
            name = m.get("name") or m.get("model")
            if name:
                models.append(name)
        return models

    def pull(self, model_name: str, stream: bool = True) -> None:
        """Pull (download) *model_name* from the Ollama registry.

        Args:
            model_name: Model identifier (e.g. ``"llama3.2:3b"``).
            stream:     When ``True`` (default), print progress to stdout.

        Raises:
            RuntimeError: If Ollama is not available.
        """
        self.assert_ollama_running()
        print(f"[*] Pulling model: {model_name} …")
        if stream:
            for progress in ollama.pull(model_name, stream=True, host=self.host):  # type: ignore[union-attr]
                status = progress.get("status", "")
                if status:
                    print(f"    {status}", end="\r", flush=True)
            print()
        else:
            ollama.pull(model_name, host=self.host)  # type: ignore[union-attr]
        print(f"[✓] Model {model_name} is ready.")

    def pull_recommended(self) -> None:
        """Pull all models listed in ``config.RECOMMENDED_MODELS``."""
        for model in RECOMMENDED_MODELS:
            self.pull(model)

    def select_model(self, model_arg: str) -> list[str]:
        """Resolve the ``--model`` CLI argument to a list of model names.

        Special values
        ~~~~~~~~~~~~~~
        ``"all"``
            Use every installed model (ensemble mode).

        A comma-separated string (e.g. ``"llama3.2:3b,phi3:mini"``)
            Use exactly those models.

        A single model name
            Use that model only; fall back to ``DEFAULT_MODEL`` if it
            is not installed.

        Args:
            model_arg: Raw ``--model`` value from the CLI.

        Returns:
            Non-empty list of model name strings.

        Raises:
            RuntimeError: If Ollama is not reachable.
        """
        self.assert_ollama_running()
        installed = self.list_installed()

        if model_arg.lower() == "all":
            if not installed:
                print(
                    "[WARN] No models installed. Falling back to default: "
                    f"{DEFAULT_MODEL}",
                    file=sys.stderr,
                )
                return [DEFAULT_MODEL]
            return installed

        # Comma-separated list
        if "," in model_arg:
            requested = [m.strip() for m in model_arg.split(",") if m.strip()]
            missing = [m for m in requested if m not in installed]
            if missing:
                print(
                    f"[WARN] Models not installed locally: {missing}. "
                    "Attempting to pull …",
                    file=sys.stderr,
                )
                for m in missing:
                    self.pull(m)
            return requested

        # Single model name
        if model_arg not in installed:
            if installed:
                print(
                    f"[WARN] Model '{model_arg}' not found locally. "
                    f"Using '{installed[0]}' instead.",
                    file=sys.stderr,
                )
                return [installed[0]]
            print(
                f"[WARN] No models installed. Using default: {DEFAULT_MODEL}.",
                file=sys.stderr,
            )
            return [DEFAULT_MODEL]

        return [model_arg]

    def query(self, model_name: str, messages: list[dict]) -> str:
        """Send *messages* to *model_name* and return the reply text.

        Args:
            model_name: The Ollama model to query.
            messages:   OpenAI-style message list
                        (``[{"role": "user", "content": "…"}, …]``).

        Returns:
            The model's reply as a plain string.

        Raises:
            RuntimeError: If Ollama is not reachable.
        """
        self.assert_ollama_running()
        response = ollama.chat(model=model_name, messages=messages, host=self.host)  # type: ignore[union-attr]
        # ollama-python returns an object or dict depending on version
        if isinstance(response, dict):
            return response.get("message", {}).get("content", "")
        return response.message.content  # type: ignore[union-attr]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _make_client(self) -> Optional[Any]:
        if ollama is None:
            return None
        try:
            return ollama.Client(host=self.host)  # type: ignore[union-attr]
        except Exception:
            return None

    def _list_raw(self) -> dict:
        """Call ``ollama.list()`` and return the raw dict."""
        if ollama is None:
            raise RuntimeError("ollama Python package is not installed.")
        result = ollama.list(host=self.host)  # type: ignore[union-attr]
        if isinstance(result, dict):
            return result
        # Pydantic model returned by newer versions
        return result.model_dump() if hasattr(result, "model_dump") else {}
