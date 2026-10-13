"""Tests for Docker container unmasker."""

from unittest.mock import MagicMock, patch

from porttree.docker import DockerUnmasker


def test_is_docker_process():
    unmasker = DockerUnmasker()
    assert unmasker.is_docker_process("docker-proxy")
    assert unmasker.is_docker_process("docker-proxy.exe")
    assert unmasker.is_docker_process("com.docker.backend")
    assert unmasker.is_docker_process("podman")
    assert not unmasker.is_docker_process("node")
    assert not unmasker.is_docker_process("python3")


def test_parse_ports():
    unmasker = DockerUnmasker()
    ports_str = (
        "0.0.0.0:5432->5432/tcp, :::5432->5432/tcp, 127.0.0.1:8080->80/tcp, "
        "::1:3000->3000/tcp, [::1]:3001->3001/tcp, localhost:4000->4000/tcp"
    )
    ports = unmasker._parse_ports(ports_str)
    assert 5432 in ports
    assert 8080 in ports
    assert 3000 in ports
    assert 3001 in ports
    assert 4000 in ports

    # Test port range
    range_str = "0.0.0.0:8000-8002->8000-8002/tcp"
    range_ports = unmasker._parse_ports(range_str)
    assert range_ports == [8000, 8001, 8002]


def test_parse_labels():
    unmasker = DockerUnmasker()
    raw = (
        "com.docker.compose.project=ecommerce,"
        "com.docker.compose.service=postgres,"
        "com.docker.compose.project.working_dir=/home/user/apps/ecom"
    )
    labels = unmasker._parse_labels(raw)
    assert labels["com.docker.compose.project"] == "ecommerce"
    assert labels["com.docker.compose.service"] == "postgres"
    assert labels["com.docker.compose.project.working_dir"] == "/home/user/apps/ecom"


def test_query_cli_and_lookup():
    unmasker = DockerUnmasker()
    sample_ps = (
        "1a2b3c4d5e6f\tpostgres-db-1\t0.0.0.0:5432->5432/tcp, :::5432->5432/tcp\t"
        "postgres:16-alpine\tUp 3 hours\t"
        "com.docker.compose.project=my-saas,com.docker.compose.service=db\n"
        "2b3c4d5e6f7a\tredis-cache\t0.0.0.0:6379->6379/tcp\t"
        "redis:7-alpine\tUp 4 hours\t\n"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_ps)

        container_5432 = unmasker.get_container_for_port(5432)
        assert container_5432 is not None
        assert container_5432.name == "postgres-db-1"
        assert container_5432.image == "postgres:16-alpine"
        assert container_5432.compose_project == "my-saas"
        assert container_5432.compose_service == "db"

        container_6379 = unmasker.get_container_for_port(6379)
        assert container_6379 is not None
        assert container_6379.name == "redis-cache"

        assert unmasker.get_container_for_port(9999) is None


def test_docker_daemon_offline():
    unmasker = DockerUnmasker()
    with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
        res = unmasker.get_container_for_port(5432)
        assert res is None
