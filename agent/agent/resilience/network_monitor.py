"""Network quality monitor and adaptive bitrate/stream degradation."""

from __future__ import annotations

from typing import Any

from agent.logging_config import get_logger

log = get_logger(__name__)

PACKET_LOSS_DOWNGRADE_THRESHOLD_PCT = 5.0
RTT_DOWNGRADE_THRESHOLD_MS = 400.0
PACKET_LOSS_RECOVERY_THRESHOLD_PCT = 1.0
RTT_RECOVERY_THRESHOLD_MS = 100.0


class NetworkQualityMonitor:
    """Evaluates network health and signals stream profile switching."""

    def __init__(self) -> None:
        self.current_recommendation: str = "main"
        self.recovery_streak: int = 0

    def evaluate_metrics(
        self,
        packet_loss_pct: float,
        rtt_ms: float,
        bitrate_kbps: float = 0.0,
    ) -> dict[str, Any]:
        """Evaluate uplink metrics and determine if stream should be downgraded/upgraded.

        Returns:
            Dict containing quality status and recommendation ("main" or "sub").
        """
        is_degraded = (
            packet_loss_pct >= PACKET_LOSS_DOWNGRADE_THRESHOLD_PCT
            or rtt_ms >= RTT_DOWNGRADE_THRESHOLD_MS
        )

        if is_degraded:
            self.recovery_streak = 0
            if self.current_recommendation != "sub":
                self.current_recommendation = "sub"
                log.warning(
                    "uplink_degradation_detected_falling_back_to_sub",
                    packet_loss_pct=packet_loss_pct,
                    rtt_ms=rtt_ms,
                    recommended_stream="sub",
                )
        else:
            # Check for recovery
            if (
                packet_loss_pct <= PACKET_LOSS_RECOVERY_THRESHOLD_PCT
                and rtt_ms <= RTT_RECOVERY_THRESHOLD_MS
            ):
                self.recovery_streak += 1
                if self.recovery_streak >= 3 and self.current_recommendation != "main":
                    self.current_recommendation = "main"
                    log.info(
                        "uplink_recovered_recommending_main_stream",
                        packet_loss_pct=packet_loss_pct,
                        rtt_ms=rtt_ms,
                        recommended_stream="main",
                    )
            else:
                self.recovery_streak = 0

        return {
            "is_degraded": is_degraded,
            "recommended_stream": self.current_recommendation,
            "packet_loss_pct": packet_loss_pct,
            "rtt_ms": rtt_ms,
            "bitrate_kbps": bitrate_kbps,
        }


network_monitor = NetworkQualityMonitor()
