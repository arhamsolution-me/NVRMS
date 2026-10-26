"""NVRSMS Edge Agent — Main entry point."""

from __future__ import annotations

import asyncio
import os
import sys

from agent.client import AgentClient, enrol_agent
from agent.config import get_settings
from agent.logging_config import configure_logging, get_logger
from agent.storage import SecureStorage

configure_logging()
log = get_logger(__name__)


async def main() -> None:
    """Agent lifecycle: bootstrap enrolment if needed, then run persistent control channel."""
    settings = get_settings()
    storage = SecureStorage()

    creds = storage.load()
    if not creds:
        # Check if an enrolment code is provided
        enrol_code = os.environ.get("AGENT_ENROLMENT_CODE")
        if not enrol_code:
            log.warning(
                "agent_unprovisioned",
                detail="No credentials found in secure storage and AGENT_ENROLMENT_CODE not set. Waiting.",
            )
            # Wait for provisioning
            while True:
                await asyncio.sleep(10)
                creds = storage.load()
                if creds:
                    break

        if not creds and enrol_code:
            log.info("agent_starting_enrolment", code=enrol_code[:8] + "...")
            enrol_res = await enrol_agent(
                hub_url=settings.hub_api_url,
                enrolment_code=enrol_code,
                name=os.environ.get("AGENT_NAME", "Edge Agent"),
                version=settings.agent_version,
            )
            creds = {
                "agent_id": str(enrol_res["agent_id"]),
                "agent_token": enrol_res["agent_token"],
                "hub_url": enrol_res["hub_url"],
                "name": enrol_res["name"],
            }
            storage.save(creds)
            log.info("agent_enrolment_succeeded_saved_credentials", agent_id=creds["agent_id"])

    if creds is None:
        log.error("agent_credentials_not_found_and_no_enrolment_code")
        return

    log.info("agent_starting_control_channel", agent_id=creds["agent_id"])
    client = AgentClient(
        agent_id=creds["agent_id"],
        agent_token=creds["agent_token"],
        hub_url=creds.get("hub_url", settings.hub_url),
        heartbeat_interval=settings.heartbeat_interval,
        base_delay=settings.reconnect_base_delay,
        max_delay=settings.reconnect_max_delay,
    )

    try:
        await client.run()
    except asyncio.CancelledError:
        log.info("agent_stopping")
        client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
