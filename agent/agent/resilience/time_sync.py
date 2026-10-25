"""Time synchronization and clock drift compensation for Edge Agent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent.logging_config import get_logger

log = get_logger(__name__)

MAX_ALLOWED_DRIFT_SECONDS = 15.0


class TimeSyncManager:
    """Manages clock skew detection and timestamp compensation."""

    def __init__(self, drift_threshold: float = MAX_ALLOWED_DRIFT_SECONDS) -> None:
        self.drift_threshold = drift_threshold
        self.skew_seconds: float = 0.0
        self.is_skewed: bool = False
        self.last_sync_time: datetime | None = None

    def sync_with_server(self, server_timestamp_iso: str) -> float:
        """Calculate skew between local clock and Hub timestamp.

        Returns:
            The calculated skew in seconds (positive means server is ahead).
        """
        try:
            # Parse ISO timestamp
            clean_ts = server_timestamp_iso.replace("Z", "+00:00")
            server_dt = datetime.fromisoformat(clean_ts)
            if server_dt.tzinfo is None:
                server_dt = server_dt.replace(tzinfo=UTC)

            local_dt = datetime.now(UTC)
            skew = (server_dt - local_dt).total_seconds()
            self.skew_seconds = skew
            self.last_sync_time = local_dt

            if abs(skew) > self.drift_threshold:
                self.is_skewed = True
                log.warning(
                    "clock_drift_detected",
                    skew_seconds=round(skew, 2),
                    threshold=self.drift_threshold,
                    server_time=server_dt.isoformat(),
                    local_time=local_dt.isoformat(),
                )
            else:
                self.is_skewed = False

            return skew
        except Exception as exc:
            log.error("time_sync_failed", error=str(exc))
            return 0.0

    def get_compensated_utc(self) -> datetime:
        """Return compensated current UTC time if drift is detected."""
        now = datetime.now(UTC)
        if self.is_skewed:
            return now + timedelta(seconds=self.skew_seconds)
        return now

    def get_compensated_iso(self) -> str:
        """Return compensated ISO formatted UTC timestamp."""
        return self.get_compensated_utc().isoformat()


# Global singleton instance for the agent
time_sync_manager = TimeSyncManager()
