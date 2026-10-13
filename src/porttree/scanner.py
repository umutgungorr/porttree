"""Cross-platform socket scanner supporting Linux, macOS, and Windows.

Extracts listening TCP and UDP sockets with their bound IP addresses, ports,
and owning PIDs without external dependencies.
"""

from __future__ import annotations

import os
import re
import socket
import struct
import subprocess
import sys

from porttree.config import SocketInfo


def _parse_hex_ipv4(hex_addr: str) -> str:
    """Convert a little-endian 8-character hex string to an IPv4 dotted quad."""
    try:
        raw_bytes = bytes.fromhex(hex_addr)
        # Linux kernel /proc/net/tcp stores IPv4 addresses in little-endian byte order
        return socket.inet_ntoa(raw_bytes[::-1])
    except Exception:
        return hex_addr


def _parse_hex_ipv6(hex_addr: str) -> str:
    """Convert a 32-character hex string from /proc/net/tcp6 to an IPv6 string."""
    try:
        raw_bytes = bytes.fromhex(hex_addr)
        # Parse 4 32-bit words in network or host byte order
        words = struct.unpack("<4I", raw_bytes)
        packed = struct.pack(">4I", *words)
        return socket.inet_ntop(socket.AF_INET6, packed)
    except Exception:
        return hex_addr


def _build_linux_inode_pid_map() -> dict[int, int]:
    """Scan /proc/[pid]/fd/* to map socket inodes to process PIDs (Linux only)."""
    inode_to_pid: dict[int, int] = {}
    proc_dir = "/proc"
    if not os.path.isdir(proc_dir):
        return inode_to_pid

    socket_pattern = re.compile(r"^socket:\[(\d+)\]$")

    for pid_entry in os.listdir(proc_dir):
        if not pid_entry.isdigit():
            continue
        pid = int(pid_entry)
        fd_dir = os.path.join(proc_dir, pid_entry, "fd")
        try:
            for fd in os.listdir(fd_dir):
                fd_path = os.path.join(fd_dir, fd)
                try:
                    target = os.readlink(fd_path)
                    match = socket_pattern.match(target)
                    if match:
                        inode = int(match.group(1))
                        inode_to_pid[inode] = pid
                except (OSError, ValueError):
                    continue
        except (OSError, PermissionError):
            continue

    return inode_to_pid


def scan_linux_procfs(protocol: str = "all") -> list[SocketInfo]:
    """Pure-Python /proc/net/tcp parser. Works on Linux without spawning subshells."""
    sockets: list[SocketInfo] = []
    inode_pid_map: dict[int, int] | None = None

    scan_targets = []
    if protocol in ("all", "tcp"):
        scan_targets.extend(
            [
                ("/proc/net/tcp", "tcp", False),
                ("/proc/net/tcp6", "tcp6", True),
            ]
        )
    if protocol in ("all", "udp"):
        scan_targets.extend(
            [
                ("/proc/net/udp", "udp", False),
                ("/proc/net/udp6", "udp6", True),
            ]
        )

    for filepath, proto, is_v6 in scan_targets:
        if not os.path.isfile(filepath):
            continue

        try:
            with open(filepath, encoding="ascii", errors="replace") as f:
                lines = f.readlines()
        except (OSError, PermissionError):
            continue

        if len(lines) <= 1:
            continue

        # Lazy load inode_pid_map only if we found lines
        if inode_pid_map is None:
            inode_pid_map = _build_linux_inode_pid_map()

        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) < 10:
                continue

            # Local address is part 1: "0100007F:0BB8"
            local_addr_part = parts[1]
            state_hex = parts[3]
            inode_str = parts[9]

            # In /proc/net/tcp, 0A is TCP_LISTEN (10 in decimal)
            # For UDP, state is often 07 (TCP_CLOSE) or others, but it represents active bind
            if proto.startswith("tcp") and state_hex != "0A":
                continue

            if ":" not in local_addr_part:
                continue

            hex_ip, hex_port = local_addr_part.split(":", 1)
            try:
                port = int(hex_port, 16)
            except ValueError:
                continue

            ip = _parse_hex_ipv6(hex_ip) if is_v6 else _parse_hex_ipv4(hex_ip)
            # Simplify standard listen addresses
            if ip == "0.0.0.0" or ip == "::":
                pass
            elif ip == "127.0.0.1":
                pass

            inode = int(inode_str) if inode_str.isdigit() else None
            pid = inode_pid_map.get(inode) if inode else None

            sockets.append(
                SocketInfo(
                    protocol=proto,
                    local_address=ip,
                    local_port=port,
                    state="LISTEN",
                    pid=pid,
                    inode=inode,
                )
            )

    return sockets


