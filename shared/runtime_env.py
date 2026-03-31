"""Load .env files at import time for local dev."""

import os
from pathlib import Path

_loaded = False


def ensure_runtime_env_loaded() -> None:
    """Load .env from project root if not already loaded."""
    global _loaded
    if _loaded:
        return
    _loaded = True

    # Walk up from this file to find .env
    search = Path(__file__).resolve().parent.parent
    for candidate in (search, search.parent):
        env_file = candidate / ".env"
        if env_file.exists():
            _load_dotenv(env_file)
            return


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — no external dependency needed."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
