"""Stage 0 agent tests: config and startup."""

from __future__ import annotations

from agent.config import AgentSettings, get_settings


class TestAgentConfig:
    """Tests for agent configuration."""

    def test_settings_load_defaults(self) -> None:
        """AgentSettings should load with valid defaults."""
        # Clear the cache to force a fresh load
        get_settings.cache_clear()  # type: ignore[attr-defined]
        import os

        os.environ.setdefault("AGENT_HUB_URL", "ws://localhost:8000")
        settings = AgentSettings()
        assert settings.agent_version == "0.1.0"
        assert "localhost" in settings.hub_url or "hub" in settings.hub_url

    def test_settings_heartbeat_interval(self) -> None:
        """Heartbeat interval should be positive."""
        settings = AgentSettings()
        assert settings.heartbeat_interval > 0

    def test_settings_reconnect_delays(self) -> None:
        """Reconnect delays should be sane (base <= max)."""
        settings = AgentSettings()
        assert settings.reconnect_base_delay <= settings.reconnect_max_delay


class TestAgentLogging:
    """Tests for agent logging configuration."""

    def test_configure_logging_does_not_raise(self) -> None:
        """configure_logging() should not raise any exceptions."""
        from agent.logging_config import configure_logging

        configure_logging()  # Should run cleanly

    def test_get_logger_returns_logger(self) -> None:
        """get_logger() should return a structlog BoundLogger."""
        from agent.logging_config import configure_logging, get_logger

        configure_logging()
        log = get_logger("test")
        assert log is not None
