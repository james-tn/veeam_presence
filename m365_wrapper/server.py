"""Veeam Presence — M365 wrapper entry point."""

import logging
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    from m365_wrapper.config import get_port
    uvicorn.run("m365_wrapper.app:app", host="0.0.0.0", port=get_port(), log_level="info")
