"""Process tree resolver and Git repository contextualizer.

Maps listening PIDs to process names, full command lines, working directories,
parent/child worker hierarchies, and active Git branches without external packages.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from porttree.config import ProcessNode


def find_git_info(cwd: str | None) -> tuple[str | None, str | None]:
    """Determine the active Git branch and repository name for a working directory.

    Pure-Python implementation that traverses parent directories and inspects
    .git/HEAD. Works for standard repos, submodules, and worktrees.
    Returns (branch_name, repo_name) or (None, None).
    """
    if not cwd:
        return None, None

    try:
        current_path = Path(cwd).resolve()
    except (OSError, RuntimeError):
        return None, None

    # If current_path doesn't exist, walk up until we find an existing directory
    while not current_path.exists() and current_path != current_path.parent:
        current_path = current_path.parent

    for directory in [current_path, *current_path.parents]:
        git_target = directory / ".git"
        if not git_target.exists():
            continue

        repo_name = directory.name
        head_path: Path | None = None

        if git_target.is_dir():
            head_path = git_target / "HEAD"
        elif git_target.is_file():
            # Git submodule or worktree: .git is a file containing "gitdir: <path>"
            try:
                content = git_target.read_text(encoding="utf-8", errors="replace").strip()
                if content.startswith("gitdir:"):
                    raw_dir = content[len("gitdir:") :].strip()
                    raw_path = Path(raw_dir)
                    if raw_path.is_absolute():
                        git_dir = raw_path.resolve()
                    else:
                        git_dir = (directory / raw_dir).resolve()
                    head_path = git_dir / "HEAD"
            except (OSError, UnicodeDecodeError):
                pass

        if head_path and head_path.is_file():
            try:
                head_content = head_path.read_text(encoding="utf-8", errors="replace").strip()
                if head_content.startswith("ref: refs/heads/"):
                    branch = head_content[len("ref: refs/heads/") :]
                    return branch, repo_name
                if head_content.startswith("ref: refs/tags/"):
                    tag = head_content[len("ref: refs/tags/") :]
                    return f"tag:{tag}", repo_name
                if head_content.startswith("ref: refs/remotes/"):
                    remote = head_content[len("ref: refs/remotes/") :]
                    return f"remote:{remote}", repo_name
                if head_content.startswith("ref: refs/"):
                    ref = head_content[len("ref: refs/") :]
                    return ref, repo_name
                if re.match(r"^[0-9a-fA-F]{7,64}$", head_content):
                    # Detached HEAD (supports SHA-1 and SHA-256)
                    return f"detached:{head_content[:7]}", repo_name
            except (OSError, UnicodeDecodeError):
                return None, repo_name

        return None, repo_name

    return None, None


class ProcessResolver:
    """Dispatches process inspection and builds process trees across OS platforms."""

    def __init__(self, resolve_git: bool = True):
        self.resolve_git = resolve_git
        self._cache: dict[int, ProcessNode] = {}
        self._all_processes_loaded = False

    def get_process_node(self, pid: int) -> ProcessNode | None:
        """Fetch or build a ProcessNode for a given PID with children attached."""
        if not self._all_processes_loaded:
            self._load_all_processes()

        node = self._cache.get(pid)
        if not node:
            # Fallback single-process lookup
            node = self._fetch_single_process(pid)
            if node:
                self._cache[pid] = node

        if node and self.resolve_git and not node.git_branch:
            node.git_branch, node.git_repo = self._resolve_git_for_node(node)

        return node

    def _resolve_git_for_node(self, node: ProcessNode) -> tuple[str | None, str | None]:
        """Resolve Git branch and repository name for a process node using multiple strategies."""
        # Strategy 1: Check node.cwd if it exists
        if node.cwd:
            branch, repo = find_git_info(node.cwd)
            if branch:
                return branch, repo

        # Strategy 2: Extract candidate paths from command-line arguments
        candidates = self._extract_candidate_paths(node)
        for cand in candidates:
            branch, repo = find_git_info(cand)
            if branch:
                return branch, repo

        # Strategy 3: Check current working directory of caller if node seems local
        try:
            cwd = Path.cwd()
            branch, repo = find_git_info(str(cwd))
            if branch and repo and node.cmdline:
                for token in node.args:
                    clean_token = token.strip("\"' ")
                    if clean_token and (cwd / clean_token).exists():
                        return branch, repo
        except Exception:
            pass

        return None, None

    @staticmethod
    def _extract_candidate_paths(node: ProcessNode) -> list[str]:
        """Extract candidate directory paths from process command-line arguments."""
        candidates: list[str] = []
        tokens = list(node.args) if node.args else ([node.cmdline] if node.cmdline else [])
        for token in tokens:
            cleaned = token.strip("\"' ")
            if not cleaned or len(cleaned) < 2:
                continue

            try:
                p = Path(cleaned)
                if p.is_file():
                    candidates.append(str(p.parent.resolve()))
                elif p.is_dir():
                    candidates.append(str(p.resolve()))
            except (OSError, ValueError):
                continue

        return candidates

    def build_full_tree(self, pid: int, include_ancestors: bool = True) -> ProcessNode | None:
        """Build the full process tree for a listening PID.

        If include_ancestors is True and a relevant parent (e.g., nodemon, npm, cargo)
        exists, roots the tree at the ancestor while pointing out the socket owner.
        """
        node = self.get_process_node(pid)
        if not node:
            return None

        # Build child hierarchy
        self._attach_children(node)

        # Check if parent is a dev runner (e.g., nodemon, yarn, npm, docker)
        if include_ancestors and node.ppid and node.ppid > 1:
            parent = self.get_process_node(node.ppid)
            if parent and parent.pid != node.pid:
                # If parent is an orchestration tool, we can nest under it
                p_name = parent.name.lower()
                if any(
                    k in p_name
                    for k in ("node", "npm", "yarn", "pnpm", "nodemon", "python", "cargo", "docker")
                ):
                    # Avoid cyclic infinite loops
                    if node not in parent.children:
                        parent.children.append(node)
                    return parent

        return node

    def _attach_children(self, node: ProcessNode) -> None:
        """Find all processes that have ppid == node.pid and attach them."""
        if not self._all_processes_loaded:
            self._load_all_processes()

        children = [p for p in self._cache.values() if p.ppid == node.pid and p.pid != node.pid]
        node.children = children
        for child in children:
            if self.resolve_git and not child.git_branch:
                child.git_branch, child.git_repo = self._resolve_git_for_node(child)
            self._attach_children(child)

    def _load_all_processes(self) -> None:
        """Load all system processes into cache using OS-optimized bulk commands."""
        self._all_processes_loaded = True

        if sys.platform.startswith("linux"):
            self._load_linux_procfs()
        elif sys.platform == "darwin":
            self._load_macos_ps()
        elif sys.platform.startswith("win"):
            self._load_windows_processes()

    def _load_linux_procfs(self) -> None:
        """Read all processes directly from /proc on Linux."""
        proc_dir = "/proc"
        if not os.path.isdir(proc_dir):
            return

        for entry in os.listdir(proc_dir):
            if not entry.isdigit():
                continue
            pid = int(entry)
            p_dir = os.path.join(proc_dir, entry)

            name = ""
            ppid: int | None = None
            # Read status for Name and PPid
            status_file = os.path.join(p_dir, "status")
            try:
                with open(status_file, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.startswith("Name:"):
                            name = line.split(":", 1)[1].strip()
                        elif line.startswith("PPid:"):
                            ppid_str = line.split(":", 1)[1].strip()
                            if ppid_str.isdigit():
                                ppid = int(ppid_str)
            except (OSError, PermissionError):
                pass

            # Read cmdline
            cmdline = ""
            args: list[str] = []
            cmdline_file = os.path.join(p_dir, "cmdline")
            try:
                with open(cmdline_file, "rb") as f:
                    raw_cmd = f.read()
                    if raw_cmd:
                        args = [
                            p.decode("utf-8", errors="replace") for p in raw_cmd.split(b"\x00") if p
                        ]
                        cmdline = " ".join(args)
            except (OSError, PermissionError):
                pass

            if not name and args:
                name = os.path.basename(args[0])

            # Read cwd
            cwd: str | None = None
            cwd_link = os.path.join(p_dir, "cwd")
            try:
                cwd = os.readlink(cwd_link)
            except (OSError, PermissionError):
                pass

            self._cache[pid] = ProcessNode(
                pid=pid,
                ppid=ppid,
                name=name,
                cmdline=cmdline,
                args=args,
                cwd=cwd,
            )

    def _load_macos_ps(self) -> None:
        """Read all processes using 'ps -eo pid,ppid,user,comm,args' on macOS."""
        try:
            proc = subprocess.run(
                ["ps", "-eo", "pid,ppid,user,comm,args"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5,
            )
            if proc.returncode != 0 or not proc.stdout:
                return
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return

        lines = proc.stdout.splitlines()
        for line in lines[1:]:
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue

            try:
                pid = int(parts[0])
                ppid = int(parts[1])
            except ValueError:
                continue

            user = parts[2]
            comm = parts[3]
            args_str = parts[4] if len(parts) > 4 else comm
            name = os.path.basename(comm)

            self._cache[pid] = ProcessNode(
                pid=pid,
                ppid=ppid,
                name=name,
                cmdline=args_str,
                args=shlex.split(args_str) if args_str else [comm],
                user=user,
            )

    def _load_windows_processes(self) -> None:
        """Read all processes on Windows using PowerShell Get-CimInstance or tasklist."""
        # Method 1: PowerShell Get-CimInstance Win32_Process
        ps_cmd = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId,Name,CommandLine,ExecutablePath | "
            "ConvertTo-Csv -NoTypeInformation"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=8,
            )
            if proc.returncode == 0 and proc.stdout:
                reader = csv.DictReader(io.StringIO(proc.stdout))
                for row in reader:
                    pid_str = row.get("ProcessId", "")
                    if not pid_str or not pid_str.isdigit():
                        continue
                    pid = int(pid_str)

                    ppid_str = row.get("ParentProcessId", "")
                    ppid = int(ppid_str) if ppid_str and ppid_str.isdigit() else None

                    name = row.get("Name", "") or ""
                    cmdline = row.get("CommandLine", "") or ""
                    exe_path = row.get("ExecutablePath", "") or ""

                    cwd = os.path.dirname(exe_path) if exe_path else None

                    self._cache[pid] = ProcessNode(
                        pid=pid,
                        ppid=ppid,
                        name=name,
                        cmdline=cmdline,
                        args=shlex.split(cmdline, posix=False) if cmdline else [name],
                        cwd=cwd,
                    )
                return
        except Exception:
            pass

        # Method 2: Tasklist CSV fallback
        try:
            proc = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout:
                reader = csv.reader(io.StringIO(proc.stdout))
                for row in reader:
                    if len(row) < 2:
                        continue
                    name = row[0]
                    pid_str = row[1]
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        self._cache[pid] = ProcessNode(
                            pid=pid,
                            name=name,
                            cmdline=name,
                            args=[name],
                        )
        except Exception:
            pass

    def _fetch_single_process(self, pid: int) -> ProcessNode | None:
        """Fetch info for a single PID on demand."""
        if sys.platform.startswith("linux"):
            p_dir = f"/proc/{pid}"
            if not os.path.isdir(p_dir):
                return None
            name = ""
            ppid: int | None = None
            try:
                with open(f"{p_dir}/status", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.startswith("Name:"):
                            name = line.split(":", 1)[1].strip()
                        elif line.startswith("PPid:"):
                            val = line.split(":", 1)[1].strip()
                            if val.isdigit():
                                ppid = int(val)
            except OSError:
                pass

            cmdline = ""
            args: list[str] = []
            try:
                with open(f"{p_dir}/cmdline", "rb") as f:
                    raw = f.read()
                    if raw:
                        args = [
                            p.decode("utf-8", errors="replace") for p in raw.split(b"\x00") if p
                        ]
                        cmdline = " ".join(args)
            except OSError:
                pass

            cwd: str | None = None
            try:
                cwd = os.readlink(f"{p_dir}/cwd")
            except OSError:
                pass

            return ProcessNode(
                pid=pid,
                ppid=ppid,
                name=name or (args[0] if args else f"pid-{pid}"),
                cmdline=cmdline,
                args=args,
                cwd=cwd,
            )

        return None
