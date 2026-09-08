from unittest.mock import Mock, patch

import pytest

from ia_assistant_local.integrations.home_assistant import HomeAssistantClient
from ia_assistant_local.integrations.tools import ToolRegistry


def test_unknown_tool_is_denied():
    registry = ToolRegistry(Mock())
    with pytest.raises(PermissionError):
        registry.execute("run_shell", {"command": "anything"}, lambda _: True)


def test_tool_denied_by_user_permission_is_not_executed():
    registry = ToolRegistry(Mock())
    with (
        patch("subprocess.Popen") as process,
        pytest.raises(PermissionError, match="não tem permissão"),
    ):
        registry.execute(
            "open_application",
            {"application": "calculadora"},
            lambda _: True,
            allowed=frozenset({"system_info"}),
        )
    process.assert_not_called()


def test_action_is_not_executed_without_confirmation():
    registry = ToolRegistry(Mock())
    with patch("subprocess.Popen") as process:
        result = registry.execute(
            "open_application", {"application": "calculadora"}, lambda _: False
        )
    process.assert_not_called()
    assert result["status"] == "cancelado pelo usuario"


def test_unlisted_application_is_denied():
    registry = ToolRegistry(Mock())
    with pytest.raises(PermissionError):
        registry.execute("open_application", {"application": "powershell"}, lambda _: True)


def test_unlisted_home_entity_is_denied():
    client = HomeAssistantClient("http://ha.local", "secret", frozenset({"light.sala"}))
    with pytest.raises(PermissionError):
        client.get_state("lock.porta")
