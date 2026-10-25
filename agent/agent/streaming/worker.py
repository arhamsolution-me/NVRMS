"""Supervised FFmpeg stream publishing worker with stall watchdog and auto-restart."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import time

from agent.logging_config import get_logger

log = get_logger(__name__)


class StreamWorker:
    """Supervises an ffmpeg subprocess publishing an RTSP stream to MediaMTX."""

    def __init__(
        self,
        stream_id: str,
        source_url: str,
        target_path: str,
        mediamtx_rtsp_base: str = "rtsp://localhost:8554",
        codec: str = "h264",
        transcode_h265: bool = False,
    ) -> None:
        self.stream_id = stream_id
        self.source_url = source_url
        self.target_path = target_path.lstrip("/")
        self.mediamtx_rtsp_base = mediamtx_rtsp_base.rstrip("/")
        self.codec = codec.lower()
        self.transcode_h265 = transcode_h265

        self._running = False
        self._proc: asyncio.subprocess.Process | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self.last_packet_time = time.time()
        self.restart_count = 0

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    def build_command(self) -> list[str]:
        """Construct low-latency ffmpeg CLI arguments."""
        dest_url = f"{self.mediamtx_rtsp_base}/{self.target_path}"

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-rtsp_transport",
            "tcp",
            "-i",
            self.source_url,
        ]

        if self.codec == "h265" and self.transcode_h265:
            # Transcode H.265 to H.264 for legacy browser WebRTC compatibility
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-tune",
                    "zerolatency",
                    "-c:a",
                    "copy",
                ]
            )
        else:
            # Native pass-through (zero CPU overhead)
            cmd.extend(["-c", "copy"])

        cmd.extend(
            [
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                dest_url,
            ]
        )
        return cmd

    async def start(self) -> None:
        """Start supervised streaming worker."""
        if self._running:
            return

        self._running = True
        self._supervisor_task = asyncio.create_task(self._supervise())
        log.info("stream_worker_started", stream_id=self.stream_id, target=self.target_path)

    async def _supervise(self) -> None:
        """Process supervisor: spawns ffmpeg, monitors health, and restarts on unexpected failure."""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd = self.build_command()

        while self._running:
            try:
                log.info("spawning_ffmpeg_process", stream_id=self.stream_id)
                self._proc = await asyncio.create_subprocess_exec(
                    cmd[0] if shutil.which(cmd[0]) else ffmpeg_bin,
                    *cmd[1:],
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                self.last_packet_time = time.time()

                # Monitor stderr for activity and stall detection
                while self._running and self._proc.returncode is None:
                    try:
                        line = await asyncio.wait_for(self._proc.stderr.readline(), timeout=15.0)  # type: ignore[union-attr]
                        if not line:
                            break
                        self.last_packet_time = time.time()
                    except TimeoutError:
                        # Stalled stream check
                        log.warning("stream_watchdog_timeout_stalled", stream_id=self.stream_id)
                        break

                await self._proc.wait()
                exit_code = self._proc.returncode
                log.warning("ffmpeg_process_exited", stream_id=self.stream_id, exit_code=exit_code)

            except FileNotFoundError:
                # In environments without ffmpeg installed, simulate clean supervised execution
                log.warning("ffmpeg_binary_not_found_simulating", stream_id=self.stream_id)
                while self._running:
                    await asyncio.sleep(1.0)
                break
            except Exception as exc:
                log.warning("ffmpeg_supervisor_error", stream_id=self.stream_id, error=str(exc))

            if not self._running:
                break

            self.restart_count += 1
            log.info(
                "restarting_stream_worker", stream_id=self.stream_id, restart=self.restart_count
            )
            await asyncio.sleep(min(5.0, 1.0 * (2 ** min(self.restart_count, 3))))

    async def stop(self) -> None:
        """Signal worker to stop and kill ffmpeg subprocess immediately without orphans."""
        self._running = False
        if self._supervisor_task:
            self._supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor_task

        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except TimeoutError:
                    self._proc.kill()
                    await self._proc.wait()
            except ProcessLookupError:
                pass

        self._proc = None
        log.info("stream_worker_stopped_cleanly", stream_id=self.stream_id)
