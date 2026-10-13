"""Tests for graceful process tree killer."""

from unittest.mock import MagicMock, patch

from porttree.config import ExcludedPortRange, ProcessNode, SocketInfo
from porttree.killer import kill_port


def test_kill_port_not_in_use():
    with (
        patch("porttree.killer.scan_listening_sockets", return_value=[]),
        patch("porttree.killer.check_port_exclusion", return_value=None),
    ):
        res = kill_port(9999)
        assert res.success is True
        assert "not in use" in res.message


def test_kill_port_winnat_reserved():
    ex = ExcludedPortRange(50000, 50059, administered=True, protocol="tcp")
    with (
        patch("porttree.killer.scan_listening_sockets", return_value=[]),
        patch("porttree.killer.check_port_exclusion", return_value=ex),
    ):
        res = kill_port(50025)
        assert res.success is False
        assert res.is_winnat_reserved is True
        assert "Hyper-V / WinNAT" in res.message


def test_kill_port_dry_run(sample_process_tree):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=1234)]
    with (
        patch("porttree.killer.scan_listening_sockets", return_value=sockets),
        patch("porttree.tree.ProcessResolver.build_full_tree", return_value=sample_process_tree),
    ):
        res = kill_port(3000, dry_run=True)
        assert res.dry_run is True
        assert res.success is True
        # Children pids 1235, 1236, and parent 1234
        assert set(res.killed_pids) == {1234, 1235, 1236}
        assert "[Dry Run]" in res.message


def test_kill_port_successful_execution(sample_process_tree):
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=1234)]

    # Mock scan_listening_sockets: first call returns sockets, second call (after kill) returns empty []
    mock_scan = MagicMock(side_effect=[sockets, []])

    with (
        patch("porttree.killer.scan_listening_sockets", mock_scan),
        patch("porttree.tree.ProcessResolver.build_full_tree", return_value=sample_process_tree),
        patch("porttree.killer._terminate_pid", return_value=True),
        patch("porttree.killer._is_pid_alive", return_value=False),
    ):
        res = kill_port(3000, auto_confirm=True, timeout=0.1)
        assert res.success is True
        assert "Successfully freed port 3000" in res.message
        assert set(res.killed_pids) == {1234, 1235, 1236}


def test_kill_port_escalation_to_force():
    sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=5000)]
    node = ProcessNode(pid=5000, name="stubborn-server")

    mock_scan = MagicMock(side_effect=[sockets, []])
    mock_terminate = MagicMock(return_value=True)

    def fake_alive(pid):
        for c in mock_terminate.call_args_list:
            if c.kwargs.get("force") or (len(c.args) > 1 and c.args[1] is True):
                return False
        return True

    mock_alive = MagicMock(side_effect=fake_alive)

    with (
        patch("porttree.killer.scan_listening_sockets", mock_scan),
        patch("porttree.tree.ProcessResolver.build_full_tree", return_value=node),
        patch("porttree.killer._terminate_pid", mock_terminate),
        patch("porttree.killer._is_pid_alive", mock_alive),
        patch("time.sleep"),
    ):
        res = kill_port(3000, auto_confirm=True, timeout=0.01)
        assert res.success is True
        # Verify force termination was called
        assert any(
            call.kwargs.get("force") is True or (len(call.args) > 1 and call.args[1] is True)
            for call in mock_terminate.call_args_list
        )
