"""Pre-flight stack checker for PortTree.

Scans project files (docker-compose.yml, package.json, .env) for declared ports
and flags collisions with currently running processes before server boot.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from porttree.config import DeclaredPort, PortEntry
from porttree.docker import DockerUnmasker
from porttree.scanner import scan_listening_sockets
from porttree.tree import ProcessResolver
from porttree.winnat import check_port_exclusion


@dataclass
class CheckResult:
    """Outcome of pre-flight port collision check."""

    checked_files: list[str] = field(default_factory=list)
    declared_ports: list[DeclaredPort] = field(default_factory=list)
    conflicts: list[PortEntry] = field(default_factory=list)
    clean_ports: list[DeclaredPort] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "has_conflicts": self.has_conflicts,
            "checked_files": self.checked_files,
            "conflict_count": len(self.conflicts),
            "declared_ports": [
                {
                    "port": d.port,
                    "protocol": d.protocol,
                    "source_file": d.source_file,
                    "context": d.context,
                }
                for d in self.declared_ports
            ],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "clean_ports": [
                {
                    "port": c.port,
                    "protocol": c.protocol,
                    "source_file": c.source_file,
                    "context": c.context,
                }
                for c in self.clean_ports
            ],
        }


def _extract_compose_host_ports(raw_val: str) -> list[int]:
    """Parse a docker-compose port entry and extract host port numbers."""
    val = raw_val.strip("\"' ")
    if "/" in val:
        val = val.split("/", 1)[0]

    parts = val.split(":")
    if len(parts) == 1:
        # e.g. "3000"
        host_part = parts[0]
    elif len(parts) == 2:
        # e.g. "8080:80" -> host port 8080
        host_part = parts[0]
    elif len(parts) == 3:
        # e.g. "127.0.0.1:8080:80" -> host port 8080
        host_part = parts[1]
    else:
        return []

    # Handle ranges like 9000-9002
    if "-" in host_part:
        s, e = host_part.split("-", 1)
        if s.isdigit() and e.isdigit():
            start_p, end_p = int(s), int(e)
            if 1 <= start_p <= 65535 and 1 <= end_p <= 65535:
                return list(range(min(start_p, end_p), max(start_p, end_p) + 1))
    elif host_part.isdigit():
        p_val = int(host_part)
        if 1 <= p_val <= 65535:
            return [p_val]
    return []


def parse_compose_file(file_path: Path) -> list[DeclaredPort]:
    """Extract host ports from a docker-compose.yml without external YAML dependencies."""
    declared: list[DeclaredPort] = []
    if not file_path.is_file():
        return declared

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return declared

    current_service = ""
    in_ports_block = False
    ports_indent = 0

    for line in content.splitlines():
        # Track service blocks
        service_match = re.match(r"^ {2,4}([a-zA-Z0-9_-]+):\s*$", line)
        if service_match and not line.strip().startswith("ports:"):
            current_service = service_match.group(1)
            in_ports_block = False
            continue

        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if stripped.startswith("ports:"):
            in_ports_block = True
            ports_indent = indent
            continue

        if in_ports_block:
            if (
                indent <= ports_indent
                and not stripped.startswith("-")
                and not stripped.startswith("target:")
                and not stripped.startswith("published:")
            ):
                in_ports_block = False
                continue

            # Long syntax: "published: 8080" or "published: '8080'"
            pub_match = re.search(r"published:\s*['\"]?(\d+)['\"]?", stripped)
            if pub_match:
                p = int(pub_match.group(1))
                if 1 <= p <= 65535:
                    ctx = f"service '{current_service}'" if current_service else "service"
                    declared.append(
                        DeclaredPort(
                            port=p,
                            protocol="tcp",
                            source_file=file_path.name,
                            context=ctx,
                        )
                    )
                continue

            if stripped.startswith("-"):
                port_line = stripped.lstrip("- ").strip()
                proto = "udp" if "/udp" in port_line.lower() else "tcp"
                ctx = f"service '{current_service}'" if current_service else "service"
                host_ports = _extract_compose_host_ports(port_line)
                for p in host_ports:
                    declared.append(
                        DeclaredPort(
                            port=p,
                            protocol=proto,
                            source_file=file_path.name,
                            context=ctx,
                        )
                    )

    return declared


def parse_package_json(file_path: Path) -> list[DeclaredPort]:
    """Scan scripts and config in package.json for standard port arguments (--port, -p, PORT=)."""
    declared: list[DeclaredPort] = []
    if not file_path.is_file():
        return declared

    try:
        data = json.loads(file_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return declared

    def _check_port_value(val: object, ctx: str) -> None:
        if isinstance(val, int) and 1 <= val <= 65535:
            declared.append(
                DeclaredPort(port=val, protocol="tcp", source_file=file_path.name, context=ctx)
            )
        elif isinstance(val, str) and val.isdigit() and 1 <= int(val) <= 65535:
            declared.append(
                DeclaredPort(port=int(val), protocol="tcp", source_file=file_path.name, context=ctx)
            )

    # Check top-level or config/devServer port
    if isinstance(data, dict):
        if "port" in data:
            _check_port_value(data["port"], "config 'port'")
        for section_name in ("config", "devServer", "server"):
            sec = data.get(section_name)
            if isinstance(sec, dict) and "port" in sec:
                _check_port_value(sec["port"], f"{section_name} 'port'")

    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    if not isinstance(scripts, dict):
        return declared

    port_patterns = [
        re.compile(r"(?:--port|-p)\s+([0-9]{2,5})\b"),
        re.compile(r"\bPORT=([0-9]{2,5})\b"),
        re.compile(r"--port=([0-9]{2,5})\b"),
    ]

    for script_name, cmd in scripts.items():
        if not isinstance(cmd, str):
            continue

        for pat in port_patterns:
            for match in pat.finditer(cmd):
                port = int(match.group(1))
                if 1 <= port <= 65535:
                    declared.append(
                        DeclaredPort(
                            port=port,
                            protocol="tcp",
                            source_file=file_path.name,
                            context=f"script '{script_name}'",
                        )
                    )

    return declared


def parse_env_file(file_path: Path) -> list[DeclaredPort]:
    """Scan .env files for declared port variables and localhost URLs."""
    declared: list[DeclaredPort] = []
    if not file_path.is_file():
        return declared

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return declared

    url_port_pattern = re.compile(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{2,5})")

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()

        # Strip inline comment (e.g. PORT=3000 # comment) if not within quotes
        if "#" in val and not (val.startswith(('"', "'")) and val.endswith(('"', "'"))):
            val = val.split("#", 1)[0].strip()

        # Strip enclosing quotes
        val = val.strip("\"' ")

        # Match PORT variable
        if "port" in key.lower():
            if val.isdigit():
                port = int(val)
                if 1 <= port <= 65535:
                    declared.append(
                        DeclaredPort(
                            port=port,
                            protocol="tcp",
                            source_file=file_path.name,
                            context=f"env var '{key}'",
                        )
                    )
                    continue

        # Match database/service connection URLs targeting localhost
        url_match = url_port_pattern.search(val)
        if url_match:
            port = int(url_match.group(1))
            if 1 <= port <= 65535:
                declared.append(
                    DeclaredPort(
                        port=port,
                        protocol="tcp",
                        source_file=file_path.name,
                        context=f"env url '{key}'",
                    )
                )

    return declared


def check_preflight(
    files: list[str] | None = None,
    explicit_ports: list[int] | None = None,
) -> CheckResult:
    """Perform pre-flight check across specified config files and explicit ports.

    If files is empty or None, auto-discovers docker-compose.yml, package.json,
    and .env in the current working directory.
    """
    result = CheckResult()
    target_files: list[Path] = []

    if files:
        target_files = [Path(f) for f in files]
    else:
        # Auto-discovery in cwd
        candidates = [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
            "package.json",
            ".env",
            ".env.local",
            ".env.development",
        ]
        for c in candidates:
            p = Path(c)
            if p.is_file():
                target_files.append(p)

    for p in target_files:
        if not p.is_file():
            continue

        result.checked_files.append(str(p))
        fname = p.name.lower()

        if "compose" in fname or fname.endswith((".yml", ".yaml")):
            result.declared_ports.extend(parse_compose_file(p))
        elif fname == "package.json":
            result.declared_ports.extend(parse_package_json(p))
        elif fname.startswith(".env"):
            result.declared_ports.extend(parse_env_file(p))

    # Add any explicit ports
    if explicit_ports:
        for ep in explicit_ports:
            result.declared_ports.append(
                DeclaredPort(
                    port=ep,
                    protocol="tcp",
                    source_file="cli",
                    context="explicit flag",
                )
            )

    if not result.declared_ports:
        return result

    # Deduplicate declared ports by (port, protocol)
    unique_ports: dict[int, DeclaredPort] = {}
    for dp in result.declared_ports:
        if dp.port not in unique_ports:
            unique_ports[dp.port] = dp

    target_port_numbers = list(unique_ports.keys())

    # Scan the system for currently listening sockets
    listening_sockets = scan_listening_sockets(ports=target_port_numbers)
    sockets_by_port: dict[int, list] = {}
    for s in listening_sockets:
        sockets_by_port.setdefault(s.local_port, []).append(s)

    # Initialize tools
    process_resolver = ProcessResolver(resolve_git=True)
    docker_unmasker = DockerUnmasker()

    for port, decl in unique_ports.items():
        s_list = sockets_by_port.get(port, [])
        winnat_excl = check_port_exclusion(port)

        if s_list or winnat_excl:
            # We have a collision!
            entry = PortEntry(
                port=port,
                protocol=decl.protocol,
                sockets=s_list,
                exclusion=winnat_excl,
                is_conflict=True,
                source_file=f"{decl.source_file} ({decl.context})",
            )

            # Unmask Docker container
            container = docker_unmasker.get_container_for_port(port)
            if container:
                entry.docker_info = container

            # Resolve process tree if we have a PID
            owning_pid = next((s.pid for s in s_list if s.pid), None)
            if owning_pid:
                proc_node = process_resolver.build_full_tree(owning_pid)
                if proc_node:
                    if container:
                        proc_node.docker_info = container
                    entry.process = proc_node

            result.conflicts.append(entry)
        else:
            result.clean_ports.append(decl)

    return result
