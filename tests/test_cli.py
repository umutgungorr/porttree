"""Tests for PortTree CLI entrypoint and commands."""

from unittest.mock import patch

from porttree.checker import CheckResult
from porttree.cli import _parse_port_argument, main
from porttree.config import ExcludedPortRange, PortEntry, SocketInfo
from porttree.killer import KillResult


def test_parse_port_argument():
    assert _parse_port_argument("3000") == [3000]
    assert _parse_port_argument("3000,8080") == [3000, 8080]
    assert _parse_port_argument("3000-3003") == [3000, 3001, 3002, 3003]
    assert _parse_port_argument("invalid,4000,99999") == [4000]


def test_cli_scan_default(capsys):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=123)]
    with (
        patch("porttree.cli.scan_listening_sockets", return_value=sockets),
        patch("porttree.cli.ProcessResolver.build_full_tree", return_value=None),
        patch("porttree.cli.is_windows", return_value=False),
    ):
        code = main([])
        assert code == 0
        captured = capsys.readouterr()
        assert "PORT 3000" in captured.out


def test_cli_scan_json(capsys):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=123)]
    with (
        patch("porttree.cli.scan_listening_sockets", return_value=sockets),
        patch("porttree.cli.ProcessResolver.build_full_tree", return_value=None),
        patch("porttree.cli.is_windows", return_value=False),
    ):
        code = main(["--json"])
        assert code == 0
        captured = capsys.readouterr()
        assert '"port": 3000' in captured.out


def test_cli_scan_compact(capsys):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=123)]
    with (
        patch("porttree.cli.scan_listening_sockets", return_value=sockets),
        patch("porttree.cli.ProcessResolver.build_full_tree", return_value=None),
        patch("porttree.cli.is_windows", return_value=False),
    ):
        code = main(["--compact"])
        assert code == 0
        captured = capsys.readouterr()
        assert "PORT" in captured.out
        assert "3000" in captured.out


def test_cli_free_success(capsys):
    kill_res = KillResult(port=3000, success=True, killed_pids=[123], message="Port 3000 freed")
    with patch("porttree.cli.kill_port", return_value=kill_res):
        code = main(["free", "3000", "-y"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Port 3000 freed" in captured.out


def test_cli_kill_alias(capsys):
    kill_res = KillResult(port=8080, success=True, killed_pids=[456], message="Port 8080 killed")
    with patch("porttree.cli.kill_port", return_value=kill_res):
        code = main(["kill", "8080", "-y"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Port 8080 killed" in captured.out


def test_cli_check_clean(capsys):
    check_res = CheckResult()
    with patch("porttree.cli.check_preflight", return_value=check_res):
        code = main(["check", "--fail"])
        assert code == 0
        captured = capsys.readouterr()
        assert "ALL CLEAR" in captured.out


def test_cli_check_fail_on_conflict(capsys):
    conflict = PortEntry(
        port=3000, protocol="tcp", is_conflict=True, source_file="docker-compose.yml"
    )
    check_res = CheckResult(conflicts=[conflict])
    with patch("porttree.cli.check_preflight", return_value=check_res):
        code = main(["check", "--fail"])
        assert code == 1
        captured = capsys.readouterr()
        assert "PORT CONFLICTS DETECTED" in captured.out


def test_cli_winnat(capsys):
    ranges = [ExcludedPortRange(50000, 50059, administered=True, protocol="tcp")]
    with (
        patch("porttree.cli.is_windows", return_value=True),
        patch("porttree.cli.get_windows_port_exclusions", return_value=ranges),
    ):
        code = main(["winnat"])
        assert code == 0
        captured = capsys.readouterr()
        assert "50000" in captured.out
        assert "Administered (*)" in captured.out


def test_cli_positional_port_target(capsys):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=123)]
    with (
        patch("porttree.cli.scan_listening_sockets", return_value=sockets) as mock_scan,
        patch("porttree.cli.ProcessResolver.build_full_tree", return_value=None),
        patch("porttree.cli.is_windows", return_value=False),
    ):
        code = main(["3000"])
        assert code == 0
        mock_scan.assert_called_once_with(ports=[3000], protocol="all")
        captured = capsys.readouterr()
        assert "PORT 3000" in captured.out


def test_cli_positional_port_range(capsys):
    with (
        patch("porttree.cli.scan_listening_sockets", return_value=[]) as mock_scan,
        patch("porttree.cli.is_windows", return_value=False),
    ):
        code = main(["3000-3002"])
        assert code == 0
        mock_scan.assert_called_once_with(ports=[3000, 3001, 3002], protocol="all")


def test_cli_positional_port_with_flags(capsys):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=8080, pid=456)]
    with (
        patch("porttree.cli.scan_listening_sockets", return_value=sockets),
        patch("porttree.cli.ProcessResolver.build_full_tree", return_value=None),
        patch("porttree.cli.is_windows", return_value=False),
    ):
        code = main(["--compact", "8080"])
        assert code == 0
        captured = capsys.readouterr()
        assert "8080" in captured.out
        assert "PORT" in captured.out
