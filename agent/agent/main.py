"""NVRSMS Agent — Edge agent connecting to the hub.

Stage 0: Placeholder main loop.
Full implementation in Stage 2 (enrolment + control channel).
"""

from __future__ import annotations

import asyncio
import sys

from agent.config import get_settings
from agent.logging_config import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


async def main() -> None:
    """Agent main entry point."""
    settings = get_settings()
    log.info(
        "agent_starting",
        version=settings.agent_version,
        hub_url=settings.hub_url,
    )

    # Stage 0: just run indefinitely (replaced in Stage 2)
    log.info("agent_running", state="idle", note="Full implementation in Stage 2")
    try:
        while True:
            await asyncio.sleep(30)
            log.debug("agent_heartbeat_placeholder")
    except asyncio.CancelledError:
        log.info("agent_stopping")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