def scan_linux_ss(protocol: str = "all") -> list[SocketInfo]:
    """Parse output of 'ss -tulpn' or 'ss -tlpn' on Linux."""
    sockets: list[SocketInfo] = []
    flags = "-tlpn" if protocol == "tcp" else "-tulpn"

    try:
        proc = subprocess.run(
            ["ss", flags],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
        if proc.returncode != 0 or not proc.stdout:
            return sockets
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return sockets

    # Sample output:
    # Netid State  Recv-Q Send-Q  Local Address:Port   Peer Address:PortProcess
    # tcp   LISTEN 0      128     0.0.0.0:22           0.0.0.0:*       users:(("sshd",pid=123,fd=3))
    # tcp   LISTEN 0      511     *:3000               *:*             users:(("node",pid=456,fd=19))
    # tcp   LISTEN 0      128     [::]:8080            [::]:*          users:(("java",pid=789,fd=45))

    pid_regex = re.compile(r"pid=(\d+)")
    lines = proc.stdout.splitlines()

    for line in lines:
        parts = line.split()
        if len(parts) < 5 or parts[0] in ("Netid", "State"):
            continue

        proto_name = parts[0].lower()
        state = parts[1].upper() if len(parts) > 1 else "LISTEN"
        if proto_name.startswith("tcp") and state != "LISTEN":
            continue

        # Local address is usually parts[4]
        local_raw = parts[4]
        if ":" not in local_raw:
            continue

        # Split host:port from end (handles IPv6 like [::]:8080)
        idx = local_raw.rfind(":")
        ip_str = local_raw[:idx].strip("[]*") or "0.0.0.0"
        port_str = local_raw[idx + 1 :]

        try:
            port = int(port_str)
        except ValueError:
            continue

        # Look for pid in remaining parts
        pid = None
        users_str = " ".join(parts[5:]) if len(parts) > 5 else ""
        pid_match = pid_regex.search(users_str)
        if pid_match:
            pid = int(pid_match.group(1))

        sockets.append(
            SocketInfo(
                protocol="tcp" if "tcp" in proto_name else "udp",
                local_address=ip_str,
                local_port=port,
                state="LISTEN",
                pid=pid,
            )
        )

    return sockets


def scan_macos_lsof(protocol: str = "all") -> list[SocketInfo]:
    """Parse output of 'lsof -iTCP -sTCP:LISTEN -P -n' on macOS."""
    sockets: list[SocketInfo] = []
    cmds = []
    if protocol in ("all", "tcp"):
        cmds.append(["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"])
    if protocol in ("all", "udp"):
        cmds.append(["lsof", "-iUDP", "-P", "-n"])

    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5,
            )
            if proc.returncode != 0 or not proc.stdout:
                continue
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue

        # Sample output:
        # COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
        # node    45621 user   23u  IPv6 0x...       0t0  TCP *:3000 (LISTEN)
        # python3 89123 user    4u  IPv4 0x...       0t0  TCP 127.0.0.1:8000 (LISTEN)
        lines = proc.stdout.splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue

            try:
                pid = int(parts[1])
            except ValueError:
                pid = None

            proto = parts[7].lower()
            name_col = parts[8]

            if ":" not in name_col:
                continue

            idx = name_col.rfind(":")
            addr = name_col[:idx].strip("[]*") or "0.0.0.0"
            port_str = name_col[idx + 1 :]

            try:
                port = int(port_str)
            except ValueError:
                continue

            sockets.append(
                SocketInfo(
                    protocol=proto,
                    local_address=addr,
                    local_port=port,
                    state="LISTEN",
                    pid=pid,
                )
            )

    return sockets


def scan_windows_netstat(protocol: str = "all") -> list[SocketInfo]:
    """Parse output of 'netstat -ano -p tcp' (and udp) on Windows."""
    sockets: list[SocketInfo] = []
    protocols_to_scan = []
    if protocol in ("all", "tcp"):
        protocols_to_scan.append("tcp")
    if protocol in ("all", "udp"):
        protocols_to_scan.append("udp")

    for p in protocols_to_scan:
        try:
            proc = subprocess.run(
                ["netstat", "-ano", "-p", p],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5,
            )
            if proc.returncode != 0 or not proc.stdout:
                continue
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue

        # Sample output:
        #   Proto  Local Address          Foreign Address        State           PID
        #   TCP    0.0.0.0:22             0.0.0.0:0              LISTENING       7240
        #   TCP    [::]:8080              [::]:0                 LISTENING       12345
        #   UDP    0.0.0.0:5353           *:*                                    54321
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("Proto") or line.startswith("Active"):
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            proto_col = parts[0].lower()
            if p == "tcp" and proto_col != "tcp":
                continue
            if p == "udp" and proto_col != "udp":
                continue

            local_raw = parts[1]

            if proto_col == "tcp":
                if len(parts) < 5:
                    continue
                state = parts[3].upper()
                if state != "LISTENING":
                    continue
                pid_str = parts[4]
            else:
                # UDP does not have state column
                pid_str = parts[3]
                state = "BOUND"

            try:
                pid = int(pid_str)
            except ValueError:
                pid = None

            if ":" not in local_raw:
                continue

            idx = local_raw.rfind(":")
            addr = local_raw[:idx].strip("[]") or "0.0.0.0"
            port_str = local_raw[idx + 1 :]

            try:
                port = int(port_str)
            except ValueError:
                continue

            sockets.append(
                SocketInfo(
                    protocol=proto_col,
                    local_address=addr,
                    local_port=port,
                    state="LISTEN",
                    pid=pid,
                )
            )

    return sockets


