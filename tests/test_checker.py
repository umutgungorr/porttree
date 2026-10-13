"""Tests for pre-flight stack checking and port collision detection."""

from unittest.mock import patch

from porttree.checker import (
    check_preflight,
    parse_compose_file,
    parse_env_file,
    parse_package_json,
)
from porttree.config import ProcessNode, SocketInfo


def test_parse_compose_file(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        """version: '3.8'
services:
  web:
    image: nginx
    ports:
      - "8080:80"
      - "443:443"
  api:
    image: my-api
    ports:
      - "127.0.0.1:3000:3000"
      - "9000-9002:9000-9002"
""",
        encoding="utf-8",
    )
    ports = parse_compose_file(compose_path)
    port_nums = [p.port for p in ports]
    assert 8080 in port_nums
    assert 443 in port_nums
    assert 3000 in port_nums
    assert 9000 in port_nums
    assert 9001 in port_nums
    assert 9002 in port_nums

    # Verify context
    web_entry = next(p for p in ports if p.port == 8080)
    assert "web" in web_entry.context


def test_parse_package_json(tmp_path):
    pkg_path = tmp_path / "package.json"
    pkg_path.write_text(
        """{
  "name": "frontend",
  "scripts": {
    "dev": "next dev --port 3001",
    "start": "PORT=5000 node server.js",
    "preview": "vite preview -p 4173"
  }
}""",
        encoding="utf-8",
    )
    ports = parse_package_json(pkg_path)
    port_nums = [p.port for p in ports]
    assert 3001 in port_nums
    assert 5000 in port_nums
    assert 4173 in port_nums


def test_parse_env_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        """PORT=8000
DATABASE_URL=postgres://localhost:5432/db
APP_PORT=8001
HOST=0.0.0.0
""",
        encoding="utf-8",
    )
    ports = parse_env_file(env_path)
    port_nums = [p.port for p in ports]
    assert 8000 in port_nums
    assert 8001 in port_nums


def test_check_preflight_clean(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  app:\n    ports:\n      - '3000:3000'\n", encoding="utf-8"
    )

    with (
        patch("porttree.checker.scan_listening_sockets", return_value=[]),
        patch("porttree.checker.check_port_exclusion", return_value=None),
    ):
        res = check_preflight(files=[str(compose_path)])
        assert not res.has_conflicts
        assert len(res.clean_ports) == 1
        assert res.clean_ports[0].port == 3000


def test_check_preflight_with_conflict(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  app:\n    ports:\n      - '3000:3000'\n", encoding="utf-8"
    )

    mock_sockets = [SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=3000, pid=7777)]
    mock_node = ProcessNode(pid=7777, name="node", cmdline="node server.js")

    with (
        patch("porttree.checker.scan_listening_sockets", return_value=mock_sockets),
        patch("porttree.checker.check_port_exclusion", return_value=None),
        patch("porttree.tree.ProcessResolver.build_full_tree", return_value=mock_node),
    ):
        res = check_preflight(files=[str(compose_path)])
        assert res.has_conflicts
        assert len(res.conflicts) == 1
        c = res.conflicts[0]
        assert c.port == 3000
        assert c.process is not None
        assert c.process.pid == 7777


def test_parse_compose_file_long_syntax(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        """version: '3.8'
services:
  web:
    image: nginx
    ports:
      - target: 80
        published: 8080
        protocol: tcp
      - target: 443
        published: "8443"
""",
        encoding="utf-8",
    )
    ports = parse_compose_file(compose_path)
    port_nums = [p.port for p in ports]
    assert 8080 in port_nums
    assert 8443 in port_nums


def test_parse_env_file_quotes_and_comments_and_urls(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        """PORT="3000"
APP_PORT='8080'
SERVER_PORT=5000 # production port
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
REDIS_URL=redis://127.0.0.1:6379/0
""",
        encoding="utf-8",
    )
    ports = parse_env_file(env_path)
    port_nums = [p.port for p in ports]
    assert 3000 in port_nums
    assert 8080 in port_nums
    assert 5000 in port_nums
    assert 5432 in port_nums
    assert 6379 in port_nums


def test_parse_package_json_config_port(tmp_path):
    pkg_path = tmp_path / "package.json"
    pkg_path.write_text(
        """{
  "name": "my-service",
  "port": 3000,
  "config": {
    "port": 8080
  }
}""",
        encoding="utf-8",
    )
    ports = parse_package_json(pkg_path)
    port_nums = [p.port for p in ports]
    assert 3000 in port_nums
    assert 8080 in port_nums
