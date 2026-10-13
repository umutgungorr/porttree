"""Tests for GitHub Action runner and CI outputs."""

from unittest.mock import patch

from porttree.action import run_action, set_output, write_step_summary
from porttree.checker import CheckResult
from porttree.config import PortEntry, SocketInfo


def test_set_output(tmp_path):
    output_file = tmp_path / "github_output.txt"
    with patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_file)}):
        set_output("test-key", "test-val")
        content = output_file.read_text(encoding="utf-8")
        assert "test-key=test-val\n" in content


def test_write_step_summary(tmp_path):
    summary_file = tmp_path / "github_step_summary.md"
    with patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(summary_file)}):
        write_step_summary("### Test Summary Title")
        content = summary_file.read_text(encoding="utf-8")
        assert "### Test Summary Title" in content


def test_run_action_scan_mode(tmp_path):
    output_file = tmp_path / "github_output.txt"
    summary_file = tmp_path / "summary.md"

    mock_sockets = [
        SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=80, pid=10),
        SocketInfo(protocol="tcp", local_address="0.0.0.0", local_port=443, pid=20),
    ]

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
                "INPUT_PORTS": "",
                "INPUT_CHECK_FILE": "",
            },
        ),
        patch("porttree.action.scan_listening_sockets", return_value=mock_sockets),
    ):
        code = run_action()
        assert code == 0

        out_content = output_file.read_text(encoding="utf-8")
        assert "open-ports=80,443" in out_content
        assert "conflict-count=0" in out_content

        summary_content = summary_file.read_text(encoding="utf-8")
        assert "PortTree Socket Scan Summary" in summary_content


def test_run_action_preflight_conflict(tmp_path):
    output_file = tmp_path / "github_output.txt"
    summary_file = tmp_path / "summary.md"

    conflict = PortEntry(
        port=3000, protocol="tcp", is_conflict=True, source_file="docker-compose.yml"
    )
    check_res = CheckResult(conflicts=[conflict])

    with (
        patch.dict(
            "os.environ",
            {
                "GITHUB_OUTPUT": str(output_file),
                "GITHUB_STEP_SUMMARY": str(summary_file),
                "INPUT_PORTS": "3000",
                "INPUT_FAIL_ON_CONFLICT": "true",
            },
        ),
        patch("porttree.action.check_preflight", return_value=check_res),
        patch("porttree.action.scan_listening_sockets", return_value=[]),
    ):
        code = run_action()
        assert code == 1

        out_content = output_file.read_text(encoding="utf-8")
        assert "conflict-count=1" in out_content
        assert "conflicts=3000" in out_content
