"""Windows NAT / Hyper-V / WSL2 Dynamic Port Exclusion detector for PortTree.

Diagnoses 'address already in use' (EADDRINUSE / WinError 10013) issues caused by
Windows kernel dynamic port exclusions where no user-space PID exists in netstat.
"""

from __future__ import annotations

import re
import subprocess
import sys

from porttree.config import Colors, ExcludedPortRange


def is_windows() -> bool:
    """Return True if running on Windows."""
    return sys.platform.startswith("win")


def get_windows_port_exclusions(protocol: str = "tcp") -> list[ExcludedPortRange]:
    """Retrieve all active Windows port exclusion ranges via netsh."""
    if not is_windows():
        return []

    ranges: list[ExcludedPortRange] = []
    protos = ["tcp"] if protocol == "tcp" else (["udp"] if protocol == "udp" else ["tcp", "udp"])

    for proto in protos:
        for ip_ver in ("ipv4", "ipv6"):
            cmd = ["netsh", "int", ip_ver, "show", "excludedportrange", f"protocol={proto}"]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=4,
                )
                if proc.returncode != 0 or not proc.stdout:
                    continue
            except (FileNotFoundError, OSError, subprocess.SubprocessError):
                continue

            ranges.extend(_parse_netsh_output(proc.stdout, proto))

    # Deduplicate ranges
    unique: list[ExcludedPortRange] = []
    seen = set()
    for r in ranges:
        key = (r.start_port, r.end_port, r.protocol)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda r: r.start_port)
    return unique


def _parse_netsh_output(output: str, protocol: str) -> list[ExcludedPortRange]:
    """Parse table output from 'netsh int ... show excludedportrange'."""
    ranges: list[ExcludedPortRange] = []
    lines = output.splitlines()

    # Look for lines with two integers, optional '*'
    line_pattern = re.compile(r"^\s*(\d+)\s+(\d+)\s*(\*)?")

    in_table = False
    for line in lines:
        line = line.strip()
        if "Start Port" in line and "End Port" in line:
            in_table = True
            continue
        if "---" in line:
            continue
        if not in_table or not line:
            continue

        match = line_pattern.match(line)
        if match:
            start_p = int(match.group(1))
            end_p = int(match.group(2))
            is_admin = bool(match.group(3))
            ranges.append(
                ExcludedPortRange(
                    start_port=start_p,
                    end_port=end_p,
                    administered=is_admin,
                    protocol=protocol,
                )
            )

    return ranges


def check_port_exclusion(port: int, protocol: str = "tcp") -> ExcludedPortRange | None:
    """Check if a port falls within any active Windows dynamic port exclusions."""
    if not is_windows():
        return None

    for r in get_windows_port_exclusions(protocol=protocol):
        if r.contains(port):
            return r

    return None


def format_winnat_diagnosis(port: int, exclusion: ExcludedPortRange) -> str:
    """Format an actionable diagnostic report with root cause and fix commands."""
    lines = [
        f"{Colors.warn('⚠️  Port')} {Colors.port(str(port))} {Colors.warn('is reserved by Windows Kernel (Hyper-V / WinNAT / WSL2)')}",
        f"   {Colors.dim('Range:')} {exclusion.start_port} – {exclusion.end_port} ({exclusion.protocol.upper()})"
        + (" [Administered]" if exclusion.administered else " [Dynamic Kernel Pool]"),
        "",
        f"   {Colors.BOLD}Root Cause:{Colors.RESET}",
        "   Windows NAT (WinNAT) or Hyper-V reserved this port range for internal container/WSL2 routing.",
        "   No user-space PID exists in netstat or Task Manager, yet socket binds fail with EADDRINUSE (WinError 10013).",
        "",
        f"   {Colors.BOLD}Recommended Solutions:{Colors.RESET}",
        f"   1. {Colors.proc('Restart WinNAT')} (instant fix, frees reserved pool):",
        "      " + Colors.dim('powershell -Command "net stop winnat; net start winnat"'),
        "",
        f"   2. {Colors.proc('Reconfigure dynamic port pool')} (prevents future collision with dev ports):",
        "      " + Colors.dim("netsh int ipv4 set dynamicport tcp start=49152 num=16384"),
        "",
        f"   3. {Colors.proc('Restart Host Network Service')} (if running Docker/WSL2):",
        "      " + Colors.dim("net stop hns && net start hns"),
    ]
    return "\n".join(lines)
