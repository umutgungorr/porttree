"""Command-line interface for PortTree.

Zero-dependency CLI providing instant port scanning, process tree visualization,
Docker unmasking, Windows Dynamic Port Exclusion diagnostics, graceful tree killing,
and pre-flight stack checking.
"""

from __future__ import annotations

import argparse
import sys

from porttree import __version__
from porttree.checker import check_preflight
from porttree.config import Colors, ExcludedPortRange, PortEntry
from porttree.docker import DockerUnmasker
from porttree.formatter import TreeFormatter
from porttree.killer import kill_port
from porttree.scanner import scan_listening_sockets
from porttree.tree import ProcessResolver
from porttree.winnat import (
    check_port_exclusion,
    format_winnat_diagnosis,
    get_windows_port_exclusions,
    is_windows,
)


def _parse_port_argument(port_arg: str) -> list[int]:
    """Parse port strings like '3000', '3000,8080', or '3000-3005' into a list of ints."""
    ports: list[int] = []
    if not port_arg:
        return ports

    parts = [p.strip() for p in port_arg.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            start_s, end_s = p.split("-", 1)
            try:
                start_p = int(start_s.strip())
                end_p = int(end_s.strip())
                if 1 <= start_p <= 65535 and 1 <= end_p <= 65535:
                    ports.extend(range(min(start_p, end_p), max(start_p, end_p) + 1))
            except ValueError:
                continue
        else:
            try:
                port_val = int(p)
                if 1 <= port_val <= 65535:
                    ports.append(port_val)
            except ValueError:
                continue

    return sorted(list(set(ports)))


def handle_scan(args: argparse.Namespace) -> int:
    """Handle standard socket tree scan."""
    Colors.init(
        force_color=getattr(args, "force_color", False), no_color=getattr(args, "no_color", False)
    )
    formatter = TreeFormatter(use_ascii=getattr(args, "ascii", False))

    target_ports: list[int] | None = None
    if getattr(args, "target", None):
        target_ports = _parse_port_argument(args.target)
    elif getattr(args, "port", None):
        target_ports = _parse_port_argument(args.port)

    protocol = "all"
    if getattr(args, "tcp", False):
        protocol = "tcp"
    elif getattr(args, "udp", False):
        protocol = "udp"

    sockets = scan_listening_sockets(ports=target_ports, protocol=protocol)

    # Group sockets by port
    grouped: dict[int, list] = {}
    for s in sockets:
        grouped.setdefault(s.local_port, []).append(s)

    # If specific target ports were requested and nothing was found, also check Windows exclusions
    if target_ports:
        for tp in target_ports:
            if tp not in grouped:
                grouped[tp] = []

    # Resolve processes and docker containers
    resolve_docker = not getattr(args, "no_docker", False)
    resolve_git = not getattr(args, "no_git", False)

    docker_unmasker = DockerUnmasker() if resolve_docker else None
    process_resolver = ProcessResolver(resolve_git=resolve_git)

    entries: list[PortEntry] = []
    for port in sorted(grouped.keys()):
        s_list = grouped[port]
        proto = s_list[0].protocol if s_list else "tcp"

        exclusion: ExcludedPortRange | None = None
        if is_windows():
            exclusion = check_port_exclusion(port, protocol=proto)

        if not s_list and not exclusion:
            continue

        entry = PortEntry(
            port=port,
            protocol=proto,
            sockets=s_list,
            exclusion=exclusion,
        )

        if docker_unmasker:
            entry.docker_info = docker_unmasker.get_container_for_port(port, protocol=proto)

        # Resolve process node if PID available
        owning_pid = next((s.pid for s in s_list if s.pid), None)
        if owning_pid:
            proc_node = process_resolver.build_full_tree(owning_pid)
            if proc_node:
                if entry.docker_info:
                    proc_node.docker_info = entry.docker_info
                entry.process = proc_node

        entries.append(entry)

    # Render output
    if getattr(args, "json", False):
        print(formatter.render_json([e.to_dict() for e in entries]))
    elif getattr(args, "compact", False):
        print(formatter.render_compact(entries))
    else:
        print(formatter.render_tree(entries))

    return 0


def handle_kill(args: argparse.Namespace) -> int:
    """Handle port tree killing / freeing."""
    Colors.init(
        force_color=getattr(args, "force_color", False), no_color=getattr(args, "no_color", False)
    )
    formatter = TreeFormatter(use_ascii=getattr(args, "ascii", False))

    port_val: int | None = None
    target_str = getattr(args, "port_to_kill", "") or ""
    try:
        port_val = int(target_str)
    except ValueError:
        print(
            Colors.error(
                f"Error: Invalid port number '{target_str}'. Expected integer between 1 and 65535."
            )
        )
        return 2

    res = kill_port(
        port=port_val,
        force=getattr(args, "force", False),
        timeout=getattr(args, "timeout", 3.0),
        dry_run=getattr(args, "dry_run", False),
        auto_confirm=getattr(args, "yes", False),
    )

    if getattr(args, "json", False):
        print(formatter.render_json(res.to_dict()))
    else:
        print(formatter.render_kill_result(res))

    return 0 if res.success else 1


def handle_check(args: argparse.Namespace) -> int:
    """Handle pre-flight collision checking."""
    Colors.init(
        force_color=getattr(args, "force_color", False), no_color=getattr(args, "no_color", False)
    )
    formatter = TreeFormatter(use_ascii=getattr(args, "ascii", False))

    explicit_ports: list[int] | None = None
    if getattr(args, "ports", None):
        explicit_ports = _parse_port_argument(args.ports)

    files: list[str] | None = getattr(args, "files", None) or None

    result = check_preflight(files=files, explicit_ports=explicit_ports)

    if getattr(args, "json", False):
        print(formatter.render_json(result.to_dict()))
    else:
        print(formatter.render_check_result(result))

    if getattr(args, "fail", False) and result.has_conflicts:
        return 1

    return 0


def handle_winnat(args: argparse.Namespace) -> int:
    """Handle Windows NAT / Hyper-V port exclusion inspection."""
    Colors.init(
        force_color=getattr(args, "force_color", False), no_color=getattr(args, "no_color", False)
    )

    if not is_windows():
        print(
            Colors.warn(
                "Windows NAT exclusion detection is only applicable on Windows operating systems."
            )
        )
        return 0

    target = getattr(args, "port", None)
    if target:
        try:
            port_num = int(target)
        except ValueError:
            print(Colors.error(f"Invalid port: {target}"))
            return 2

        excl = check_port_exclusion(port_num)
        if excl:
            print(format_winnat_diagnosis(port_num, excl))
        else:
            print(
                f"{Colors.success('Clean:')} Port {Colors.port(str(port_num))} is not within any Windows excluded port range."
            )
        return 0

    exclusions = get_windows_port_exclusions()
    if not exclusions:
        print("No active Windows Dynamic Port Exclusion ranges detected.")
        return 0

    print(
        f"{Colors.style('Windows Dynamic Port Exclusion Ranges (WinNAT / Hyper-V)', Colors.BOLD)}"
    )
    print(Colors.dim("-" * 65))
    print(f"{'START PORT':<15} {'END PORT':<15} {'PROTOCOL':<12} {'TYPE'}")
    print(Colors.dim("-" * 65))
    for ex in exclusions:
        type_str = (
            Colors.warn("Administered (*)") if ex.administered else Colors.dim("Dynamic Pool")
        )
        print(f"{ex.start_port:<15} {ex.end_port:<15} {ex.protocol.upper():<12} {type_str}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="porttree",
        description="PortTree: Zero-dependency cross-platform socket scanner and process tree resolver.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  porttree                  # Scan all listening sockets and render process trees
  porttree 3000             # Inspect specific port 3000
  porttree 3000-3005        # Inspect port range
  porttree --compact        # Display 1-line tabular summary
  porttree --json           # Dump machine-readable JSON

Kill & Free:
  porttree free 3000        # Gracefully terminate parent and all child workers on port 3000
  porttree kill 8080 -f -y  # Force-kill without confirmation prompt

Pre-Flight Check:
  porttree check            # Auto-check docker-compose.yml, package.json, and .env
  porttree check --fail     # Exit with code 1 if any port collision is found (ideal for CI)

Windows Port Exclusions:
  porttree winnat           # List all Hyper-V/WinNAT kernel port exclusions
  porttree winnat 50025     # Diagnose why port 50025 gives EADDRINUSE without a PID
""",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"porttree {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: free / kill
    free_parser = subparsers.add_parser(
        "free",
        aliases=["kill"],
        help="Gracefully terminate parent and all child workers holding a port",
    )
    free_parser.add_argument("port_to_kill", help="Port number to free or kill")
    free_parser.add_argument(
        "-f", "--force", action="store_true", help="Escalate immediately to SIGKILL / taskkill /F"
    )
    free_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    free_parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=3.0,
        help="Graceful shutdown timeout in seconds (default: 3.0)",
    )
    free_parser.add_argument(
        "--dry-run", action="store_true", help="Preview processes to terminate without killing"
    )
    free_parser.add_argument("--json", action="store_true", help="Output result as JSON")
    free_parser.add_argument("--no-color", action="store_true", help="Disable ANSI color codes")
    free_parser.add_argument(
        "--ascii", action="store_true", help="Use ASCII characters for tree branches"
    )

    # Subcommand: check
    check_parser = subparsers.add_parser(
        "check", help="Pre-flight check files for port collisions before server startup"
    )
    check_parser.add_argument(
        "files", nargs="*", help="Config files to scan (docker-compose.yml, package.json, .env)"
    )
    check_parser.add_argument(
        "-p", "--ports", help="Additional explicit ports to check (e.g. '3000,8080')"
    )
    check_parser.add_argument(
        "--fail", action="store_true", help="Exit with non-zero code if collisions are detected"
    )
    check_parser.add_argument("--json", action="store_true", help="Output result as JSON")
    check_parser.add_argument("--no-color", action="store_true", help="Disable ANSI color codes")
    check_parser.add_argument(
        "--ascii", action="store_true", help="Use ASCII characters for tree branches"
    )

    # Subcommand: winnat
    winnat_parser = subparsers.add_parser(
        "winnat", help="Inspect Windows NAT / Hyper-V Dynamic Port Exclusions"
    )
    winnat_parser.add_argument("port", nargs="?", help="Specific port number to diagnose")
    winnat_parser.add_argument("--no-color", action="store_true", help="Disable ANSI color codes")

    # Options for default scan mode
    parser.add_argument(
        "target",
        nargs="?",
        help="Specific port (e.g. 3000), list (3000,8080), or range (3000-3010)",
    )
    parser.add_argument("-p", "--port", help="Port or port range to inspect")
    parser.add_argument("--tcp", action="store_true", help="Filter for TCP sockets only")
    parser.add_argument("--udp", action="store_true", help="Filter for UDP sockets only")
    parser.add_argument(
        "--compact", action="store_true", help="Output compact one-line tabular view"
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color codes")
    parser.add_argument(
        "--force-color", action="store_true", help="Force ANSI color codes even if not a TTY"
    )
    parser.add_argument(
        "--ascii", action="store_true", help="Use standard ASCII characters for tree branches"
    )
    parser.add_argument("--no-docker", action="store_true", help="Skip Docker container unmasking")
    parser.add_argument("--no-git", action="store_true", help="Skip Git branch resolution")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the PortTree CLI."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()

    # Special handling: if first arg is an integer, treat as default scan with target
    if (
        argv
        and argv[0].isdigit()
        and "-" not in argv[0]
        and argv[0] not in ("free", "kill", "check", "winnat")
    ):
        # Let parser handle it as target
        pass

    args = parser.parse_args(argv)

    if args.command in ("free", "kill"):
        return handle_kill(args)
    elif args.command == "check":
        return handle_check(args)
    elif args.command == "winnat":
        return handle_winnat(args)
    else:
        return handle_scan(args)


if __name__ == "__main__":
    sys.exit(main())
