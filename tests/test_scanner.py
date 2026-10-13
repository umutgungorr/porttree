"""Tests for the cross-platform socket scanner."""

from unittest.mock import MagicMock, mock_open, patch

from porttree.scanner import (
    _parse_hex_ipv4,
    _parse_hex_ipv6,
    scan_linux_procfs,
    scan_linux_ss,
    scan_listening_sockets,
    scan_macos_lsof,
    scan_windows_netstat,
)


def test_parse_hex_ipv4():
    # 0100007F in little endian -> 127.0.0.1
    assert _parse_hex_ipv4("0100007F") == "127.0.0.1"
    # 00000000 -> 0.0.0.0
    assert _parse_hex_ipv4("00000000") == "0.0.0.0"


def test_parse_hex_ipv6():
    # 32 zeros -> ::
    hex_v6 = "00000000000000000000000000000000"
    res = _parse_hex_ipv6(hex_v6)
    assert res in ("::", "0:0:0:0:0:0:0:0")


def test_scan_windows_netstat():
    sample_output = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:22             0.0.0.0:0              LISTENING       7240
  TCP    127.0.0.1:3000         0.0.0.0:0              LISTENING       14200
  TCP    [::]:8080              [::]:0                 LISTENING       18900
  TCP    192.168.1.10:49152     142.250.1.1:443        ESTABLISHED     4500
  UDP    0.0.0.0:5353           *:*                                    9999
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_output)
        sockets = scan_windows_netstat(protocol="all")

        assert len(sockets) == 4  # 3 listening TCP + 1 bound UDP
        assert sockets[0].local_port == 22
        assert sockets[0].pid == 7240
        assert sockets[0].local_address == "0.0.0.0"

        assert sockets[1].local_port == 3000
        assert sockets[1].pid == 14200
        assert sockets[1].local_address == "127.0.0.1"

        assert sockets[2].local_port == 8080
        assert sockets[2].pid == 18900
        assert sockets[2].local_address == "::"

        assert sockets[3].local_port == 5353
        assert sockets[3].protocol == "udp"
        assert sockets[3].pid == 9999


def test_scan_macos_lsof():
    sample_output = """COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
node    45621 user   23u  IPv6 0x12345678       0t0  TCP *:3000 (LISTEN)
python3 89123 user    4u  IPv4 0x87654321       0t0  TCP 127.0.0.1:8000 (LISTEN)
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_output)
        sockets = scan_macos_lsof(protocol="tcp")

        assert len(sockets) == 2
        assert sockets[0].local_port == 3000
        assert sockets[0].pid == 45621
        assert sockets[0].local_address == "0.0.0.0"

        assert sockets[1].local_port == 8000
        assert sockets[1].pid == 89123
        assert sockets[1].local_address == "127.0.0.1"


def test_scan_linux_ss():
    sample_output = """Netid State  Recv-Q Send-Q  Local Address:Port   Peer Address:PortProcess
tcp   LISTEN 0      128     0.0.0.0:22           0.0.0.0:*       users:(("sshd",pid=123,fd=3))
tcp   LISTEN 0      511     *:3000               *:*             users:(("node",pid=456,fd=19))
tcp   LISTEN 0      128     [::]:8080            [::]:*          users:(("java",pid=789,fd=45))
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_output)
        sockets = scan_linux_ss(protocol="tcp")

        assert len(sockets) == 3
        assert sockets[0].local_port == 22
        assert sockets[0].pid == 123
        assert sockets[0].local_address == "0.0.0.0"

        assert sockets[1].local_port == 3000
        assert sockets[1].pid == 456

        assert sockets[2].local_port == 8080
        assert sockets[2].pid == 789


def test_scan_linux_procfs():
    # Header + 1 TCP line (port 3000 in hex is 0BB8, state 0A is LISTEN)
    proc_tcp_content = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:0BB8 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 998877 1 0000000000000000 100 0 0 10 0
"""
    with (
        patch("os.path.isfile", side_effect=lambda p: p == "/proc/net/tcp"),
        patch("builtins.open", mock_open(read_data=proc_tcp_content)),
        patch("porttree.scanner._build_linux_inode_pid_map", return_value={998877: 4321}),
    ):
        sockets = scan_linux_procfs(protocol="tcp")

        assert len(sockets) == 1
        assert sockets[0].local_port == 3000
        assert sockets[0].local_address == "127.0.0.1"
        assert sockets[0].pid == 4321
        assert sockets[0].inode == 998877


def test_scan_listening_sockets_deduplication_and_filtering():
    with (
        patch("sys.platform", "win32"),
        patch("porttree.scanner.scan_windows_netstat") as mock_netstat,
    ):
        from porttree.config import SocketInfo

        mock_netstat.return_value = [
            SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=100),
            SocketInfo(
                protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=100
            ),  # Duplicate
            SocketInfo(protocol="tcp", local_address="127.0.0.1", local_port=8080, pid=200),
            SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=9000, pid=300),
        ]

        # Filter by specific port [3000]
        filtered = scan_listening_sockets(ports=[3000])
        assert len(filtered) == 1
        assert filtered[0].local_port == 3000

        # Scan all (deduped)
        all_res = scan_listening_sockets()
        assert len(all_res) == 3
