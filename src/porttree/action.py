"""GitHub Action runner for PortTree.

Reads inputs from environment, checks for port collisions or scans listening ports,
populates GITHUB_OUTPUT, and generates a formatted Markdown report in $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import os
import sys

from porttree.checker import check_preflight
from porttree.scanner import scan_listening_sockets


def set_output(name: str, value: str) -> None:
    """Write key=value to $GITHUB_OUTPUT file."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    try:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    except OSError:
        pass


def write_step_summary(markdown_text: str) -> None:
    """Write markdown summary to $GITHUB_STEP_SUMMARY."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown_text + "\n")
    except OSError:
        pass


def run_action() -> int:
    """Execute action logic."""
    raw_ports = os.environ.get("INPUT_PORTS", "").strip()
    raw_files = os.environ.get("INPUT_CHECK_FILE", "").strip()
    fail_on_conflict = os.environ.get("INPUT_FAIL_ON_CONFLICT", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    write_summary = os.environ.get("INPUT_SUMMARY", "true").lower() in ("true", "1", "yes")

    explicit_ports: list[int] | None = None
    if raw_ports:
        explicit_ports = []
        for p in raw_ports.split(","):
            p = p.strip()
            if p.isdigit():
                explicit_ports.append(int(p))

    files: list[str] | None = None
    if raw_files:
        files = [f.strip() for f in raw_files.split(",") if f.strip()]

    # If neither files nor ports were provided, perform scan of open ports
    if not explicit_ports and not files:
        all_sockets = scan_listening_sockets()
        open_ports_list = sorted(list({s.local_port for s in all_sockets}))
        ports_str = ",".join(str(p) for p in open_ports_list)

        set_output("open-ports", ports_str)
        set_output("conflict-count", "0")
        set_output("conflicts", "none")

        if write_summary:
            md = [
                "### 🌲 PortTree Socket Scan Summary",
                "",
                f"**Active Listening Ports ({len(open_ports_list)}):**",
                "",
                "| Port | Protocol | Address | PID |",
                "|---|---|---|---|",
            ]
            for s in all_sockets[:25]:
                md.append(
                    f"| `{s.local_port}` | {s.protocol.upper()} | `{s.local_address}` | `{s.pid or '-'}` |"
                )
            if len(all_sockets) > 25:
                md.append(f"| ... | ... | *({len(all_sockets) - 25} more sockets)* | ... |")
            write_step_summary("\n".join(md))

        return 0

    # Otherwise run pre-flight check
    result = check_preflight(files=files, explicit_ports=explicit_ports)

    open_sockets = scan_listening_sockets()
    open_ports_str = ",".join(str(p) for p in sorted(list({s.local_port for s in open_sockets})))

    conflict_count = len(result.conflicts)
    conflicts_str = (
        ",".join(str(c.port) for c in result.conflicts) if conflict_count > 0 else "none"
    )

    set_output("open-ports", open_ports_str)
    set_output("conflict-count", str(conflict_count))
    set_output("conflicts", conflicts_str)

    if write_summary:
        md = [
            "### 🌲 PortTree Pre-Flight Collision Report",
            "",
            f"- **Checked Files:** `{', '.join(result.checked_files) or 'auto-discovered'}`",
            f"- **Declared Ports Checked:** {len(result.declared_ports)}",
            f"- **Detected Collisions:** **{conflict_count}**",
            "",
        ]

        if result.has_conflicts:
            md.extend(
                [
                    "#### ❌ Port Collisions Detected",
                    "",
                    "| Port | Protocol | Source | Conflicting Process / Owner |",
                    "|---|---|---|---|",
                ]
            )
            for c in result.conflicts:
                proc_info = "-"
                if c.docker_info:
                    proc_info = f"🐳 Docker: `{c.docker_info.name}` ({c.docker_info.image})"
                elif c.process:
                    git_badge = f" `[{c.process.git_branch}]`" if c.process.git_branch else ""
                    proc_info = f"`{c.process.name}` (PID {c.process.pid}){git_badge}"
                elif c.exclusion:
                    proc_info = f"⚠️ Windows Dynamic Port Pool ({c.exclusion.start_port}–{c.exclusion.end_port})"
                md.append(
                    f"| **`{c.port}`** | {c.protocol.upper()} | `{c.source_file}` | {proc_info} |"
                )
        else:
            md.extend(
                [
                    "#### ✅ All Declared Ports Available",
                    "",
                    "All ports declared in stack configuration files are clear and ready for binding.",
                ]
            )

        write_step_summary("\n".join(md))

    if fail_on_conflict and result.has_conflicts:
        sys.stderr.write(f"PortTree: {conflict_count} port collision(s) detected!\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run_action())
