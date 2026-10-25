"""Stage 4 agent tests: FFmpeg command construction, stream worker lifecycle, and stream manager."""

from __future__ import annotations

import pytest

from agent.commands import execute_command
from agent.streaming.manager import AgentStreamManager
from agent.streaming.worker import StreamWorker


class TestFFmpegCommandBuilder:
    """Tests for low-latency ffmpeg command line generation."""

    def test_native_copy_command(self) -> None:
        """H.264 streams use -c copy for zero transcoding overhead."""
        worker = StreamWorker(
            stream_id="cam1_sub",
            source_url="rtsp://192.168.1.100:554/ch1/sub",
            target_path="live/cam1_sub",
            mediamtx_rtsp_base="rtsp://mediamtx:8554",
            codec="h264",
            transcode_h265=False,
        )
        cmd = worker.build_command()
        assert "ffmpeg" in cmd[0]
        assert "-rtsp_transport" in cmd
        assert "tcp" in cmd
        assert "-c" in cmd
        assert "copy" in cmd
        assert "rtsp://mediamtx:8554/live/cam1_sub" in cmd

    def test_transcode_h265_command(self) -> None:
        """H.265 transcoding uses libx264 with ultrafast and zerolatency flags."""
        worker = StreamWorker(
            stream_id="cam2_main",
            source_url="rtsp://192.168.1.100:554/ch2/main",
            target_path="live/cam2_main",
            mediamtx_rtsp_base="rtsp://mediamtx:8554",
            codec="h265",
            transcode_h265=True,
        )
        cmd = worker.build_command()
        assert "libx264" in cmd
        assert "ultrafast" in cmd
        assert "zerolatency" in cmd


class TestAgentStreamManager:
    """Tests for agent stream manager tracking and command execution."""

    @pytest.mark.asyncio
    async def test_stream_manager_lifecycle(self) -> None:
        """Manager starts stream, detects existing running stream, and stops cleanly."""
        manager = AgentStreamManager()

        # 1. Start stream
        start_res = await manager.start_stream(
            stream_id="stream-001",
            source_url="rtsp://localhost:554/mock",
            target_path="live/stream-001",
            codec="h264",
        )
        assert start_res["status"] == "started"
        assert "stream-001" in manager.list_active()

        # 2. Starting same stream returns already_running without duplicate
        dup_res = await manager.start_stream(
            stream_id="stream-001",
            source_url="rtsp://localhost:554/mock",
            target_path="live/stream-001",
        )
        assert dup_res["status"] == "already_running"
        assert len(manager.list_active()) == 1

        # 3. Stop stream
        stop_res = await manager.stop_stream("stream-001")
        assert stop_res["status"] == "stopped"
        assert "stream-001" not in manager.list_active()

        # 4. Stop non-existent stream
        not_found_res = await manager.stop_stream("stream-001")
        assert not_found_res["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_streaming_commands_dispatch(self) -> None:
        """start_stream and stop_stream commands execute through execute_command."""
        start_res = await execute_command(
            "start_stream",
            {
                "stream_id": "cmd-stream-test",
                "source_url": "rtsp://localhost/test",
                "target_path": "live/cmd-stream-test",
                "codec": "h264",
            },
        )
        assert start_res["status"] == "started"

        stop_res = await execute_command(
            "stop_stream",
            {"stream_id": "cmd-stream-test"},
        )
        assert stop_res["status"] == "stopped"