def scan_windows_nettcpconnection(protocol: str = "all") -> list[SocketInfo]:
    """Parse output of PowerShell 'Get-NetTCPConnection' and 'Get-NetUDPEndpoint' on Windows.

    Provides direct querying of the Windows TCP/IP kernel stack with structured CSV output.
    """
    import csv
    import io

    sockets: list[SocketInfo] = []

    # 1. TCP sockets via Get-NetTCPConnection
    if protocol in ("all", "tcp"):
        ps_tcp = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-NetTCPConnection -State Listen | "
            "Select-Object LocalAddress,LocalPort,OwningProcess | "
            "ConvertTo-Csv -NoTypeInformation"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_tcp],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=6,
            )
            if proc.returncode == 0 and proc.stdout:
                reader = csv.DictReader(io.StringIO(proc.stdout))
                for row in reader:
                    addr = (row.get("LocalAddress") or "").strip().strip("[]") or "0.0.0.0"
                    port_str = (row.get("LocalPort") or "").strip()
                    pid_str = (row.get("OwningProcess") or "").strip()

                    try:
                        port = int(port_str)
                    except ValueError:
                        continue

                    try:
                        pid = int(pid_str) if pid_str else None
                    except ValueError:
                        pid = None

                    sockets.append(
                        SocketInfo(
                            protocol="tcp",
                            local_address=addr,
                            local_port=port,
                            state="LISTEN",
                            pid=pid,
                        )
                    )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass

    # 2. UDP endpoints via Get-NetUDPEndpoint
    if protocol in ("all", "udp"):
        ps_udp = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-NetUDPEndpoint | "
            "Select-Object LocalAddress,LocalPort,OwningProcess | "
            "ConvertTo-Csv -NoTypeInformation"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_udp],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=6,
            )
            if proc.returncode == 0 and proc.stdout:
                reader = csv.DictReader(io.StringIO(proc.stdout))
                for row in reader:
                    addr = (row.get("LocalAddress") or "").strip().strip("[]") or "0.0.0.0"
                    port_str = (row.get("LocalPort") or "").strip()
                    pid_str = (row.get("OwningProcess") or "").strip()

                    try:
                        port = int(port_str)
                    except ValueError:
                        continue

                    try:
                        pid = int(pid_str) if pid_str else None
                    except ValueError:
                        pid = None

                    sockets.append(
                        SocketInfo(
                            protocol="udp",
                            local_address=addr,
                            local_port=port,
                            state="LISTEN",
                            pid=pid,
                        )
                    )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass

    return sockets


def scan_listening_sockets(
    ports: list[int] | None = None,
    protocol: str = "all",
) -> list[SocketInfo]:
    """Scan and return all active listening sockets on the local machine.

    Dispatches across Linux, macOS, and Windows with multi-strategy fallbacks.
    """
    raw_sockets: list[SocketInfo] = []

    if sys.platform.startswith("linux"):
        # Strategy 1: /proc/net/tcp (Pure Python, fast, zero subprocess)
        try:
            raw_sockets = scan_linux_procfs(protocol=protocol)
        except Exception:
            raw_sockets = []

        # If procfs didn't resolve PIDs (e.g. non-root), try 'ss'
        has_missing_pids = any(s.pid is None for s in raw_sockets)
        if not raw_sockets or has_missing_pids:
            ss_sockets = scan_linux_ss(protocol=protocol)
            if ss_sockets:
                raw_sockets = ss_sockets

        # If ss failed, try lsof
        if not raw_sockets:
            raw_sockets = scan_macos_lsof(protocol=protocol)

    elif sys.platform == "darwin":
        raw_sockets = scan_macos_lsof(protocol=protocol)

    elif sys.platform.startswith("win"):
        raw_sockets = scan_windows_netstat(protocol=protocol)
        # If netstat returned nothing or had missing PIDs, augment with Get-NetTCPConnection
        has_missing_pids = any(s.pid is None for s in raw_sockets)
        if not raw_sockets or has_missing_pids:
            ps_sockets = scan_windows_nettcpconnection(protocol=protocol)
            if ps_sockets:
                if not raw_sockets:
                    raw_sockets = ps_sockets
                else:
                    # Fill missing PIDs from PowerShell structured query
                    pid_lookup = {(s.protocol, s.local_port): s.pid for s in ps_sockets if s.pid}
                    for s in raw_sockets:
                        if s.pid is None:
                            s.pid = pid_lookup.get((s.protocol, s.local_port))

    else:
        # Fallback for BSD / others
        raw_sockets = scan_macos_lsof(protocol=protocol)

    # Deduplicate sockets by (protocol, local_address, local_port, pid)
    seen: set[str] = set()
    deduped: list[SocketInfo] = []

    for s in raw_sockets:
        key = f"{s.protocol.lower()}:{s.local_address}:{s.local_port}:{s.pid}"
        if key in seen:
            continue
        seen.add(key)

        if ports and s.local_port not in ports:
            continue

        deduped.append(s)

    # Sort primarily by port number, then address
    deduped.sort(key=lambda x: (x.local_port, x.local_address))
    return deduped
