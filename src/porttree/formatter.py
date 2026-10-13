"""Terminal tree formatter and structured output renderer for PortTree.

Supports Unicode ANSI tree branches (├─, └─), compact tabular views,
JSON dumps, and automatic ASCII fallback for legacy consoles.
"""

from __future__ import annotations

import json
import sys

from porttree.checker import CheckResult
from porttree.config import Colors, PortEntry, ProcessNode
from porttree.killer import KillResult


class TreeGlyphs:
    """Branch symbols for hierarchical tree rendering."""

    UTF8_TEE = "├─ "
    UTF8_ELBOW = "└─ "
    UTF8_PIPE = "│  "
    UTF8_SPACE = "   "
    UTF8_HORIZ = "── "

    ASCII_TEE = "|-- "
    ASCII_ELBOW = "\\-- "
    ASCII_PIPE = "|   "
    ASCII_SPACE = "    "
    ASCII_HORIZ = "-- "

    def __init__(self, use_ascii: bool = False):
        # Auto-detect if stdout can render UTF-8
        is_utf8 = False
        try:
            encoding = getattr(sys.stdout, "encoding", "") or ""
            is_utf8 = "utf" in encoding.lower()
        except Exception:
            is_utf8 = False

        if use_ascii or not is_utf8:
            self.tee = self.ASCII_TEE
            self.elbow = self.ASCII_ELBOW
            self.pipe = self.ASCII_PIPE
            self.space = self.ASCII_SPACE
            self.horiz = self.ASCII_HORIZ
        else:
            self.tee = self.UTF8_TEE
            self.elbow = self.UTF8_ELBOW
            self.pipe = self.UTF8_PIPE
            self.space = self.UTF8_SPACE
            self.horiz = self.UTF8_HORIZ


