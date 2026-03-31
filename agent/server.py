"""Veeam Presence — Agent service entry point."""

import logging
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    uvicorn.run("agent.api:app", host="0.0.0.0", port=8000, log_level="info")
