"""Tests for Windows NAT / Hyper-V Dynamic Port Exclusion detector."""

from unittest.mock import patch

from porttree.config import ExcludedPortRange
from porttree.winnat import (
    _parse_netsh_output,
    check_port_exclusion,
    format_winnat_diagnosis,
)


def test_parse_netsh_output():
    sample_output = """
Protocol tcp Port Exclusion Ranges

Start Port    End Port
----------    --------
      5357        5357
     50000       50059     *
     53337       53436

* - Administered port exclusions.
"""
    ranges = _parse_netsh_output(sample_output, protocol="tcp")
    assert len(ranges) == 3

    assert ranges[0].start_port == 5357
    assert ranges[0].end_port == 5357
    assert not ranges[0].administered

    assert ranges[1].start_port == 50000
    assert ranges[1].end_port == 50059
    assert ranges[1].administered

    assert ranges[2].start_port == 53337
    assert ranges[2].end_port == 53436
    assert not ranges[2].administered


def test_check_port_exclusion():
    with (
        patch("porttree.winnat.is_windows", return_value=True),
        patch("porttree.winnat.get_windows_port_exclusions") as mock_get,
    ):
        mock_get.return_value = [
            ExcludedPortRange(50000, 50059, administered=True, protocol="tcp"),
            ExcludedPortRange(53337, 53436, administered=False, protocol="tcp"),
        ]

        # Port in range
        hit = check_port_exclusion(50025)
        assert hit is not None
        assert hit.start_port == 50000

        # Port out of range
        miss = check_port_exclusion(3000)
        assert miss is None


def test_format_winnat_diagnosis():
    ex = ExcludedPortRange(50000, 50059, administered=True, protocol="tcp")
    diag = format_winnat_diagnosis(50025, ex)
    assert "50025" in diag
    assert "50000" in diag
    assert "net stop winnat" in diag
    assert "Hyper-V / WinNAT" in diag