class TreeFormatter:
    """Formats PortEntries and scan results into visual terminal trees."""

    def __init__(self, use_ascii: bool = False):
        self.glyphs = TreeGlyphs(use_ascii=use_ascii)

    def render_tree(self, entries: list[PortEntry]) -> str:
        """Render a list of PortEntries into a rich hierarchical ANSI tree."""
        if not entries:
            return f"{Colors.dim('No listening ports or collisions found.')}"

        lines: list[str] = []
        for i, entry in enumerate(entries):
            # Port Header
            port_label = Colors.port(f"PORT {entry.port}")
            proto_label = Colors.dim(f"({entry.protocol.upper()})")

            if entry.exclusion and not entry.sockets:
                status_badge = Colors.warn("[RESERVED BY KERNEL]")
            elif entry.is_conflict:
                status_badge = Colors.error("[CONFLICT]")
            else:
                status_badge = Colors.success("[LISTEN]")

            # Addresses summary
            addrs = (
                ", ".join(f"{s.local_address}:{s.local_port}" for s in entry.sockets)
                if entry.sockets
                else ""
            )
            addr_str = f" {Colors.dim('• ' + addrs)}" if addrs else ""

            source_str = (
                f" {Colors.warn('• from ' + entry.source_file)}" if entry.source_file else ""
            )

            lines.append(f"{port_label} {proto_label} {status_badge}{addr_str}{source_str}")

            # If Windows Kernel Exclusion
            if entry.exclusion:
                r = entry.exclusion
                excl_text = (
                    f"{Colors.warn('⚠️  Windows NAT / Hyper-V dynamic exclusion')} "
                    f"({r.start_port}–{r.end_port})"
                )
                if not entry.process and not entry.docker_info:
                    lines.append(f" {self.glyphs.elbow}{excl_text}")
                else:
                    lines.append(f" {self.glyphs.tee}{excl_text}")

            # If Docker Container info
            if entry.docker_info:
                d = entry.docker_info
                dock_line = (
                    f"{Colors.docker('🐳 Docker:')} {Colors.style(d.name, Colors.BOLD, Colors.CYAN)} "
                    f"{Colors.dim('(' + d.image + ')')}"
                )
                if d.compose_service or d.compose_project:
                    svc = d.compose_service or "service"
                    proj = f" @ {d.compose_project}" if d.compose_project else ""
                    dock_line += f" {Colors.git('[' + svc + proj + ']')}"

                if entry.process:
                    lines.append(f" {self.glyphs.tee}{dock_line}")
                else:
                    lines.append(f" {self.glyphs.elbow}{dock_line}")

            # If Process Tree
            if entry.process:
                proc_lines = self._render_process_node(entry.process, prefix=" ")
                lines.extend(proc_lines)
            elif not entry.exclusion and not entry.docker_info:
                # Sockets with unknown PID
                lines.append(
                    f" {self.glyphs.elbow}{Colors.dim('Unknown process (run as admin/sudo to inspect PID)')}"
                )

            if i < len(entries) - 1:
                lines.append("")

        return "\n".join(lines)

    def _render_process_node(
        self,
        node: ProcessNode,
        prefix: str = "",
        is_last: bool = True,
    ) -> list[str]:
        """Recursively format a process node and its children."""
        lines: list[str] = []

        branch = self.glyphs.elbow if is_last else self.glyphs.tee
        proc_str = Colors.proc(node.name or f"pid-{node.pid}")
        pid_str = Colors.pid(f"(PID {node.pid})")

        meta_parts: list[str] = []
        if node.git_branch:
            repo_info = f" ({node.git_repo})" if node.git_repo else ""
            meta_parts.append(Colors.git(f"git: {node.git_branch}{repo_info}"))

        if node.cwd:
            meta_parts.append(Colors.dim(node.cwd))

        meta_str = f" [{' '.join(meta_parts)}]" if meta_parts else ""

        lines.append(f"{prefix}{branch}{proc_str} {pid_str}{meta_str}")

        # Render cmdline if distinctive
        if node.cmdline and node.cmdline != node.name:
            cmd_indent = prefix + (self.glyphs.space if is_last else self.glyphs.pipe)
            # Truncate cmdline if extremely long
            display_cmd = node.cmdline if len(node.cmdline) <= 120 else node.cmdline[:117] + "..."
            lines.append(f"{cmd_indent}  {Colors.dim('$ ' + display_cmd)}")

        # Render children
        child_prefix = prefix + (self.glyphs.space if is_last else self.glyphs.pipe)
        for idx, child in enumerate(node.children):
            is_child_last = idx == len(node.children) - 1
            child_lines = self._render_process_node(
                child,
                prefix=child_prefix,
                is_last=is_child_last,
            )
            lines.extend(child_lines)

        return lines

    def render_compact(self, entries: list[PortEntry]) -> str:
        """Render a compact table view (one row per port)."""
        if not entries:
            return f"{Colors.dim('No listening ports found.')}"

        header = f"{'PORT':<8} {'PROTO':<6} {'STATUS':<10} {'PID':<8} {'PROCESS':<20} {'DETAILS'}"
        sep = "-" * 80
        rows = [Colors.style(header, Colors.BOLD), Colors.dim(sep)]

        for e in entries:
            port_col = str(e.port)
            proto_col = e.protocol.upper()

            if e.exclusion and not e.sockets:
                status_col = "RESERVED"
                pid_col = "-"
                proc_col = "Kernel / WinNAT"
                detail_col = f"Exclusion {e.exclusion.start_port}-{e.exclusion.end_port}"
            else:
                status_col = "CONFLICT" if e.is_conflict else "LISTEN"
                pid_col = str(e.process.pid) if e.process else "-"
                proc_col = e.process.name if e.process else "Unknown"

                detail_parts: list[str] = []
                if e.docker_info:
                    detail_parts.append(f"🐳 {e.docker_info.name}")
                if e.process and e.process.git_branch:
                    detail_parts.append(f"git:{e.process.git_branch}")
                if e.source_file:
                    detail_parts.append(f"from {e.source_file}")

                detail_col = " | ".join(detail_parts) or "-"

            c_port = Colors.port(f"{port_col:<8}")
            c_proto = Colors.dim(f"{proto_col:<6}")
            status_styled = (
                Colors.success(f"{status_col:<10}")
                if status_col == "LISTEN"
                else Colors.warn(f"{status_col:<10}")
            )
            c_pid = Colors.pid(f"{pid_col:<8}")
            proc_disp = proc_col if len(proc_col) <= 20 else proc_col[:17] + "..."
            c_proc = Colors.proc(f"{proc_disp:<20}")

            rows.append(f"{c_port} {c_proto} {status_styled} {c_pid} {c_proc} {detail_col}")

        return "\n".join(rows)

    def render_check_result(self, result: CheckResult) -> str:
        """Render the pre-flight check report."""
        lines: list[str] = []
        lines.append(f"{Colors.style('🔍 PortTree Pre-Flight Stack Check', Colors.BOLD)}")
        lines.append(Colors.dim("=" * 45))

        if result.checked_files:
            lines.append(f"{Colors.dim('Files scanned:')} {', '.join(result.checked_files)}")
        lines.append(f"{Colors.dim('Declared ports:')} {len(result.declared_ports)}")
        lines.append("")

        if not result.has_conflicts:
            lines.append(f"{Colors.success('✅ ALL CLEAR')}: No port collisions detected.")
            if result.clean_ports:
                for c in result.clean_ports:
                    lines.append(
                        f"   • Port {Colors.port(str(c.port))} ({c.protocol.upper()}) ready for {Colors.dim(c.source_file + ' [' + c.context + ']')}"
                    )
            return "\n".join(lines)

        lines.append(
            f"{Colors.error('❌ PORT CONFLICTS DETECTED')}: {len(result.conflicts)} collision(s) found!"
        )
        lines.append(Colors.dim("The following declared ports are already occupied or reserved:\n"))

        lines.append(self.render_tree(result.conflicts))
        lines.append("")
        lines.append(
            f"{Colors.warn('Tip:')} Free conflicting ports with: {Colors.BOLD}porttree free <PORT>{Colors.RESET}"
        )
        return "\n".join(lines)

    def render_kill_result(self, result: KillResult) -> str:
        """Render the result of a port kill/free command."""
        lines: list[str] = []
        port_str = Colors.port(str(result.port))

        if result.dry_run:
            lines.append(f"{Colors.warn('🔍 DRY RUN PREVIEW')} for Port {port_str}:")
            lines.append(f"   {result.message}")
            return "\n".join(lines)

        if result.success:
            lines.append(f"{Colors.success('✅ SUCCESS')}: {result.message}")
            if result.killed_pids:
                lines.append(f"   Terminated PIDs: {Colors.pid(str(result.killed_pids))}")
        else:
            lines.append(f"{Colors.error('❌ FAILED')}: {result.message}")

        return "\n".join(lines)

    @staticmethod
    def render_json(data: object) -> str:
        """Serialize data to formatted JSON."""
        return json.dumps(data, indent=2, ensure_ascii=False)
