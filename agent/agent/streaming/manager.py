"""Agent Stream Manager coordinating local active stream workers."""

from __future__ import annotations

import asyncio
from typing import Any

from agent.logging_config import get_logger
from agent.streaming.worker import StreamWorker

log = get_logger(__name__)


class AgentStreamManager:
    """Manages active StreamWorker instances on the edge agent."""

    def __init__(self) -> None:
        self.workers: dict[str, StreamWorker] = {}
        self._lock = asyncio.Lock()

    async def start_stream(
        self,
        stream_id: str,
        source_url: str,
        target_path: str,
        codec: str = "h264",
        transcode_h265: bool = False,
    ) -> dict[str, Any]:
        """Start or return active stream worker for this stream_id."""
        async with self._lock:
            if stream_id in self.workers:
                worker = self.workers[stream_id]
                return {
                    "status": "already_running",
                    "stream_id": stream_id,
                    "target_path": worker.target_path,
                }

            worker = StreamWorker(
                stream_id=stream_id,
                source_url=source_url,
                target_path=target_path,
                codec=codec,
                transcode_h265=transcode_h265,
            )
            await worker.start()
            self.workers[stream_id] = worker

            log.info("agent_stream_started", stream_id=stream_id, target_path=target_path)
            return {
                "status": "started",
                "stream_id": stream_id,
                "target_path": target_path,
                "codec": codec,
            }

    async def stop_stream(self, stream_id: str) -> dict[str, Any]:
        """Stop and remove a stream worker."""
        async with self._lock:
            worker = self.workers.pop(stream_id, None)
            if not worker:
                return {"status": "not_found", "stream_id": stream_id}

            await worker.stop()
            log.info("agent_stream_stopped", stream_id=stream_id)
            return {"status": "stopped", "stream_id": stream_id}

    async def stop_all(self) -> None:
        """Stop all workers during agent shutdown."""
        async with self._lock:
            for worker in list(self.workers.values()):
                await worker.stop()
            self.workers.clear()

    def list_active(self) -> list[str]:
        return list(self.workers.keys())


agent_stream_manager = AgentStreamManager()
