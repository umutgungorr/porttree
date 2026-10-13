"""Pytest fixtures and test helpers for PortTree."""

import pytest

from porttree.config import (
    Colors,
    DockerContainerInfo,
    ProcessNode,
    SocketInfo,
)


@pytest.fixture(autouse=True)
def disable_terminal_colors():
    """Ensure consistent test outputs by disabling ANSI escape codes by default."""
    Colors.disable()
    yield
    Colors.enable()


@pytest.fixture
def sample_socket_info():
    """Sample SocketInfo instance for tests."""
    return SocketInfo(
        protocol="tcp",
        local_address="127.0.0.1",
        local_port=3000,
        state="LISTEN",
        pid=1234,
    )


@pytest.fixture
def sample_docker_container():
    """Sample DockerContainerInfo instance for tests."""
    return DockerContainerInfo(
        container_id="c1a2b3c4d5e6",
        name="web-frontend-1",
        image="node:18-alpine",
        compose_project="my-project",
        compose_service="web",
        compose_workdir="/app",
        ports=["0.0.0.0:3000->3000/tcp"],
        status="Up 2 hours",
    )


@pytest.fixture
def sample_process_tree():
    """Sample ProcessNode hierarchy with parent and child workers."""
    child1 = ProcessNode(
        pid=1235,
        ppid=1234,
        name="node worker",
        cmdline="node worker.js",
        args=["node", "worker.js"],
        cwd="/home/user/apps/web",
        git_branch="main",
        git_repo="web",
    )
    child2 = ProcessNode(
        pid=1236,
        ppid=1234,
        name="node worker",
        cmdline="node worker.js",
        args=["node", "worker.js"],
        cwd="/home/user/apps/web",
        git_branch="main",
        git_repo="web",
    )
    root = ProcessNode(
        pid=1234,
        ppid=1000,
        name="node server",
        cmdline="node server.js",
        args=["node", "server.js"],
        cwd="/home/user/apps/web",
        git_branch="main",
        git_repo="web",
        children=[child1, child2],
    )
    return root
