"""Graceful process tree killer for PortTree.

Terminates parent and all child workers (SIGTERM with timeout, then SIGKILL)
to eliminate orphaned zombie processes holding ports.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field

from porttree.scanner import scan_listening_sockets
from porttree.tree import ProcessResolver
from porttree.winnat import check_port_exclusion, format_winnat_diagnosis


@dataclass
class KillResult:
    """Outcome of a kill or free operation on a port."""

    port: int
    success: bool
    killed_pids: list[int] = field(default_factory=list)
    process_names: list[str] = field(default_factory=list)
    message: str = ""
    dry_run: bool = False
    is_winnat_reserved: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "port": self.port,
            "success": self.success,
            "killed_pids": self.killed_pids,
            "process_names": self.process_names,
            "message": self.message,
            "dry_run": self.dry_run,
            "is_winnat_reserved": self.is_winnat_reserved,
        }


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if pid <= 0:
        return False

    if sys.platform.startswith("win"):
        # On Windows, try tasklist or OpenProcess
        try:
            res = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            return str(pid) in res.stdout
        except Exception:
            return False
    else:
        # On POSIX, signal 0 checks for process existence without sending a signal
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists, but we don't have permission to signal it
            return True


def _terminate_pid(pid: int, force: bool = False) -> bool:
    """Send SIGTERM or SIGKILL to a PID depending on OS and force flag."""
    if pid <= 0:
        return False

    if sys.platform.startswith("win"):
        # Windows: taskkill /PID or /F /T /PID
        cmd = ["taskkill"]
        if force:
            cmd.extend(["/F", "/T"])
        cmd.extend(["/PID", str(pid)])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=3)
            return res.returncode == 0
        except Exception:
            return False
    else:
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.kill(pid, sig)
            return True
        except ProcessLookupError:
            return True
        except PermissionError:
            return False


def kill_port(
    port: int,
    force: bool = False,
    timeout: float = 3.0,
    dry_run: bool = False,
    auto_confirm: bool = False,
) -> KillResult:
    """Terminate the entire process tree holding a port.

    Args:
        port: The target port number.
        force: If True, escalate straight to SIGKILL / taskkill /F.
        timeout: Seconds to wait for SIGTERM before escalating to SIGKILL.
        dry_run: If True, returns preview of actions without terminating.
        auto_confirm: If False and interactive, prompts user for confirmation.
    """
    # 1. Scan the port for listening sockets
    sockets = scan_listening_sockets(ports=[port])
    if not sockets:
        # Check if Windows Dynamic Port Exclusion is holding it
        exclusion = check_port_exclusion(port)
        if exclusion:
            diag = format_winnat_diagnosis(port, exclusion)
            return KillResult(
                port=port,
                success=False,
                message=diag,
                is_winnat_reserved=True,
            )
        return KillResult(
            port=port,
            success=True,
            message=f"Port {port} is not in use.",
        )

    # 2. Collect listening PIDs
    listening_pids: set[int] = {s.pid for s in sockets if s.pid and s.pid > 0}
    if not listening_pids:
        return KillResult(
            port=port,
            success=False,
            message=f"Port {port} is open, but owning PID could not be determined (try running with sudo / Administrator).",
        )

    # 3. Resolve full process tree (children + parent)
    resolver = ProcessResolver(resolve_git=False)
    pids_to_kill: list[int] = []
    process_names: list[str] = []

    for l_pid in listening_pids:
        node = resolver.build_full_tree(l_pid, include_ancestors=False)
        if node:
            all_tree_pids = node.all_pids()
            # Order: children first, then parent
            children_pids = [p for p in all_tree_pids if p != l_pid]
            pids_to_kill.extend(children_pids)
            pids_to_kill.append(l_pid)
            process_names.append(node.name or f"PID {node.pid}")
            for c in node.children:
                process_names.append(c.name or f"PID {c.pid}")
        else:
            pids_to_kill.append(l_pid)
            process_names.append(f"PID {l_pid}")

    # Deduplicate while preserving kill order (children before root)
    ordered_pids: list[int] = []
    seen = set()
    for p in reversed(pids_to_kill):
        if p not in seen:
            seen.add(p)
            ordered_pids.append(p)
    ordered_pids.reverse()

    # 4. Dry Run Mode
    if dry_run:
        return KillResult(
            port=port,
            success=True,
            killed_pids=ordered_pids,
            process_names=process_names,
            message=f"[Dry Run] Would terminate {len(ordered_pids)} process(es) holding port {port}: {ordered_pids}",
            dry_run=True,
        )

    # 5. Interactive confirmation if needed
    if not auto_confirm and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
        prompt_text = (
            f"Port {port} is held by {len(ordered_pids)} process(es) "
            f"({', '.join(process_names[:3])}{'...' if len(process_names) > 3 else ''}).\n"
            f"Terminate process tree [PID {', '.join(str(p) for p in ordered_pids)}]? [y/N]: "
        )
        try:
            choice = input(prompt_text).strip().lower()
            if choice not in ("y", "yes"):
                return KillResult(
                    port=port,
                    success=False,
                    message="Operation aborted by user.",
                )
        except (EOFError, KeyboardInterrupt):
            return KillResult(
                port=port,
                success=False,
                message="Operation cancelled.",
            )

    # 6. Step 1: Graceful termination (or force if requested)
    for p in ordered_pids:
        _terminate_pid(p, force=force)

    # 7. Step 2: Poll for graceful exit up to timeout
    if not force:
        start_time = time.time()
        while time.time() - start_time < timeout:
            alive = [p for p in ordered_pids if _is_pid_alive(p)]
            if not alive:
                break
            time.sleep(0.1)

        # 8. Step 3: Escalate to SIGKILL for any stubborn survivors
        still_alive = [p for p in ordered_pids if _is_pid_alive(p)]
        for p in still_alive:
            _terminate_pid(p, force=True)

    # 9. Step 4: Verification re-scan
    time.sleep(0.15)
    remaining_sockets = scan_listening_sockets(ports=[port])
    if not remaining_sockets:
        return KillResult(
            port=port,
            success=True,
            killed_pids=ordered_pids,
            process_names=process_names,
            message=f"Successfully freed port {port}. Terminated {len(ordered_pids)} process(es).",
        )
    else:
        remaining_pids = [s.pid for s in remaining_sockets if s.pid]
        return KillResult(
            port=port,
            success=False,
            killed_pids=ordered_pids,
            process_names=process_names,
            message=(
                f"Failed to completely free port {port}. "
                f"Still occupied by PID(s): {remaining_pids}. Elevated privileges may be required."
            ),
        )
