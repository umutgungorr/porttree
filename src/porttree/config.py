"""Configuration, data models, and ANSI formatting utilities for PortTree.

Zero external dependencies - pure Python 3.9+ standard library.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


class Colors:
    """ANSI color codes with automatic terminal and NO_COLOR detection."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"

    _enabled = True

    @classmethod
    def init(cls, force_color: bool = False, no_color: bool = False) -> None:
        """Initialize color support based on terminal, NO_COLOR, and flags."""
        if no_color or "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
            cls.disable()
            return

        if force_color:
            cls.enable()
            return

        # Auto-detect TTY
        is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        if is_tty:
            cls.enable()
        else:
            cls.disable()

    @classmethod
    def enable(cls) -> None:
        """Enable ANSI styling."""
        cls._enabled = True

    @classmethod
    def disable(cls) -> None:
        """Disable ANSI styling (strip all codes)."""
        cls._enabled = False

    @classmethod
    def is_enabled(cls) -> bool:
        """Return whether color output is active."""
        return cls._enabled

    @classmethod
    def style(cls, text: str, *codes: str) -> str:
        """Wrap text in one or more ANSI codes if styling is active."""
        if not cls._enabled or not codes:
            return text
        prefix = "".join(codes)
        return f"{prefix}{text}{cls.RESET}"

    # Pre-styled convenience helpers
    @classmethod
    def port(cls, text: str) -> str:
        return cls.style(text, cls.BOLD, cls.BRIGHT_CYAN)

    @classmethod
    def proc(cls, text: str) -> str:
        return cls.style(text, cls.BOLD, cls.BRIGHT_GREEN)

    @classmethod
    def pid(cls, text: str) -> str:
        return cls.style(text, cls.YELLOW)

    @classmethod
    def git(cls, text: str) -> str:
        return cls.style(text, cls.MAGENTA)

    @classmethod
    def docker(cls, text: str) -> str:
        return cls.style(text, cls.BRIGHT_BLUE)

    @classmethod
    def warn(cls, text: str) -> str:
        return cls.style(text, cls.BOLD, cls.BRIGHT_YELLOW)

    @classmethod
    def error(cls, text: str) -> str:
        return cls.style(text, cls.BOLD, cls.BRIGHT_RED)

    @classmethod
    def success(cls, text: str) -> str:
        return cls.style(text, cls.BOLD, cls.BRIGHT_GREEN)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls.style(text, cls.DIM)


@dataclass
class SocketInfo:
    """Represents a network socket listening on a local port."""

    protocol: str  # "tcp", "udp", "tcp4", "tcp6", etc.
    local_address: str  # "0.0.0.0", "127.0.0.1", "::", etc.
    local_port: int
    remote_address: str | None = None
    remote_port: int | None = None
    state: str = "LISTEN"
    pid: int | None = None
    inode: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "local_address": self.local_address,
            "local_port": self.local_port,
            "remote_address": self.remote_address,
            "remote_port": self.remote_port,
            "state": self.state,
            "pid": self.pid,
            "inode": self.inode,
        }


@dataclass
class DockerContainerInfo:
    """Detailed metadata for a Docker container unmasked from docker-proxy."""

    container_id: str
    name: str
    image: str
    compose_project: str | None = None
    compose_service: str | None = None
    compose_workdir: str | None = None
    ports: list[str] = field(default_factory=list)
    status: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "name": self.name,
            "image": self.image,
            "compose_project": self.compose_project,
            "compose_service": self.compose_service,
            "compose_workdir": self.compose_workdir,
            "ports": self.ports,
            "status": self.status,
        }


@dataclass
class ProcessNode:
    """Represents a process and its hierarchically attached child processes."""

    pid: int
    ppid: int | None = None
    name: str = ""
    cmdline: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    git_branch: str | None = None
    git_repo: str | None = None
    user: str | None = None
    children: list[ProcessNode] = field(default_factory=list)
    docker_info: DockerContainerInfo | None = None

    def all_pids(self) -> list[int]:
        """Return list of this PID and all descendant child PIDs."""
        pids = [self.pid]
        for child in self.children:
            pids.extend(child.all_pids())
        return pids

    def to_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "name": self.name,
            "cmdline": self.cmdline,
            "args": self.args,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "git_repo": self.git_repo,
            "user": self.user,
            "children": [c.to_dict() for c in self.children],
            "docker_info": self.docker_info.to_dict() if self.docker_info else None,
        }


@dataclass
class ExcludedPortRange:
    """Represents a Windows Hyper-V / WSL2 Dynamic Port Exclusion range."""

    start_port: int
    end_port: int
    administered: bool = False
    protocol: str = "tcp"

    def contains(self, port: int) -> bool:
        return self.start_port <= port <= self.end_port

    def to_dict(self) -> dict[str, object]:
        return {
            "start_port": self.start_port,
            "end_port": self.end_port,
            "administered": self.administered,
            "protocol": self.protocol,
        }


@dataclass
class PortEntry:
    """Aggregated representation of an open or reserved port."""

    port: int
    protocol: str
    sockets: list[SocketInfo] = field(default_factory=list)
    process: ProcessNode | None = None
    docker_info: DockerContainerInfo | None = None
    exclusion: ExcludedPortRange | None = None
    is_conflict: bool = False
    source_file: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "port": self.port,
            "protocol": self.protocol,
            "sockets": [s.to_dict() for s in self.sockets],
            "process": self.process.to_dict() if self.process else None,
            "docker_info": self.docker_info.to_dict() if self.docker_info else None,
            "exclusion": self.exclusion.to_dict() if self.exclusion else None,
            "is_conflict": self.is_conflict,
            "source_file": self.source_file,
        }


@dataclass
class DeclaredPort:
    """A port declared in a project configuration file (compose, package.json, .env)."""

    port: int
    protocol: str = "tcp"
    source_file: str = ""
    context: str = ""  # e.g., service name or script key
