"""Stream manager: viewer reference counting, fan-out, grace period, and concurrency tracking."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status

from hub_backend.logging_config import get_logger
from hub_backend.models.camera import Camera
from hub_backend.models.nvr import NVR
from hub_backend.services.agent_manager import agent_manager

log = get_logger(__name__)

MAX_STREAMS_PER_TENANT = 50
MAX_STREAMS_PER_AGENT = 20
DEFAULT_GRACE_PERIOD_SECONDS = 15.0


class ActiveStreamSession:
    """Represents a live video stream published by an edge agent."""

    def __init__(
        self,
        stream_id: str,
        camera_id: uuid.UUID,
        agent_id: uuid.UUID,
        tenant_id: uuid.UUID,
        stream_type: str,
        target_path: str,
    ) -> None:
        self.stream_id = stream_id
        self.camera_id = camera_id
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.stream_type = stream_type
        self.target_path = target_path
        self.viewers: set[str] = set()
        self.started_at = datetime.now(UTC)
        self.grace_task: asyncio.Task[None] | None = None

    @property
    def viewer_count(self) -> int:
        return len(self.viewers)


class StreamManager:
    """Supervises active streams, viewer fan-out, grace periods, and agent publishing workers."""

    def __init__(self) -> None:
        self.active_streams: dict[str, ActiveStreamSession] = {}
        self._lock = asyncio.Lock()

    def get_stream_key(self, camera_id: uuid.UUID, stream_type: str) -> str:
        return f"{camera_id}_{stream_type}"

    def get_agent_active_count(self, agent_id: uuid.UUID) -> int:
        return sum(1 for s in self.active_streams.values() if s.agent_id == agent_id)

    def get_tenant_active_count(self, tenant_id: uuid.UUID) -> int:
        return sum(1 for s in self.active_streams.values() if s.tenant_id == tenant_id)

    async def request_stream(
        self,
        camera: Camera,
        nvr: NVR,
        stream_type: str,
        viewer_id: str,
    ) -> tuple[ActiveStreamSession, bool]:
        """Request a stream for a viewer.

        If stream is already running, re-uses existing NVR pull (fan-out) and cancels any pending grace period.
        If stream is not running, initiates an on-demand pull via the edge agent.

        Returns:
            tuple[ActiveStreamSession, bool]: (session, was_newly_started)
        """
        stream_key = self.get_stream_key(camera.id, stream_type)

        async with self._lock:
            if stream_key in self.active_streams:
                session = self.active_streams[stream_key]
                if session.grace_task and not session.grace_task.done():
                    session.grace_task.cancel()
                    session.grace_task = None
                    log.info("stream_grace_period_aborted_new_viewer", stream_id=stream_key)

                session.viewers.add(viewer_id)
                log.info(
                    "stream_viewer_joined_fan_out",
                    stream_id=stream_key,
                    viewer_count=session.viewer_count,
                )
                return session, False

            # Concurrency limit enforcement
            agent_count = self.get_agent_active_count(nvr.agent_id)
            if agent_count >= MAX_STREAMS_PER_AGENT:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Agent stream limit reached ({MAX_STREAMS_PER_AGENT} active streams)",
                )

            tenant_count = self.get_tenant_active_count(camera.tenant_id)
            if tenant_count >= MAX_STREAMS_PER_TENANT:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Tenant stream limit reached ({MAX_STREAMS_PER_TENANT} active streams)",
                )

            # Determine source URL
            source_url = (
                camera.main_stream_url
                if stream_type == "main"
                else (camera.sub_stream_url or camera.main_stream_url)
            )
            target_path = f"live/{stream_key}"

            # Dispatch start_stream command to Agent
            try:
                await agent_manager.send_command(
                    agent_id=str(nvr.agent_id),
                    command="start_stream",
                    payload={
                        "stream_id": stream_key,
                        "source_url": source_url,
                        "target_path": target_path,
                        "codec": camera.codec,
                    },
                    timeout_seconds=10,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to start stream on agent: {exc}",
                ) from exc

            session = ActiveStreamSession(
                stream_id=stream_key,
                camera_id=camera.id,
                agent_id=nvr.agent_id,
                tenant_id=camera.tenant_id,
                stream_type=stream_type,
                target_path=target_path,
            )
            session.viewers.add(viewer_id)
            self.active_streams[stream_key] = session

            log.info("stream_started_on_demand", stream_id=stream_key, agent_id=str(nvr.agent_id))
            return session, True

    async def leave_stream(
        self,
        camera_id: uuid.UUID,
        stream_type: str,
        viewer_id: str,
        grace_seconds: float = DEFAULT_GRACE_PERIOD_SECONDS,
    ) -> None:
        """Viewer leaves stream. If last viewer leaves, initiates grace period timer."""
        stream_key = self.get_stream_key(camera_id, stream_type)

        async with self._lock:
            session = self.active_streams.get(stream_key)
            if not session:
                return

            session.viewers.discard(viewer_id)
            log.info(
                "stream_viewer_left",
                stream_id=stream_key,
                remaining_viewers=session.viewer_count,
            )

            if session.viewer_count == 0 and not session.grace_task:
                session.grace_task = asyncio.create_task(
                    self._grace_period_shutdown(stream_key, grace_seconds)
                )

    async def _grace_period_shutdown(self, stream_key: str, grace_seconds: float) -> None:
        """Wait for grace period, then stop stream if no viewers rejoined."""
        try:
            await asyncio.sleep(grace_seconds)
            session = None
            async with self._lock:
                s = self.active_streams.get(stream_key)
                if not s or s.viewer_count > 0:
                    return
                session = self.active_streams.pop(stream_key, None)

            if session:
                with contextlib.suppress(Exception):
                    await agent_manager.send_command(
                        agent_id=str(session.agent_id),
                        command="stop_stream",
                        payload={"stream_id": stream_key},
                        timeout_seconds=5,
                    )
                log.info("stream_grace_period_expired_stopped", stream_id=stream_key)
        except asyncio.CancelledError:
            pass


stream_manager = StreamManager()
