"""Tests for PortTree configuration, data classes, and Colors utility."""

from porttree.config import (
    Colors,
    DockerContainerInfo,
    ExcludedPortRange,
    PortEntry,
    ProcessNode,
    SocketInfo,
)


def test_colors_enable_disable():
    Colors.enable()
    assert Colors.is_enabled()
    styled = Colors.style("test", Colors.BOLD)
    assert "\033[1m" in styled

    Colors.disable()
    assert not Colors.is_enabled()
    unstyled = Colors.style("test", Colors.BOLD)
    assert unstyled == "test"


def test_colors_init_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    Colors.init()
    assert not Colors.is_enabled()


def test_colors_init_dumb_term(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    Colors.init()
    assert not Colors.is_enabled()


def test_colors_convenience_helpers():
    Colors.disable()
    assert Colors.port("3000") == "3000"
    assert Colors.proc("node") == "node"
    assert Colors.pid("1234") == "1234"
    assert Colors.git("main") == "main"
    assert Colors.docker("app") == "app"
    assert Colors.warn("warning") == "warning"
    assert Colors.error("error") == "error"
    assert Colors.success("ok") == "ok"
    assert Colors.dim("dimmed") == "dimmed"


def test_socket_info_to_dict():
    sock = SocketInfo(
        protocol="tcp",
        local_address="0.0.0.0",
        local_port=8080,
        state="LISTEN",
        pid=999,
        inode=123456,
    )
    d = sock.to_dict()
    assert d["protocol"] == "tcp"
    assert d["local_port"] == 8080
    assert d["pid"] == 999
    assert d["inode"] == 123456


def test_docker_container_info_to_dict():
    c = DockerContainerInfo(
        container_id="abcdef123456",
        name="api",
        image="python:3.11",
        compose_project="backend",
        compose_service="api",
        compose_workdir="/src",
        ports=["0.0.0.0:8000->8000/tcp"],
        status="Up 5 minutes",
    )
    d = c.to_dict()
    assert d["container_id"] == "abcdef123456"
    assert d["compose_project"] == "backend"
    assert d["ports"] == ["0.0.0.0:8000->8000/tcp"]


def test_process_node_all_pids():
    child2 = ProcessNode(pid=300)
    child1 = ProcessNode(pid=200, children=[child2])
    root = ProcessNode(pid=100, children=[child1])

    assert root.all_pids() == [100, 200, 300]


def test_process_node_to_dict():
    node = ProcessNode(
        pid=42,
        ppid=1,
        name="python",
        cmdline="python server.py",
        cwd="/workspace",
        git_branch="feat/auth",
        git_repo="my-app",
    )
    d = node.to_dict()
    assert d["pid"] == 42
    assert d["ppid"] == 1
    assert d["name"] == "python"
    assert d["git_branch"] == "feat/auth"
    assert d["children"] == []


def test_excluded_port_range():
    r = ExcludedPortRange(start_port=50000, end_port=50059, administered=True, protocol="tcp")
    assert r.contains(50000)
    assert r.contains(50025)
    assert r.contains(50059)
    assert not r.contains(49999)
    assert not r.contains(50060)

    d = r.to_dict()
    assert d["start_port"] == 50000
    assert d["administered"] is True


def test_port_entry_to_dict():
    entry = PortEntry(
        port=3000,
        protocol="tcp",
        is_conflict=True,
        source_file="docker-compose.yml",
    )
    d = entry.to_dict()
    assert d["port"] == 3000
    assert d["is_conflict"] is True
    assert d["source_file"] == "docker-compose.yml"
