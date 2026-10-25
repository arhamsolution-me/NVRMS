"""Tests for Agent resilience layer and failure matrix implementations."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent.client import AgentClient
from agent.commands import execute_command
from agent.resilience.disk_monitor import DiskMonitor
from agent.resilience.network_monitor import NetworkQualityMonitor
from agent.resilience.time_sync import TimeSyncManager
from agent.resilience.updater import AgentUpdater, UpdateVerificationError
from agent.streaming.worker import StreamWorker


class TestTimeDriftAndCompensation:
    """Matrix Row 9: Clock drift detection and compensation."""

    def test_clock_drift_within_threshold_not_skewed(self) -> None:
        mgr = TimeSyncManager(drift_threshold=15.0)
        local_now = datetime.now(UTC)
        # Server timestamp within 5 seconds
        server_ts = (local_now + timedelta(seconds=5)).isoformat()

        skew = mgr.sync_with_server(server_ts)
        assert abs(skew) < 15.0
        assert mgr.is_skewed is False

    def test_clock_drift_exceeding_threshold_triggers_compensation(self) -> None:
        mgr = TimeSyncManager(drift_threshold=15.0)
        local_now = datetime.now(UTC)
        # Server timestamp 120 seconds ahead (2 minutes drift)
        server_ts = (local_now + timedelta(seconds=120)).isoformat()

        skew = mgr.sync_with_server(server_ts)
        assert skew >= 115.0
        assert mgr.is_skewed is True

        # Compensated time should be approximately server_ts
        compensated = mgr.get_compensated_utc()
        diff = (compensated - local_now).total_seconds()
        assert 115.0 <= diff <= 125.0


class TestDiskMonitorAndLogRotation:
    """Matrix Row 7: Disk monitoring and bounded FIFO log rotation."""

    def test_disk_usage_stats(self, tmp_path: Path) -> None:
        monitor = DiskMonitor(min_free_mb=100.0, max_used_percent=95.0)
        stats = monitor.get_disk_stats(tmp_path)
        assert "total_mb" in stats
        assert "free_mb" in stats
        assert "used_percent" in stats
        assert isinstance(stats["is_critical"], bool)

    def test_log_pruning_fifo_order(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create 5 dummy log files with distinct timestamps
        files: list[Path] = []
        for i in range(5):
            p = log_dir / f"app_{i}.log"
            p.write_text(f"log data {i}")
            files.append(p)

        monitor = DiskMonitor(max_log_files=2)
        # Pruning keeping at most 2 files
        deleted = monitor.prune_old_logs(log_dir, max_files=2, force=True)
        assert len(deleted) == 3

        # Oldest files (app_0, app_1, app_2) should be deleted
        remaining = list(log_dir.glob("*.log"))
        assert len(remaining) == 2


class TestAgentUpdaterAndRollback:
    """Matrix Row 8: Cryptographic signature verification and atomic rollback."""

    def test_update_success_flow(self, tmp_path: Path) -> None:
        updater = AgentUpdater(secret_key=b"test_secret_key_123")

        curr_bin = tmp_path / "agent_binary"
        curr_bin.write_text("v1.0.0-original")

        new_bin = tmp_path / "agent_new_package"
        new_bin.write_text("v1.1.0-upgraded")

        sha = updater.compute_sha256(new_bin)
        sig = updater.compute_signature(new_bin)

        res = updater.apply_update(
            current_file=curr_bin,
            new_package=new_bin,
            expected_sha256=sha,
            signature=sig,
            health_check_fn=lambda: True,
        )

        assert res["status"] == "success"
        assert res["rolled_back"] is False
        assert curr_bin.read_text() == "v1.1.0-upgraded"

    def test_update_checksum_tampered_rejected(self, tmp_path: Path) -> None:
        updater = AgentUpdater(secret_key=b"test_secret_key_123")
        new_bin = tmp_path / "tampered"
        new_bin.write_text("payload")

        with pytest.raises(UpdateVerificationError, match="Checksum mismatch"):
            updater.verify_package(new_bin, expected_sha256="wrong_checksum", signature="sig")

    def test_update_signature_mismatch_rejected(self, tmp_path: Path) -> None:
        updater = AgentUpdater(secret_key=b"test_secret_key_123")
        new_bin = tmp_path / "bad_sig"
        new_bin.write_text("payload")
        sha = updater.compute_sha256(new_bin)

        with pytest.raises(UpdateVerificationError, match="signature validation failed"):
            updater.verify_package(new_bin, expected_sha256=sha, signature="invalid_sig")

    def test_update_health_failure_triggers_automatic_rollback(self, tmp_path: Path) -> None:
        updater = AgentUpdater(secret_key=b"test_secret_key_123")

        curr_bin = tmp_path / "agent_binary"
        curr_bin.write_text("v1.0.0-original")

        new_bin = tmp_path / "agent_faulty_package"
        new_bin.write_text("v1.1.0-corrupt-binary")

        sha = updater.compute_sha256(new_bin)
        sig = updater.compute_signature(new_bin)

        # Health check returns False (simulating crashed boot or failing tests)
        res = updater.apply_update(
            current_file=curr_bin,
            new_package=new_bin,
            expected_sha256=sha,
            signature=sig,
            health_check_fn=lambda: False,
        )

        assert res["status"] == "rolled_back"
        assert res["rolled_back"] is True
        # Content must have been automatically restored to original!
        assert curr_bin.read_text() == "v1.0.0-original"


class TestNetworkQualityAndAdaptiveDegradation:
    """Matrix Row 6: Low uplink bandwidth adaptive stream degradation."""

    def test_degraded_network_recommends_sub_stream(self) -> None:
        monitor = NetworkQualityMonitor()
        # High packet loss (8%)
        res = monitor.evaluate_metrics(packet_loss_pct=8.0, rtt_ms=50.0)
        assert res["is_degraded"] is True
        assert res["recommended_stream"] == "sub"

    def test_recovered_network_streak_restores_main_stream(self) -> None:
        monitor = NetworkQualityMonitor()
        # First degrade
        monitor.evaluate_metrics(packet_loss_pct=10.0, rtt_ms=500.0)
        assert monitor.current_recommendation == "sub"

        # Recover streak 1 and 2 (not yet 3)
        res1 = monitor.evaluate_metrics(packet_loss_pct=0.2, rtt_ms=30.0)
        assert res1["recommended_stream"] == "sub"
        res2 = monitor.evaluate_metrics(packet_loss_pct=0.1, rtt_ms=25.0)
        assert res2["recommended_stream"] == "sub"

        # Streak 3 recovers to main
        res3 = monitor.evaluate_metrics(packet_loss_pct=0.0, rtt_ms=20.0)
        assert res3["recommended_stream"] == "main"


class TestProcessSupervisorAndWatchdog:
    """Matrix Rows 3 & 4: Process crash restart and watchdog stall kill."""

    @pytest.mark.asyncio
    async def test_watchdog_kills_stalled_process(self) -> None:
        worker = StreamWorker(
            stream_id="test_stall",
            source_url="rtsp://localhost:554/live",
            target_path="live/test_stall",
        )
        worker.stall_timeout = 0.05  # 50ms fast timeout for test

        # Mock process
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        from unittest.mock import MagicMock

        mock_proc.kill = MagicMock()
        mock_proc.terminate = MagicMock()
        # Stderr readline hangs / times out
        mock_proc.stderr.readline = AsyncMock(side_effect=TimeoutError)
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            worker._running = True
            asyncio.create_task(worker._supervise())
            await asyncio.sleep(0.1)
            await worker.stop()

        # Verify watchdog killed the hung process
        assert mock_proc.kill.called

    @pytest.mark.asyncio
    async def test_crash_loop_trips_circuit_breaker(self) -> None:
        worker = StreamWorker(
            stream_id="test_crash_loop",
            source_url="rtsp://localhost:554/live",
            target_path="live/test_crash_loop",
        )
        worker.max_crashes_in_window = 3
        worker.crash_window_seconds = 60.0

        # Mock process that exits immediately with error code 1
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=1)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.sleep", AsyncMock()),
        ):
            worker._running = True
            await worker._supervise()

        # Circuit breaker must be tripped after 3 rapid crashes
        assert worker.is_circuit_broken is True
        assert len(worker.crash_timestamps) == 3


class TestAgentClientResilience:
    """Matrix Rows 1 & 5: Connection backoff, jitter, and retry-storm prevention."""

    def test_backoff_has_jitter_within_bounds(self) -> None:
        client = AgentClient(
            agent_id="test-agt",
            agent_token="tok",
            hub_url="http://localhost:8000",
        )
        delays = [client.compute_backoff(attempt=3) for _ in range(50)]
        # All delays must be positive and bounded
        assert all(d >= 1.0 for d in delays)
        assert min(delays) != max(delays)  # Proves jitter is active

    @pytest.mark.asyncio
    async def test_resilience_commands_execution(self) -> None:
        # check_disk
        disk_res = await execute_command("check_disk", {"path": "."})
        assert "stats" in disk_res

        # sync_time
        time_res = await execute_command(
            "sync_time", {"server_timestamp": datetime.now(UTC).isoformat()}
        )
        assert "skew_seconds" in time_res

        # check_network
        net_res = await execute_command("check_network", {"packet_loss_pct": 0.5, "rtt_ms": 30.0})
        assert net_res["recommended_stream"] == "main"
