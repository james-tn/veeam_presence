"""Veeam Presence — Dev UI entry point."""

import logging
import os
import uvicorn

# Load .env from project root before any other imports
from dotenv import load_dotenv

_project_root = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(_project_root, ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    uvicorn.run("dev_ui.app:app", host="0.0.0.0", port=8787, reload=True, log_level="info")
