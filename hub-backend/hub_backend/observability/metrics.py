"""Prometheus metrics collection and exposition engine."""

from __future__ import annotations

from collections import defaultdict

from hub_backend.services.agent_manager import agent_manager
from hub_backend.services.stream_manager import stream_manager


class MetricsRegistry:
    """Collects and renders standard Prometheus formatted text metrics."""

    def __init__(self) -> None:
        self.request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self.nvr_probes: dict[str, int] = defaultdict(int)
        self.dr_verifications: dict[str, int] = defaultdict(int)

    def record_request(self, method: str, path: str, status_code: int) -> None:
        self.request_counts[(method, path, status_code)] += 1

    def record_probe(self, status: str) -> None:
        self.nvr_probes[status] += 1

    def record_dr_verification(self, status: str) -> None:
        self.dr_verifications[status] += 1

    def generate_prometheus_output(self) -> str:
        lines: list[str] = [
            "# HELP http_requests_total Total number of HTTP requests processed.",
            "# TYPE http_requests_total counter",
        ]

        for (method, path, code), count in self.request_counts.items():
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status="{code}"}} {count}'
            )

        # Dynamic live gauges
        online_agents = agent_manager.get_online_count()
        active_streams = len(stream_manager.active_streams)
        active_viewers = sum(s.viewer_count for s in stream_manager.active_streams.values())

        lines.extend(
            [
                "# HELP nvrsms_agents_connected_count Current number of edge agents connected via WSS.",
                "# TYPE nvrsms_agents_connected_count gauge",
                f"nvrsms_agents_connected_count {online_agents}",
                "# HELP nvrsms_active_streams_count Current number of active camera RTSP stream pulls.",
                "# TYPE nvrsms_active_streams_count gauge",
                f"nvrsms_active_streams_count {active_streams}",
                "# HELP nvrsms_active_viewers_count Current number of active stream viewers.",
                "# TYPE nvrsms_active_viewers_count gauge",
                f"nvrsms_active_viewers_count {active_viewers}",
            ]
        )

        # NVR Probes
        lines.extend(
            [
                "# HELP nvrsms_nvr_probes_total Total number of NVR discovery probes dispatched.",
                "# TYPE nvrsms_nvr_probes_total counter",
            ]
        )
        for st, count in self.nvr_probes.items():
            lines.append(f'nvrsms_nvr_probes_total{{status="{st}"}} {count}')

        # DR Verifications
        lines.extend(
            [
                "# HELP nvrsms_dr_verifications_total Total automated DR restore verification runs.",
                "# TYPE nvrsms_dr_verifications_total counter",
            ]
        )
        for st, count in self.dr_verifications.items():
            lines.append(f'nvrsms_dr_verifications_total{{status="{st}"}} {count}')

        lines.append("")  # Trailing newline
        return "\n".join(lines)


metrics_registry = MetricsRegistry()
