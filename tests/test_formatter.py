"""Tests for terminal tree formatter and output renderers."""

import json

from porttree.checker import CheckResult
from porttree.config import (
    DeclaredPort,
    DockerContainerInfo,
    ExcludedPortRange,
    PortEntry,
    ProcessNode,
    SocketInfo,
)
from porttree.formatter import TreeFormatter, TreeGlyphs
from porttree.killer import KillResult


def test_tree_glyphs_selection():
    utf8_g = TreeGlyphs(use_ascii=False)
    ascii_g = TreeGlyphs(use_ascii=True)

    assert ascii_g.elbow == "\\-- "
    assert ascii_g.tee == "|-- "
    assert utf8_g.elbow in ("└─ ", "\\-- ")


def test_render_tree_standard(sample_process_tree):
    formatter = TreeFormatter(use_ascii=True)
    sock = SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=1234)
    entry = PortEntry(
        port=3000,
        protocol="tcp",
        sockets=[sock],
        process=sample_process_tree,
    )

    out = formatter.render_tree([entry])
    assert "PORT 3000" in out
    assert "node server" in out
    assert "PID 1234" in out
    assert "git: main" in out
    assert "node worker" in out
    assert "PID 1235" in out


def test_render_tree_docker():
    formatter = TreeFormatter(use_ascii=True)
    d = DockerContainerInfo(
        container_id="c1a2b3",
        name="postgres-db",
        image="postgres:16",
        compose_project="app",
        compose_service="db",
    )
    entry = PortEntry(
        port=5432,
        protocol="tcp",
        docker_info=d,
    )
    out = formatter.render_tree([entry])
    assert "PORT 5432" in out
    assert "Docker:" in out
    assert "postgres-db" in out
    assert "postgres:16" in out
    assert "db @ app" in out


def test_render_tree_winnat():
    formatter = TreeFormatter(use_ascii=True)
    ex = ExcludedPortRange(50000, 50059, protocol="tcp")
    entry = PortEntry(
        port=50025,
        protocol="tcp",
        exclusion=ex,
    )
    out = formatter.render_tree([entry])
    assert "PORT 50025" in out
    assert "RESERVED BY KERNEL" in out
    assert "50000–50059" in out


def test_render_compact():
    formatter = TreeFormatter(use_ascii=True)
    p = ProcessNode(pid=8888, name="python3")
    entry = PortEntry(port=8000, protocol="tcp", process=p)

    out = formatter.render_compact([entry])
    assert "PORT" in out
    assert "8000" in out
    assert "python3" in out
    assert "8888" in out


def test_render_json():
    formatter = TreeFormatter()
    data = {"status": "ok", "ports": [3000, 8080]}
    json_str = formatter.render_json(data)
    loaded = json.loads(json_str)
    assert loaded["status"] == "ok"
    assert loaded["ports"] == [3000, 8080]


def test_render_check_result_clean():
    formatter = TreeFormatter(use_ascii=True)
    res = CheckResult(
        declared_ports=[DeclaredPort(port=3000, source_file="package.json", context="dev")],
        clean_ports=[DeclaredPort(port=3000, source_file="package.json", context="dev")],
    )
    out = formatter.render_check_result(res)
    assert "ALL CLEAR" in out
    assert "Port 3000" in out


def test_render_check_result_conflicts():
    formatter = TreeFormatter(use_ascii=True)
    conflict = PortEntry(port=3000, protocol="tcp", is_conflict=True, source_file="package.json")
    res = CheckResult(
        conflicts=[conflict],
    )
    out = formatter.render_check_result(res)
    assert "PORT CONFLICTS DETECTED" in out
    assert "PORT 3000" in out


def test_render_kill_result():
    formatter = TreeFormatter(use_ascii=True)
    res = KillResult(port=3000, success=True, killed_pids=[100, 101], message="Freed port 3000")
    out = formatter.render_kill_result(res)
    assert "SUCCESS" in out
    assert "Freed port 3000" in out
    assert "100" in out


def test_render_compact_alignment_no_color():
    from porttree.config import Colors

    Colors.disable()
    try:
        formatter = TreeFormatter(use_ascii=True)
        p = ProcessNode(pid=1234, name="node")
        entry = PortEntry(port=80, protocol="tcp", process=p)
        out = formatter.render_compact([entry])
        lines = out.splitlines()
        header = lines[0]
        data_row = lines[2]

        # Verify that column headers and values start at identical indices
        assert header.index("PORT") == data_row.index("80")
        assert header.index("PROTO") == data_row.index("TCP")
        assert header.index("STATUS") == data_row.index("LISTEN")
        assert header.index("PID") == data_row.index("1234")
        assert header.index("PROCESS") == data_row.index("node")
    finally:
        Colors.enable()
