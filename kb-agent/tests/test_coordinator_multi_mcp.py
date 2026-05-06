"""Tests for the multi-MCP wiring of the Coordinator agent.

These tests stub out MCPToolset so no `npx` subprocess is ever spawned.
"""
import pytest

pytest.importorskip("mcp")

from unittest.mock import patch, MagicMock


def _clear_toolbox_env(monkeypatch):
    for var in (
        "KC_TOOLBOX_ENABLED", "BQ_TOOLBOX_ENABLED",
        "DATAPLEX_PROJECT", "BIGQUERY_PROJECT", "BIGQUERY_LOCATION",
    ):
        monkeypatch.delenv(var, raising=False)


def test_no_toolboxes_when_flags_off(monkeypatch):
    _clear_toolbox_env(monkeypatch)
    with patch("agents.coordinator.MCPToolset") as mock_mcp:
        from agents.coordinator import build_coordinator
        agent = build_coordinator()
        assert mock_mcp.call_count == 0
        # Baseline: tool_query_spanner_graph + _doc_agent_tool
        assert len(agent.tools) == 2


def test_kc_toolbox_enabled(monkeypatch):
    _clear_toolbox_env(monkeypatch)
    monkeypatch.setenv("KC_TOOLBOX_ENABLED", "true")
    monkeypatch.setenv("DATAPLEX_PROJECT", "test-proj")

    fake_toolset = MagicMock(name="FakeToolset")
    with patch("agents.coordinator.MCPToolset", return_value=fake_toolset) as mock_mcp:
        from agents.coordinator import build_coordinator
        agent = build_coordinator()

    assert mock_mcp.call_count == 1
    kwargs = mock_mcp.call_args.kwargs
    assert kwargs["tool_name_prefix"] == "kc_"

    conn = kwargs["connection_params"]
    server_params = conn.server_params
    env = server_params.env
    assert "PATH" in env and env["PATH"]  # PATH propagated
    assert env["DATAPLEX_PROJECT"] == "test-proj"
    assert "dataplex" in server_params.args

    # baseline 2 + 1 KC toolset
    assert len(agent.tools) == 3
    assert agent.tools[-1] is fake_toolset


def test_kc_enabled_missing_project_raises(monkeypatch):
    _clear_toolbox_env(monkeypatch)
    monkeypatch.setenv("KC_TOOLBOX_ENABLED", "true")
    with patch("agents.coordinator.MCPToolset"):
        from agents.coordinator import build_coordinator
        with pytest.raises(RuntimeError, match="DATAPLEX_PROJECT"):
            build_coordinator()


def test_bq_enabled_missing_location_raises(monkeypatch):
    _clear_toolbox_env(monkeypatch)
    monkeypatch.setenv("BQ_TOOLBOX_ENABLED", "true")
    monkeypatch.setenv("BIGQUERY_PROJECT", "test")
    with patch("agents.coordinator.MCPToolset"):
        from agents.coordinator import build_coordinator
        with pytest.raises(RuntimeError, match="BIGQUERY_LOCATION"):
            build_coordinator()
