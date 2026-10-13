"""Edge case and boundary condition tests for PortTree."""

from porttree.checker import (
    _extract_compose_host_ports,
    parse_compose_file,
    parse_env_file,
    parse_package_json,
)
from porttree.cli import _parse_port_argument
from porttree.config import PortEntry, ProcessNode
from porttree.docker import DockerUnmasker
from porttree.formatter import TreeFormatter
from porttree.killer import _is_pid_alive, _terminate_pid
from porttree.scanner import _parse_hex_ipv4, _parse_hex_ipv6
from porttree.tree import find_git_info
from porttree.winnat import _parse_netsh_output


def test_parse_port_argument_edge_cases():
    assert _parse_port_argument("") == []
    assert _parse_port_argument("   ") == []
    assert _parse_port_argument("0") == []
    assert _parse_port_argument("65536") == []
    assert _parse_port_argument("-5") == []
    assert _parse_port_argument("abc") == []
    assert _parse_port_argument("1,65535") == [1, 65535]
    assert _parse_port_argument("5000-5002") == [5000, 5001, 5002]
    # Inverted range
    assert _parse_port_argument("5002-5000") == [5000, 5001, 5002]
    # Duplicates in range
    assert _parse_port_argument("3000,3000-3001") == [3000, 3001]


def test_extract_compose_host_ports():
    assert _extract_compose_host_ports("") == []
    assert _extract_compose_host_ports("invalid:invalid:invalid:extra") == []
    assert _extract_compose_host_ports("80/tcp") == [80]
    assert _extract_compose_host_ports('"127.0.0.1:4000:4000/udp"') == [4000]
    assert _extract_compose_host_ports("8080:80") == [8080]
    assert _extract_compose_host_ports("3000-3002:3000-3002") == [3000, 3001, 3002]
    # Invalid port range
    assert _extract_compose_host_ports("abc-def:80") == []


def test_parse_package_json_edge_cases(tmp_path):
    p = tmp_path / "package.json"
    # Non-existent
    assert parse_package_json(tmp_path / "missing.json") == []

    # Corrupt JSON
    p.write_text("{invalid json", encoding="utf-8")
    assert parse_package_json(p) == []

    # Valid JSON without scripts
    p.write_text('{"name": "test"}', encoding="utf-8")
    assert parse_package_json(p) == []

    # Scripts not a dict
    p.write_text('{"scripts": "echo hello"}', encoding="utf-8")
    assert parse_package_json(p) == []

    # Scripts with non-string values
    p.write_text('{"scripts": {"dev": 123}}', encoding="utf-8")
    assert parse_package_json(p) == []


def test_parse_env_file_edge_cases(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """# PORT=9000
INVALID_PORT=not_a_number
PORT=0
PORT=99999
PORT=3000
SERVER_PORT=8080
""",
        encoding="utf-8",
    )
    res = parse_env_file(env_file)
    ports = [r.port for r in res]
    assert 9000 not in ports  # Commented
    assert 0 not in ports  # Out of range
    assert 99999 not in ports  # Out of range
    assert 3000 in ports
    assert 8080 in ports


def test_parse_compose_file_edge_cases(tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    assert parse_compose_file(tmp_path / "nonexistent.yml") == []

    # Empty file
    compose_file.write_text("", encoding="utf-8")
    assert parse_compose_file(compose_file) == []

    # No ports block
    compose_file.write_text("services:\n  web:\n    image: nginx\n", encoding="utf-8")
    assert parse_compose_file(compose_file) == []


def test_formatter_long_cmdline():
    formatter = TreeFormatter(use_ascii=True)
    long_cmd = "python " + "arg " * 50
    node = ProcessNode(pid=100, name="python", cmdline=long_cmd)
    entry = PortEntry(port=8000, protocol="tcp", process=node)

    out = formatter.render_tree([entry])
    assert "..." in out  # Truncated cleanly
    assert "PORT 8000" in out


def test_formatter_empty():
    formatter = TreeFormatter(use_ascii=True)
    assert "No listening ports" in formatter.render_tree([])
    assert "No listening ports" in formatter.render_compact([])


def test_is_pid_alive_edge_cases():
    assert not _is_pid_alive(0)
    assert not _is_pid_alive(-1)


def test_terminate_pid_edge_cases():
    assert not _terminate_pid(0)
    assert not _terminate_pid(-1)


def test_parse_hex_corrupted():
    assert _parse_hex_ipv4("ZZZZ") == "ZZZZ"
    assert _parse_hex_ipv6("ZZZZ") == "ZZZZ"


def test_winnat_parse_empty():
    assert _parse_netsh_output("", "tcp") == []
    assert _parse_netsh_output("Invalid output without table", "tcp") == []


def test_find_git_info_invalid_paths():
    assert find_git_info(None) == (None, None)
    assert find_git_info("") == (None, None)


def test_docker_parse_ports_edge_cases():
    unmasker = DockerUnmasker()
    assert unmasker._parse_ports("") == []
    assert unmasker._parse_ports("80/tcp") == []
    assert unmasker._parse_ports("0.0.0.0:80->80/tcp") == [80]
